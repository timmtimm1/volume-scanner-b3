"""Cliente da brapi.dev -- fornecedor de cotacoes da B3 com contrato e token.

Usa a API v2 (`/api/v2/stocks/quote`), que a propria brapi recomenda para
integracoes novas: o endpoint v1 (`/api/quote/{tickers}`) continua funcionando,
mas e chamado de "legado" na documentacao. A v2 tambem avisa quando um ticker
foi renomeado (`changed`), o que o v1 nao fazia -- um alerta cadastrado no
codigo antigo de um papel renomeado ficaria sem cotacao, em silencio.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx

from scanner.cotacoes.base import Cota, Cotacao, ticker_valido

logger = logging.getLogger(__name__)

BASE_URL = "https://brapi.dev/api/v2/stocks/quote"
TIMEOUT_SECONDS = 15.0

# Papeis por requisicao. Lote acima do que o plano permite e recusado INTEIRO,
# entao o padrao e o unico valor que funciona em qualquer plano.
#
# Medido em 14/09/2026 contra o v1 (mesma conta, mesmo gateway de autenticacao
# do v2): sem token a brapi responde 401 (MISSING_TOKEN) para qualquer papel
# fora dos quatro de teste (PETR4, VALE3, MGLU3, ITUB4). Pela FAQ, o plano
# gratuito aceita 1 papel por requisicao, o Startup 10 e o Pro 20. O codigo
# antigo mandava lotes de 10 com token e a brapi recusou todas as checagens de
# 10/09 a 14/09 -- o Yahoo cobriu, e ninguem viu.
LOTE_PADRAO = 1

# A brapi manda dois pares de cabecalho de limite. Os `ratelimit-*` sao a
# janela curta -- 20 por minuto no gratuito, medido em 23/09/2026 -- e os
# `x-ratelimit-*` sao a cota do plano, 15 mil por mes no gratuito. E a do plano
# que interessa aqui: a checagem roda 36 vezes por pregao e o risco real e
# acabar o mes, nao estourar o minuto.
COTA_RESTANTE = "x-ratelimit-remaining"
COTA_LIMITE = "x-ratelimit-limit"

# Abaixo disto o aviso sobe de INFO para WARNING. Sao 36 passadas por pregao e
# ~21 pregoes por mes: com menos de mil requisicoes sobrando, um unico papel a
# mais na lista de alertas ja nao cabe ate o fim do ciclo.
COTA_BAIXA = 1_000


def _inteiro(bruto: object) -> int | None:
    """Cabecalho que nao veio, ou veio com texto, nao vira cota."""
    if not isinstance(bruto, str):
        return None
    try:
        return int(bruto.strip())
    except ValueError:
        return None


def ler_cota(cabecalhos: Mapping[str, str]) -> Cota:
    """A cota do plano, como a brapi a anuncia na resposta.

    Vale para resposta boa e para recusa: o 429 tambem carrega os cabecalhos, e
    e justamente ali que saber o numero importa.
    """
    return Cota(_inteiro(cabecalhos.get(COTA_RESTANTE)), _inteiro(cabecalhos.get(COTA_LIMITE)))


@dataclass
class _UltimaCota:
    """Caixa mutavel para um cliente congelado.

    `BrapiClient` e `frozen=True` de proposito -- ninguem deve trocar o token no
    meio de uma execucao. A cota, ao contrario, muda a cada resposta. Uma caixa
    mutavel guarda a ultima sem abrir o resto do objeto para escrita.
    """

    valor: Cota = field(default_factory=Cota)


@dataclass(frozen=True)
class BrapiClient:
    """Dado da B3 com token. Uma requisicao por lote de `lote` papeis."""

    token: str
    lote: int = LOTE_PADRAO
    nome: str = "brapi"
    # A hora da brapi e a da resposta, nao a do negocio -- ver
    # `ProvedorDeCotacoes.hora_e_do_negocio`, que traz a medicao. Com `False`
    # aqui ela deixa de disputar por hora e vira reserva: consultada so para o
    # papel que o Yahoo nao soube responder.
    hora_e_do_negocio: bool = False
    # `compare=False` e `repr=False`: a cota e estado observado, nao identidade
    # do cliente. Dois clientes com o mesmo token continuam iguais.
    _cota: _UltimaCota = field(default_factory=_UltimaCota, compare=False, repr=False)

    @property
    def cota(self) -> Cota:
        """A cota do plano, pela ultima resposta que a informou.

        Resposta sem os cabecalhos nao apaga o que ja se sabia: um numero de
        cinco minutos atras informa, e `Cota()` vazia nao informa nada.
        """
        return self._cota.valor

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        # Ticker invalido nem sai daqui: ele iria no parametro da URL.
        limpos = [t.upper() for t in tickers if ticker_valido(t.upper())]
        passo = max(1, self.lote)
        resultado: dict[str, Cotacao] = {}
        for inicio in range(0, len(limpos), passo):
            resultado.update(self._buscar_lote(limpos[inicio : inicio + passo]))
        return resultado

    def _buscar_lote(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        # Token no cabecalho, como a brapi recomenda: na query string ele iria
        # parar em qualquer log que imprimisse a URL.
        cabecalhos = {"Authorization": f"Bearer {self.token}"}
        params = {"symbols": ",".join(tickers)}
        try:
            resposta = httpx.get(
                BASE_URL, params=params, headers=cabecalhos, timeout=TIMEOUT_SECONDS
            )
            self._anotar_cota(resposta)
            resposta.raise_for_status()
            dados = resposta.json()
        except httpx.HTTPStatusError as exc:
            # O status diz o motivo: 401 e token, 402/429 e cota, 400 e lote.
            # Antes so o nome da excecao aparecia, e a falha ficou dias sem causa.
            logger.warning(
                "[brapi] %s recusado com HTTP %s (cota %s)",
                tickers,
                exc.response.status_code,
                self.cota.resumo(),
            )
            return {}
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("[brapi] falha ao buscar %s: %s", tickers, type(exc).__name__)
            return {}
        return extrair(dados)

    def _anotar_cota(self, resposta: httpx.Response) -> None:
        """Guarda a cota da resposta e avisa quando ela fica curta."""
        cota = ler_cota(resposta.headers)
        if cota.vazia:
            return
        self._cota.valor = cota
        if cota.restantes is not None and cota.restantes <= COTA_BAIXA:
            logger.warning("[brapi] cota baixa: %s requisicoes restantes", cota.resumo())
        else:
            logger.info("[brapi] cota %s", cota.resumo())


def _hora(bruto: object) -> datetime | None:
    """`regularMarketTime`: texto ISO com fuso, como 2026-09-14T16:14:30.000Z."""
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

    A chave do resultado e `symbol`, nao `requestedSymbol`: se a brapi disser
    que o ticker mudou (`changed: true`), e o codigo NOVO que deve aparecer no
    dicionario -- e o que um alerta cadastrado no codigo antigo precisa achar.
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
        info = item.get("data")
        if not isinstance(simbolo, str) or not isinstance(info, dict):
            continue
        if item.get("changed"):
            logger.info("[brapi] %s foi renomeado para %s", item.get("requestedSymbol"), simbolo)
        preco = info.get("regularMarketPrice")
        hora = _hora(info.get("regularMarketTime"))
        if preco is None or hora is None:
            continue
        try:
            valor = Decimal(str(preco))
        except (InvalidOperation, TypeError):
            continue
        if valor <= 0:
            continue  # preco zero ou negativo e dado corrompido, nao cotacao
        cotacoes[simbolo.upper()] = Cotacao(simbolo.upper(), valor, "brapi", hora)
    return cotacoes
