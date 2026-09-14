"""Cliente da brapi.dev -- fornecedor de cotacoes da B3 com contrato e token."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx

from scanner.cotacoes.base import Cotacao, ticker_valido

logger = logging.getLogger(__name__)

BASE_URL = "https://brapi.dev/api/quote"
TIMEOUT_SECONDS = 15.0

# Papeis por requisicao. Lote acima do que o plano permite e recusado INTEIRO,
# entao o padrao e o unico valor que funciona em qualquer plano.
#
# Medido em 14/09/2026: sem token a brapi responde 401 (MISSING_TOKEN) para
# qualquer papel fora dos quatro de teste (PETR4, VALE3, MGLU3, ITUB4). Pela
# FAQ, o plano gratuito aceita 1 papel por requisicao, o Startup 10 e o Pro 20.
# O codigo antigo mandava lotes de 10 com token e a brapi recusou todas as
# checagens de 10/09 a 14/09 -- o Yahoo cobriu, e ninguem viu.
LOTE_PADRAO = 1


@dataclass(frozen=True)
class BrapiClient:
    """Dado da B3 com token. Uma requisicao por lote de `lote` papeis."""

    token: str
    lote: int = LOTE_PADRAO
    nome: str = "brapi"

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        # Ticker invalido nem sai daqui: ele iria no caminho da URL.
        limpos = [t.upper() for t in tickers if ticker_valido(t.upper())]
        passo = max(1, self.lote)
        resultado: dict[str, Cotacao] = {}
        for inicio in range(0, len(limpos), passo):
            resultado.update(self._buscar_lote(limpos[inicio : inicio + passo]))
        return resultado

    def _buscar_lote(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        url = f"{BASE_URL}/{','.join(tickers)}"
        # Token no cabecalho, como a brapi recomenda: na query string ele iria
        # parar em qualquer log que imprimisse a URL.
        cabecalhos = {"Authorization": f"Bearer {self.token}"}
        try:
            resposta = httpx.get(url, headers=cabecalhos, timeout=TIMEOUT_SECONDS)
            resposta.raise_for_status()
            dados = resposta.json()
        except httpx.HTTPStatusError as exc:
            # O status diz o motivo: 401 e token, 402/429 e cota, 400 e lote.
            # Antes so o nome da excecao aparecia, e a falha ficou dias sem causa.
            logger.warning("[brapi] %s recusado com HTTP %s", tickers, exc.response.status_code)
            return {}
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("[brapi] falha ao buscar %s: %s", tickers, type(exc).__name__)
            return {}
        return extrair(dados)


def _hora(bruto: object) -> datetime | None:
    """`regularMarketTime` da brapi: texto ISO com fuso, como 2026-09-14T16:14:30.000Z."""
    if not isinstance(bruto, str):
        return None
    try:
        hora = datetime.fromisoformat(bruto)
    except ValueError:
        return None
    return hora if hora.tzinfo is not None else None


def extrair(dados: object) -> dict[str, Cotacao]:
    """Le a resposta defensivamente.

    Um campo que suma numa atualizacao do fornecedor viraria KeyError e
    derrubaria a checagem inteira, silenciando TODOS os alertas -- nao so o do
    papel com problema. O que nao vier no formato esperado e ignorado.
    """
    if not isinstance(dados, dict):
        return {}
    resultados = dados.get("results")
    if not isinstance(resultados, list):
        return {}

    cotacoes: dict[str, Cotacao] = {}
    for item in resultados:
        if not isinstance(item, dict):
            continue
        simbolo = item.get("symbol")
        preco = item.get("regularMarketPrice")
        hora = _hora(item.get("regularMarketTime"))
        if not isinstance(simbolo, str) or preco is None or hora is None:
            continue
        try:
            valor = Decimal(str(preco))
        except (InvalidOperation, TypeError):
            continue
        if valor <= 0:
            continue  # preco zero ou negativo e dado corrompido, nao cotacao
        cotacoes[simbolo.upper()] = Cotacao(simbolo.upper(), valor, "brapi", hora)
    return cotacoes
