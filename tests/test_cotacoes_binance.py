"""Cotacao de cripto: a maxima do dia UTC na Binance, para o aviso de entrada."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from scanner.cotacoes import binance
from scanner.cotacoes.binance import BinanceDiaClient, extrair

ABRE = 1794873600000  # 17/11/2026 00:00 UTC
FECHA = ABRE + 86_400_000 - 1


def item(simbolo: str, maxima: str = "65200.00", fecha: int = FECHA) -> dict[str, Any]:
    return {
        "symbol": simbolo,
        "openPrice": "64882.88",
        "highPrice": maxima,
        "lowPrice": "64079.83",
        "lastPrice": "65018.51",
        "openTime": fecha - 86_400_000 + 1,
        "closeTime": fecha,
    }


def test_a_cotacao_e_a_maxima_do_dia_e_nao_o_ultimo_preco() -> None:
    agora = datetime(2026, 11, 17, 12, 43, tzinfo=UTC)
    c = extrair([item("BTCUSDT"), item("SHIBUSDT", "0.0000042")], agora)
    assert c["BTC"].preco == Decimal("65200.00")
    assert c["SHIB"].preco == Decimal("0.0000042")  # sem perder casa nenhuma
    assert c["BTC"].hora == agora
    assert "máxima do dia" in c["BTC"].fonte


def test_dia_que_ja_fechou_fica_com_a_hora_daquele_dia() -> None:
    """Resposta velha cai fora em `cotacoes_de_hoje`, como cotacao de ontem."""
    agora = datetime(2026, 11, 18, 0, 5, tzinfo=UTC)
    c = extrair([item("BTCUSDT")], agora)
    assert c["BTC"].hora.date() == datetime(2026, 11, 17, tzinfo=UTC).date()


def test_resposta_fora_do_formato_nao_vira_cotacao() -> None:
    agora = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    assert extrair({"code": -1121, "msg": "Invalid symbol."}, agora) == {}
    assert extrair([{"symbol": "BTCUSDT"}, item("ETHBTC"), item("XUSDT", "0")], agora) == {}


class Binance:
    """A Binance de mentira: recusa o lote inteiro se uma moeda nao existe."""

    def __init__(self, conhecidas: set[str]) -> None:
        self.conhecidas = conhecidas
        self.pedidos: list[list[str]] = []

    def __call__(self, url: str, params: dict[str, str], timeout: float) -> httpx.Response:
        import json

        simbolos = json.loads(params["symbols"])
        self.pedidos.append(simbolos)
        pedido = httpx.Request("GET", url)
        if any(s not in self.conhecidas for s in simbolos):
            return httpx.Response(400, json={"code": -1121}, request=pedido)
        return httpx.Response(200, json=[item(s) for s in simbolos], request=pedido)


def test_moeda_deslistada_nao_derruba_as_outras(monkeypatch: pytest.MonkeyPatch) -> None:
    falsa = Binance({"BTCUSDT", "ETHUSDT"})
    monkeypatch.setattr(binance.httpx, "get", falsa)
    c = BinanceDiaClient().cotacoes(["btc", "ETH", "LUNA"])
    assert set(c) == {"BTC", "ETH"}
    assert falsa.pedidos[0] == ["BTCUSDT", "ETHUSDT", "LUNAUSDT"]  # primeiro o lote
    assert len(falsa.pedidos) == 4  # depois uma por vez


def test_mais_de_cem_moedas_vao_em_lotes(monkeypatch: pytest.MonkeyPatch) -> None:
    moedas = [f"M{i:03d}" for i in range(150)]
    falsa = Binance({f"{m}USDT" for m in moedas})
    monkeypatch.setattr(binance.httpx, "get", falsa)
    assert len(BinanceDiaClient().cotacoes(moedas)) == 150
    assert [len(p) for p in falsa.pedidos] == [100, 50]


def test_ticker_estranho_nao_vai_para_a_url(monkeypatch: pytest.MonkeyPatch) -> None:
    falsa = Binance({"BTCUSDT"})
    monkeypatch.setattr(binance.httpx, "get", falsa)
    BinanceDiaClient().cotacoes(["BTC", "../x", ""])
    assert falsa.pedidos == [["BTCUSDT"]]


def test_em_cripto_a_checagem_usa_a_binance(monkeypatch: pytest.MonkeyPatch) -> None:
    from scanner import cli, mercado

    monkeypatch.setenv(mercado.VARIAVEL, "cripto")
    assert isinstance(cli._provedor_de_cotacoes(), BinanceDiaClient)
