"""Quais moedas a aba Cripto acompanha: as maiores por valor de mercado.

Decisao do usuario em 16/11/2026: as 50 maiores com par em dolar (USDT) na
Binance, sem stablecoin. O ranking por valor de mercado vem da CoinGecko (a
mesma fonte e as mesmas categorias excluidas do resumo da semana); a Binance
diz quais delas tem par negociando.

Moeda que sai das 50 continua sendo carregada enquanto tiver barra no banco:
um setup aberto nela precisa do candle de amanha para encerrar. Ela sai da
lista da aba (`no_top` falso) e some sozinha quando a retencao podar as barras.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from scanner.semana.fontes import FonteIndisponivelError
from scanner.semana.fontes.cripto import (
    FONTE,
    PAUSA_ENTRE_CHAMADAS,
    _consultar,
    ids_da_categoria,
)

# A CoinGecko devolve ate 250 por pagina. As 50 maiores com par na Binance
# saem das ~90 primeiras; 250 da folga para o dia em que isso mudar.
CONSULTADAS = 250


def escolher(
    ranking: Any, excluidos: set[str], pares: dict[str, str], top: int
) -> list[dict[str, Any]]:
    """As `top` maiores do `ranking` que tem par em `pares` e nao estao excluidas.

    Duas moedas diferentes podem ter o mesmo simbolo na CoinGecko; vale a de
    maior valor de mercado (a primeira do ranking), que e a que a Binance lista.
    """
    if not isinstance(ranking, list):
        raise FonteIndisponivelError(FONTE, "formato inesperado (ranking nao e lista)")
    escolhidas: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for item in ranking:
        if not isinstance(item, dict) or item.get("id") in excluidos:
            continue
        simbolo = str(item.get("symbol", "")).upper()
        if not simbolo or simbolo in vistos or simbolo not in pares:
            continue
        vistos.add(simbolo)
        escolhidas.append(
            {
                "ticker": simbolo,
                "par": pares[simbolo],
                "nome": str(item.get("name") or simbolo),
                "posicao": len(escolhidas) + 1,
                "valor_de_mercado": item.get("market_cap"),
            }
        )
        if len(escolhidas) == top:
            break
    return escolhidas


def buscar_maiores(
    pares: dict[str, str],
    *,
    top: int,
    categorias_excluidas: list[str],
    cliente: httpx.Client | None = None,
    dormir: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Consulta a CoinGecko e devolve as `top` maiores com par na Binance."""
    ranking = _consultar(
        {"vs_currency": "usd", "order": "market_cap_desc", "per_page": CONSULTADAS, "page": 1},
        cliente,
        dormir,
    )
    excluidos: set[str] = set()
    for categoria in categorias_excluidas:
        dormir(PAUSA_ENTRE_CHAMADAS)
        dados = _consultar(
            {"vs_currency": "usd", "category": categoria, "per_page": 250}, cliente, dormir
        )
        excluidos |= ids_da_categoria(dados)
    return escolher(ranking, excluidos, pares, top)
