"""A Monero pela Kraken: candles fechados, maxima do dia e a copia da lista no site."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from scanner import mercado
from scanner.cotacoes import kraken as cotacao
from scanner.cotacoes.binance import BinanceDiaClient
from scanner.cotacoes.kraken import CriptoDiaClient
from scanner.cripto import kraken
from scanner.semana.fontes import FonteIndisponivelError

DIA = 86_400
ABRE = int(datetime(2026, 11, 21, tzinfo=UTC).timestamp())
AGORA = datetime(2026, 11, 23, 15, 0, tzinfo=UTC)


def candle(t: int, volume: str = "100") -> list[Any]:
    return [t, "500", "520", "490", "510", "505", volume, 42]


def test_so_grava_dia_fechado_e_pula_dia_sem_negocio() -> None:
    candles = [candle(ABRE - DIA, "0"), candle(ABRE), candle(ABRE + DIA), candle(ABRE + 2 * DIA)]
    barras = kraken.candles_para_barras("XMR", candles, AGORA)
    assert [d.date() for d in barras["trade_date"]] == [date(2026, 11, 21), date(2026, 11, 22)]
    assert barras["volume_financial"].iloc[0] == 50_500
    assert barras["avg_price"].iloc[0] == 505


def test_erro_da_kraken_vira_fonte_indisponivel() -> None:
    with pytest.raises(FonteIndisponivelError):
        kraken.resultado_do_par({"error": ["EQuery:Unknown asset pair"], "result": {}})


def test_busca_desde_o_dia_pedido() -> None:
    urls: list[httpx.URL] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        urls.append(pedido.url)
        corpo = [candle(ABRE - DIA), candle(ABRE), candle(ABRE + DIA)]
        return httpx.Response(200, json={"error": [], "result": {"XXMRZUSD": corpo, "last": 1}})

    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        barras = kraken.buscar_barras(
            "XMR", "XMRUSD", date(2026, 11, 21), agora=AGORA, cliente=cliente
        )
    assert len(barras) == 2
    assert urls[0].params["pair"] == "XMRUSD"
    assert urls[0].params["interval"] == "1440"


def test_cotacao_separa_as_corretoras(monkeypatch: pytest.MonkeyPatch) -> None:
    pedidas_na_binance: list[str] = []

    def binance(_self: BinanceDiaClient, moedas: list[str]) -> dict[str, Any]:
        pedidas_na_binance.extend(moedas)
        return {}

    def kraken_get(_url: str, **_: Any) -> httpx.Response:
        dados = {"error": [], "result": {"XXMRZUSD": {"h": ["520.10", "530"]}}}
        return httpx.Response(200, json=dados, request=httpx.Request("GET", cotacao.BASE_URL))

    monkeypatch.setattr(BinanceDiaClient, "cotacoes", binance)
    monkeypatch.setattr(cotacao.httpx, "get", kraken_get)
    achadas = CriptoDiaClient().cotacoes(["btc", "XMR"])
    assert pedidas_na_binance == ["BTC"]
    assert achadas["XMR"].preco == Decimal("520.10")
    assert "kraken" in achadas["XMR"].fonte


def test_a_lista_do_site_e_a_mesma_do_pipeline() -> None:
    texto = (Path(__file__).parents[1] / "web/src/lib/mercado.ts").read_text(encoding="utf-8")
    achado = re.search(r"MOEDAS_FORA_DA_BINANCE:[^=]*=\s*\{([^}]*)\}", texto)
    assert achado is not None
    no_site = dict(re.findall(r"(\w+):\s*\"(\w+)\"", achado.group(1)))
    assert no_site == mercado.MOEDAS_FORA_DA_BINANCE
