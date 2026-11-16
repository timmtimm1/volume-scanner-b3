"""A escolha das maiores moedas: ranking da CoinGecko cruzado com os pares da Binance."""

from __future__ import annotations

import pytest

from scanner.cripto.universo import escolher
from scanner.semana.fontes import FonteIndisponivelError

RANKING = [
    {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "market_cap": 1.3e12},
    {"id": "tether", "symbol": "usdt", "name": "Tether", "market_cap": 1.8e11},
    {"id": "ethereum", "symbol": "eth", "name": "Ethereum", "market_cap": 3.7e11},
    {"id": "usd-coin", "symbol": "usdc", "name": "USDC", "market_cap": 7.0e10},
    {"id": "hyperliquid", "symbol": "hype", "name": "Hyperliquid", "market_cap": 1.2e10},
    {"id": "leo-token", "symbol": "leo", "name": "LEO Token", "market_cap": 9.0e9},
    {"id": "solana", "symbol": "sol", "name": "Solana", "market_cap": 8.0e10},
    {"id": "sol-falso", "symbol": "sol", "name": "Outra SOL", "market_cap": 1.0e6},
    {"id": "dogecoin", "symbol": "doge", "name": "Dogecoin", "market_cap": 2.0e10},
]
PARES = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "USDC": "USDCUSDT",
    "SOL": "SOLUSDT",
    "DOGE": "DOGEUSDT",
}


def test_tira_stablecoin_e_quem_nao_tem_par_e_renumera() -> None:
    escolhidas = escolher(RANKING, {"tether", "usd-coin"}, PARES, top=3)
    assert [(m["ticker"], m["par"], m["posicao"]) for m in escolhidas] == [
        ("BTC", "BTCUSDT", 1),
        ("ETH", "ETHUSDT", 2),
        ("SOL", "SOLUSDT", 3),
    ]
    assert escolhidas[0]["nome"] == "Bitcoin"
    assert escolhidas[0]["valor_de_mercado"] == 1.3e12


def test_simbolo_repetido_vale_a_de_maior_valor() -> None:
    escolhidas = escolher(RANKING, {"tether", "usd-coin"}, PARES, top=10)
    sol = [m for m in escolhidas if m["ticker"] == "SOL"]
    assert len(sol) == 1 and sol[0]["nome"] == "Solana"
    assert [m["ticker"] for m in escolhidas] == ["BTC", "ETH", "SOL", "DOGE"]


def test_ranking_fora_do_formato_e_fonte_indisponivel() -> None:
    with pytest.raises(FonteIndisponivelError):
        escolher({"status": {"error_code": 429}}, set(), PARES, top=3)
