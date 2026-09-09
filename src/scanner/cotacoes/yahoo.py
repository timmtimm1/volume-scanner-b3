"""Cliente do Yahoo Finance -- reserva, sem cadastro nem token."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from scanner.cotacoes.base import Cotacao, ticker_valido

logger = logging.getLogger(__name__)

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
TIMEOUT_SECONDS = 15.0

# Sem User-Agent de navegador o Yahoo responde 429 em TODA requisicao, mesmo a
# primeira -- nao e limite de taxa de verdade, e recusa a cliente sem cara de
# navegador. Medido em 09/09/2026: sem o header, 429; com ele, 200.
CABECALHOS = {"User-Agent": "Mozilla/5.0 (compatible; volume-scanner-b3)"}


@dataclass(frozen=True)
class YahooClient:
    """Reserva. Uma requisicao por papel, sem token, com algum atraso.

    Serve para cobrir o que a brapi nao respondeu -- e nao para substitui-la:
    com muitos alertas, uma requisicao por papel fica lento.
    """

    nome: str = "yahoo"

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        encontradas: dict[str, Cotacao] = {}
        for bruto in tickers:
            ticker = bruto.upper()
            if not ticker_valido(ticker):
                continue
            cotacao = self._buscar(ticker)
            if cotacao is not None:
                encontradas[ticker] = cotacao
        return encontradas

    def _buscar(self, ticker: str) -> Cotacao | None:
        # O sufixo ".SA" nasce e morre AQUI, no adaptador. O banco guarda
        # "PETR4"; a convencao do Yahoo para a B3 nao e parte do papel.
        try:
            resposta = httpx.get(
                f"{BASE_URL}/{ticker}.SA",
                params={"range": "1d", "interval": "1d"},
                headers=CABECALHOS,
                timeout=TIMEOUT_SECONDS,
            )
            resposta.raise_for_status()
            dados = resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("[yahoo] falha ao buscar %s: %s", ticker, type(exc).__name__)
            return None

        try:
            meta = dados["chart"]["result"][0]["meta"]
            bruto = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
            valor = Decimal(str(bruto))
        except (KeyError, IndexError, TypeError, InvalidOperation):
            return None

        return Cotacao(ticker, valor, "yahoo") if valor > 0 else None
