"""Ranking de criptomoedas pela CoinGecko (API publica, sem chave).

"Cripto" aqui exclui o que nao se comporta como cripto: stablecoins e papeis
tokenizados (ouro, titulos, imoveis). Medido em 17/10/2026, o top 40 por valor
de mercado tinha 8 stablecoins (tether, usd-coin, usds, ethena-usde, dai,
usd1-wlfi, global-dollar, paypal-usd) e 2 papeis tokenizados (tether-gold,
figure-heloc); sem tirar, o ranking de 7 dias seria 25% de moedas que nao se
mexem. A exclusao usa as categorias da propria CoinGecko, configuraveis.

A janela de variacao e de 7 dias terminando na HORA DA COLETA, nao na sexta:
a API publica nao devolve outra. Por isso o payload carrega `coletado_em`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from scanner.semana.fontes import FonteIndisponivelError, baixar

FONTE = "coingecko"
BASE_URL = "https://api.coingecko.com/api/v3/coins/markets"
MOEDAS_CONSULTADAS = 60

# A API publica da CoinGecko responde 429 depois de ~5 chamadas rapidas. Sao 5
# chamadas por montagem (ranking + 4 categorias): 4 s entre elas fica abaixo.
PAUSA_ENTRE_CHAMADAS = 4.0
TETO_RETRY_AFTER = 60.0

BTC = "bitcoin"
ETH = "ethereum"


def _moeda(item: dict[str, Any], rank: int) -> dict[str, Any]:
    variacao = item.get("price_change_percentage_7d_in_currency")
    return {
        "id": item["id"],
        "simbolo": str(item["symbol"]).upper(),
        "nome": item["name"],
        "preco": item.get("current_price"),
        "market_cap": item.get("market_cap"),
        "rank": rank,
        "variacao_7d": None if variacao is None else float(variacao) / 100,
    }


def ids_da_categoria(mercado: Any) -> set[str]:
    """Os `id` de uma resposta de `coins/markets` (de uma categoria)."""
    if not isinstance(mercado, list):
        raise FonteIndisponivelError(FONTE, "formato inesperado (categoria nao e lista)")
    return {str(item["id"]) for item in mercado if isinstance(item, dict) and "id" in item}


def montar_cripto(
    mercado: list[dict[str, Any]], excluidos: set[str], top: int, destaques: int
) -> dict[str, Any]:
    """O ranking sem as categorias excluidas, BTC, ETH e as maiores altas e quedas.

    `moedas` sao as `top` maiores por valor de mercado depois da exclusao, com
    `rank` = posicao nessa lista filtrada. As altas e quedas saem dessas mesmas
    moedas, sem BTC e ETH (que ja vem em campo proprio).

    Alta e so quem subiu e queda so quem caiu: numa semana em que tres moedas
    subiram, a lista de altas tem tres, e nao duas quedas para completar.
    Variacao zero nao entra em nenhuma.
    """
    validas = [m for m in mercado if isinstance(m, dict) and m.get("id") not in excluidos]
    moedas = [_moeda(m, posicao) for posicao, m in enumerate(validas[:top], start=1)]

    def destaque(id_: str) -> dict[str, Any] | None:
        return next((m for m in moedas if m["id"] == id_), None)

    candidatas = [m for m in moedas if m["id"] not in (BTC, ETH) and m["variacao_7d"] is not None]
    subiram = [m for m in candidatas if m["variacao_7d"] > 0]
    cairam = [m for m in candidatas if m["variacao_7d"] < 0]
    altas = sorted(subiram, key=lambda m: (-m["variacao_7d"], m["rank"]))[:destaques]
    quedas = sorted(cairam, key=lambda m: (m["variacao_7d"], m["rank"]))[:destaques]
    return {
        "moedas": moedas,
        "btc": destaque(BTC),
        "eth": destaque(ETH),
        "altas": altas,
        "quedas": quedas,
    }


def _consultar(
    parametros: dict[str, str | int],
    cliente: httpx.Client | None,
    dormir: Callable[[float], None],
) -> Any:
    url = f"{BASE_URL}?{urlencode(parametros)}"
    try:
        resposta = baixar(FONTE, url, cliente=cliente)
    except FonteIndisponivelError as exc:
        if exc.status != 429:
            raise
        # Uma tentativa a mais, respeitando o Retry-After (com teto).
        dormir(min(exc.retry_after or PAUSA_ENTRE_CHAMADAS * 3, TETO_RETRY_AFTER))
        resposta = baixar(FONTE, url, cliente=cliente)
    try:
        return resposta.json()
    except ValueError as exc:
        raise FonteIndisponivelError(FONTE, "resposta nao e JSON") from exc


def buscar_cripto(
    *,
    categorias_excluidas: list[str],
    top: int,
    destaques: int,
    agora: datetime | None = None,
    cliente: httpx.Client | None = None,
    dormir: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Consulta o ranking e as categorias excluidas e monta o bloco de cripto."""
    coletado_em = (agora or datetime.now(UTC)).astimezone(UTC)
    mercado = _consultar(
        {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": MOEDAS_CONSULTADAS,
            "page": 1,
            "price_change_percentage": "7d",
        },
        cliente,
        dormir,
    )
    if not isinstance(mercado, list):
        raise FonteIndisponivelError(FONTE, "formato inesperado (ranking nao e lista)")

    excluidos: set[str] = set()
    for categoria in categorias_excluidas:
        dormir(PAUSA_ENTRE_CHAMADAS)
        dados = _consultar(
            {"vs_currency": "usd", "category": categoria, "per_page": 250}, cliente, dormir
        )
        excluidos |= ids_da_categoria(dados)

    bloco = montar_cripto(mercado, excluidos, top, destaques)
    bloco["coletado_em"] = coletado_em.isoformat()
    return bloco
