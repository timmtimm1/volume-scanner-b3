"""Candles da Binance -> barras do banco."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx
import pandas as pd
import pytest

from scanner.cripto import binance
from scanner.ingest.cotahist import BAR_COLUMNS
from scanner.semana.fontes import FonteIndisponivelError

DIA = 86_400_000
T0 = int(datetime(2026, 11, 13, tzinfo=UTC).timestamp() * 1000)


def candle(
    i: int, close: str = "65351.05", volume: str = "100.5", dolar: str = "6500000.129"
) -> list[Any]:
    abre = T0 + i * DIA
    return [abre, "64150.01", "66132.01", "62006.00", close, volume, abre + DIA - 1, dolar, 7395485]


def test_candle_vira_barra_com_data_utc_e_volume_em_dolar() -> None:
    agora = datetime(2026, 11, 16, 0, 5, tzinfo=UTC)
    barras = binance.candles_para_barras("BTC", [candle(0), candle(1), candle(2)], agora)
    assert list(barras.columns) == list(BAR_COLUMNS)
    assert list(barras["trade_date"].dt.date) == [
        date(2026, 11, 13),
        date(2026, 11, 14),
        date(2026, 11, 15),
    ]
    linha = barras.iloc[0]
    assert linha["ticker"] == "BTC"
    assert (linha["open"], linha["high"], linha["low"], linha["close"]) == (
        64150.01,
        66132.01,
        62006.00,
        65351.05,
    )
    assert linha["volume_financial"] == 6500000.13
    assert linha["avg_price"] == pytest.approx(6500000.129 / 100.5)
    assert linha["volume_shares"] == 100  # arredondado: a coluna e inteira
    assert linha["trades_count"] == 7395485
    assert not linha["trades_censored"]


def test_candle_do_dia_em_andamento_nao_entra() -> None:
    # 23h55 UTC do dia 15: o candle do dia 15 ainda muda a cada negocio.
    agora = datetime(2026, 11, 15, 23, 55, tzinfo=UTC)
    barras = binance.candles_para_barras("BTC", [candle(0), candle(1), candle(2)], agora)
    assert list(barras["trade_date"].dt.date) == [date(2026, 11, 13), date(2026, 11, 14)]


def test_dia_sem_negocio_e_buraco_e_nao_zero() -> None:
    agora = datetime(2026, 11, 20, tzinfo=UTC)
    parado = candle(1, volume="0.0", dolar="0.0")
    barras = binance.candles_para_barras("LUNA", [candle(0), parado, candle(2)], agora)
    assert list(barras["trade_date"].dt.date) == [date(2026, 11, 13), date(2026, 11, 15)]


def test_preco_minusculo_nao_perde_casas() -> None:
    agora = datetime(2026, 11, 20, tzinfo=UTC)
    c = [
        T0,
        "0.00000412",
        "0.00000431",
        "0.00000401",
        "0.00000425",
        "1239694456608",
        T0 + DIA - 1,
        "4931024.92",
        35312,
    ]
    linha = binance.candles_para_barras("SHIB", [c], agora).iloc[0]
    assert linha["close"] == 0.00000425
    assert linha["volume_shares"] == 1239694456608


def test_formato_inesperado_e_fonte_indisponivel() -> None:
    agora = datetime(2026, 11, 20, tzinfo=UTC)
    with pytest.raises(FonteIndisponivelError):
        binance.candles_para_barras("BTC", {"code": -1121, "msg": "Invalid symbol."}, agora)
    with pytest.raises(FonteIndisponivelError):
        binance.candles_para_barras("BTC", [[T0, "abc"]], agora)
    assert binance.candles_para_barras("BTC", [], agora).empty


def test_pares_em_dolar_tira_parado_alavancado_e_outra_cotacao() -> None:
    info = {
        "symbols": [
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING"},
            {"symbol": "BTCBRL", "baseAsset": "BTC", "quoteAsset": "BRL", "status": "TRADING"},
            {"symbol": "LUNAUSDT", "baseAsset": "LUNA", "quoteAsset": "USDT", "status": "BREAK"},
            {
                "symbol": "BTCUPUSDT",
                "baseAsset": "BTCUP",
                "quoteAsset": "USDT",
                "status": "TRADING",
            },
            {"symbol": "JUPUSDT", "baseAsset": "JUP", "quoteAsset": "USDT", "status": "TRADING"},
        ]
    }
    # JUP termina em "UP" mas e moeda de verdade (3 letras): fica.
    assert binance.pares_em_dolar(info) == {"BTC": "BTCUSDT", "JUP": "JUPUSDT"}
    assert set(binance.pares_em_dolar(info, so_negociando=False)) == {"BTC", "LUNA", "JUP"}
    with pytest.raises(FonteIndisponivelError):
        binance.pares_em_dolar({"code": 0})


def test_buscar_barras_pagina_de_mil_em_mil(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(binance.VARIAVEL_BASE, raising=False)
    pedidos: list[str] = []
    inicio = int(datetime(2020, 1, 1, tzinfo=UTC).timestamp() * 1000)

    def responder(request: httpx.Request) -> httpx.Response:
        pedidos.append(str(request.url))
        de = int(request.url.params["startTime"])
        primeiro = (de - inicio) // DIA
        quantos = max(0, min(1000, 1500 - primeiro))
        corpo = []
        for i in range(primeiro, primeiro + quantos):
            abre = inicio + i * DIA
            corpo.append([abre, "1", "2", "0.5", "1.5", "10", abre + DIA - 1, "15", 3])
        return httpx.Response(200, json=corpo)

    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        barras = binance.buscar_barras(
            "XYZ",
            "XYZUSDT",
            date(2020, 1, 1),
            agora=datetime(2026, 1, 1, tzinfo=UTC),
            cliente=cliente,
            dormir=lambda _: None,
        )
    assert len(pedidos) == 2
    assert pedidos[0].startswith("https://data-api.binance.vision/api/v3/klines?symbol=XYZUSDT")
    assert len(barras) == 1500
    assert barras["trade_date"].is_unique
    assert barras["trade_date"].iloc[-1] == pd.Timestamp(2020, 1, 1) + pd.Timedelta(days=1499)


def test_endereco_alternativo_pela_variavel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(binance.VARIAVEL_BASE, "https://api.binance.com/api/v3/")
    vistos: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        vistos.append(request.url.host)
        return httpx.Response(200, json={"symbols": []})

    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        assert binance.buscar_pares(cliente=cliente) == {}
    assert vistos == ["api.binance.com"]


def test_ultimo_dia_fechado_e_ontem_em_utc() -> None:
    assert binance.ultimo_dia_fechado(datetime(2026, 11, 16, 0, 5, tzinfo=UTC)) == date(
        2026, 11, 15
    )
