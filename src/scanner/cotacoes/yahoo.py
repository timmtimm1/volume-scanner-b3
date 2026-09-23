"""Cliente do Yahoo Finance -- sem cadastro nem token, sem contrato."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

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
    """Uma requisicao por papel, sem token. Medido em 14/09: ~15 min de atraso."""

    nome: str = "yahoo"
    # `regularMarketTime` do Yahoo e a hora do ultimo negocio: em 23/09/2026,
    # 10:10:14 para um papel cujo ultimo negocio tinha sido aquele. Por isso ele
    # entra na disputa por hora mais nova.
    hora_e_do_negocio: bool = True

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
        except httpx.HTTPStatusError as exc:
            logger.warning("[yahoo] %s recusado com HTTP %s", ticker, exc.response.status_code)
            return None
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("[yahoo] falha ao buscar %s: %s", ticker, type(exc).__name__)
            return None
        return extrair(ticker, dados)


def extrair(ticker: str, dados: Any) -> Cotacao | None:
    """Preco e hora do `meta` da resposta, ou None se faltar qualquer um.

    Nao ha reserva para `chartPreviousClose`: ele e o fechamento de ONTEM, e
    usa-lo quando falta o preco de agora faria um alerta disparar com um preco
    que nao existe mais.
    """
    try:
        meta = dados["chart"]["result"][0]["meta"]
        valor = Decimal(str(meta["regularMarketPrice"]))
        hora = datetime.fromtimestamp(int(meta["regularMarketTime"]), tz=UTC)
    except (KeyError, IndexError, TypeError, ValueError, InvalidOperation, OverflowError):
        return None
    return Cotacao(ticker, valor, "yahoo", hora) if valor > 0 else None
