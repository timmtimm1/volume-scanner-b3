"""Cotacao de cripto pela Binance, para os avisos de entrada (aba Cripto).

Devolve a MAXIMA do dia UTC de cada moeda, e nao o ultimo preco. A checagem roda
de 15 em 15 minutos; com o ultimo preco, um pico entre duas passadas que tocou o
gatilho e voltou passaria em branco. A entrada do setup e "passou da maxima do
candle" em qualquer momento do dia, e a maxima do dia responde exatamente isso.
O alerta de cripto e sempre `acima` (so os setups criam alerta em cripto), entao
a maxima e o preco que importa. `fonte` diz isso na mensagem.

Endpoint: `ticker/tradingDay` do espelho publico de dados de mercado
(`data-api.binance.vision`, o mesmo da carga: o `api.binance.com` recusa os
Estados Unidos, onde roda o Actions). Ate 100 moedas por chamada. O dia de
negociacao e o dia UTC, o mesmo do candle diario.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from scanner.cotacoes.base import Cotacao

logger = logging.getLogger(__name__)

BASE_URL = "https://data-api.binance.vision/api/v3/ticker/tradingDay"
POR_CHAMADA = 100
TIMEOUT_SECONDS = 30.0
COTACAO = "USDT"
FONTE = "binance, máxima do dia"


def extrair(dados: Any, agora: datetime) -> dict[str, Cotacao]:
    """Resposta do `tradingDay` -> cotacao (a maxima) por moeda.

    `hora`: agora, se o dia da resposta ainda esta aberto; senao, o fim daquele
    dia. Assim um dia que ja fechou (resposta velha) cai fora em
    `cotacoes_de_hoje`, como cotacao de ontem.
    """
    if not isinstance(dados, list):
        return {}
    saida: dict[str, Cotacao] = {}
    for item in dados:
        if not isinstance(item, dict):
            continue
        simbolo = str(item.get("symbol", ""))
        if not simbolo.endswith(COTACAO):
            continue
        try:
            maxima = Decimal(str(item["highPrice"]))
            fecha = datetime.fromtimestamp(int(item["closeTime"]) / 1000, UTC)
        except (KeyError, ValueError, TypeError, InvalidOperation):
            continue
        if maxima <= 0:
            continue
        moeda = simbolo[: -len(COTACAO)]
        saida[moeda] = Cotacao(ticker=moeda, preco=maxima, fonte=FONTE, hora=min(agora, fecha))
    return saida


@dataclass(frozen=True)
class BinanceDiaClient:
    """Maxima do dia UTC, em lotes de ate 100 moedas, sem chave."""

    nome: str = "binance"
    # A hora vem do proprio dia de negociacao da Binance (ver `extrair`).
    hora_e_do_negocio: bool = True

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        moedas = sorted({t.upper() for t in tickers if t and t.isalnum()})
        encontradas: dict[str, Cotacao] = {}
        for i in range(0, len(moedas), POR_CHAMADA):
            lote = moedas[i : i + POR_CHAMADA]
            dados = self._buscar(lote)
            if dados is None and len(lote) > 1:
                # Uma moeda que a Binance deixou de negociar derruba o lote
                # inteiro (HTTP 400). Uma por vez, as outras continuam.
                for moeda in lote:
                    um = self._buscar([moeda])
                    if um is not None:
                        encontradas.update(extrair(um, datetime.now(UTC)))
                continue
            encontradas.update(extrair(dados, datetime.now(UTC)))
        return encontradas

    def _buscar(self, moedas: Sequence[str]) -> Any:
        simbolos = json.dumps([f"{m}{COTACAO}" for m in moedas], separators=(",", ":"))
        try:
            resposta = httpx.get(
                BASE_URL, params={"symbols": simbolos, "type": "MINI"}, timeout=TIMEOUT_SECONDS
            )
            resposta.raise_for_status()
            return resposta.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "[binance] %s recusado com HTTP %s", moedas[:3], exc.response.status_code
            )
            return None
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("[binance] falha ao buscar %s: %s", moedas[:3], type(exc).__name__)
            return None
