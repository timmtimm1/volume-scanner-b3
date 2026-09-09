"""Cliente da brapi.dev -- fornecedor primario de cotacoes da B3."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from scanner.cotacoes.base import Cotacao, ticker_valido

logger = logging.getLogger(__name__)

BASE_URL = "https://brapi.dev/api/quote"
TIMEOUT_SECONDS = 15.0

# Teto de tickers por requisicao. Lote grande demais e recusado INTEIRO (401),
# entao perder a resposta toda por excesso e pior do que fazer duas chamadas.
#
# Medido em 09/09/2026 contra a API: sem token, lotes de 1, 2 e 3 respondem
# 200 e o de 5 responde 401. Com token o limite e bem maior -- o portfolio-api
# usa 10 ha tempos sem problema.
LOTE_COM_TOKEN = 10
LOTE_SEM_TOKEN = 3


@dataclass(frozen=True)
class BrapiClient:
    """Fonte primaria: dado da B3, uma requisicao para varios papeis."""

    token: str | None = None
    nome: str = "brapi"

    @property
    def lote_maximo(self) -> int:
        return LOTE_COM_TOKEN if self.token else LOTE_SEM_TOKEN

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        # Ticker invalido nem sai daqui: ele iria no caminho da URL.
        limpos = [t.upper() for t in tickers if ticker_valido(t.upper())]
        lote = self.lote_maximo
        resultado: dict[str, Cotacao] = {}
        for inicio in range(0, len(limpos), lote):
            resultado.update(self._buscar_lote(limpos[inicio : inicio + lote]))
        return resultado

    def _buscar_lote(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        url = f"{BASE_URL}/{','.join(tickers)}"
        params = {"token": self.token} if self.token else {}
        try:
            resposta = httpx.get(url, params=params, timeout=TIMEOUT_SECONDS)
            resposta.raise_for_status()
            dados = resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Log sem a URL nem os parametros: o token vai na query string, e um
            # log de erro com ela vazaria a credencial para quem ler o log do
            # Actions -- que e publico neste repositorio.
            logger.warning("[brapi] falha ao buscar %s: %s", tickers, type(exc).__name__)
            return {}
        return _extrair(dados)


def _extrair(dados: object) -> dict[str, Cotacao]:
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
        if not isinstance(simbolo, str) or preco is None:
            continue
        try:
            valor = Decimal(str(preco))
        except (InvalidOperation, TypeError):
            continue
        if valor <= 0:
            continue  # preco zero ou negativo e dado corrompido, nao cotacao
        cotacoes[simbolo.upper()] = Cotacao(simbolo.upper(), valor, "brapi")
    return cotacoes
