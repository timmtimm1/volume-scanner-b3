"""Maxima do dia das criptos: na Binance e, para quem ela nao negocia, na Kraken.

Como em `cotacoes/binance.py`, vale a MAXIMA do dia UTC, para um pico entre duas
passadas de 15 minutos nao escapar do aviso. Par suspenso na Binance ainda
responde com o preco antigo, entao a moeda da Kraken nunca e perguntada a ela.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from scanner import mercado
from scanner.cotacoes.base import Cotacao
from scanner.cotacoes.binance import BinanceDiaClient

logger = logging.getLogger(__name__)

BASE_URL = "https://api.kraken.com/0/public/Ticker"
TIMEOUT_SECONDS = 30.0
FONTE = "kraken, máxima do dia"


def extrair(dados: Any, moeda: str, agora: datetime) -> Cotacao | None:
    """Resposta do `Ticker` -> a maxima de hoje (posicao 0 de `h`, desde 00:00 UTC)."""
    if not isinstance(dados, dict) or dados.get("error"):
        return None
    resultado = dados.get("result")
    if not isinstance(resultado, dict) or len(resultado) != 1:
        return None
    linha = next(iter(resultado.values()))
    try:
        maxima = Decimal(str(linha["h"][0]))
    except (KeyError, IndexError, TypeError, InvalidOperation):
        return None
    if maxima <= 0:
        return None
    return Cotacao(ticker=moeda, preco=maxima, fonte=FONTE, hora=agora)


@dataclass(frozen=True)
class CriptoDiaClient:
    """Separa as moedas pela corretora de cada uma e junta as respostas."""

    binance: BinanceDiaClient = field(default_factory=BinanceDiaClient)
    nome: str = "binance+kraken"
    hora_e_do_negocio: bool = True

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        pedidas = {t.upper() for t in tickers if t and t.isalnum()}
        fora = pedidas & set(mercado.MOEDAS_FORA_DA_BINANCE)
        restantes = sorted(pedidas - fora)
        encontradas = self.binance.cotacoes(restantes) if restantes else {}
        for moeda in sorted(fora):
            cotacao = extrair(
                self._buscar(mercado.MOEDAS_FORA_DA_BINANCE[moeda]), moeda, datetime.now(UTC)
            )
            if cotacao is not None:
                encontradas[moeda] = cotacao
        return encontradas

    def _buscar(self, par: str) -> Any:
        try:
            resposta = httpx.get(BASE_URL, params={"pair": par}, timeout=TIMEOUT_SECONDS)
            resposta.raise_for_status()
            return resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("[kraken] falha ao buscar %s: %s", par, type(exc).__name__)
            return None
