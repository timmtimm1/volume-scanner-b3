"""Selic, CDI e IPCA pelo SGS do Banco Central.

Unidades, como o SGS publica: `selic_meta` em % a.a. e `ipca_12m` em %; o CDI
acumulado sai em FRACAO (0,1136 = 11,36%), pelo produto das taxas diarias.

O CDI de um dia so aparece no SGS no dia util seguinte: medido em 17/10/2026, a
serie pedida ate 16/10 acabava em 15/10. Por isso o bloco devolve `cdi_data`,
a ultima data que entrou na conta, em vez de fingir que vai ate a sexta.
"""

from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from scanner.semana.fontes import FonteIndisponivelError, baixar
from scanner.semana.periodo import Semana

FONTE = "bcb"
URL = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"
    "?formato=json&dataInicial={de}&dataFinal={ate}"
)
SELIC_META = 432
CDI_DIARIO = 12
IPCA_12M = 13522
# O SGS responde 502 de vez em quando e acerta na tentativa seguinte (medido
# em 17/10/2026: uma em quatro chamadas seguidas da serie 432).
ESPERA_APOS_5XX = 2.0


def ler_sgs(dados: Any) -> list[tuple[date, float]]:
    """[(data, valor)] de uma resposta do SGS, em ordem de data."""
    if not isinstance(dados, list):
        raise FonteIndisponivelError(FONTE, "formato inesperado (resposta nao e lista)")
    pontos: list[tuple[date, float]] = []
    for item in dados:
        try:
            pontos.append(
                (datetime.strptime(item["data"], "%d/%m/%Y").date(), float(item["valor"]))
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FonteIndisponivelError(FONTE, f"ponto ilegivel: {item!r}") from exc
    return sorted(pontos)


def acumulado(pontos: list[tuple[date, float]]) -> float | None:
    """Produto de (1 + v/100) - 1 sobre taxas diarias em %. None sem pontos."""
    if not pontos:
        return None
    return math.prod(1 + valor / 100 for _, valor in pontos) - 1


def montar_indicadores(
    fim: date,
    selic: list[tuple[date, float]],
    cdi_mes: list[tuple[date, float]],
    cdi_ano: list[tuple[date, float]],
    ipca: list[tuple[date, float]],
) -> dict[str, Any]:
    """Aplica as regras de data: tudo ate `fim`, o ultimo valor valendo para Selic e IPCA."""
    selic_ate = [p for p in selic if p[0] <= fim]
    ipca_ate = [p for p in ipca if p[0] <= fim]
    if not selic_ate:
        raise FonteIndisponivelError(FONTE, "Selic meta sem valor ate o fim da semana")
    if not ipca_ate:
        raise FonteIndisponivelError(FONTE, "IPCA 12 meses sem valor ate o fim da semana")
    cdi_ano_ate = [p for p in cdi_ano if p[0] <= fim]
    cdi_mes_ate = [p for p in cdi_mes if p[0] <= fim]
    referencia, ipca_valor = ipca_ate[-1]
    return {
        "selic_meta": selic_ate[-1][1],
        "cdi_mes": acumulado(cdi_mes_ate),
        "cdi_ano": acumulado(cdi_ano_ate),
        "cdi_data": cdi_ano_ate[-1][0].isoformat() if cdi_ano_ate else None,
        "ipca_12m": ipca_valor,
        "ipca_referencia": referencia.strftime("%Y-%m"),
    }


def _serie(
    numero: int, de: date, ate: date, cliente: httpx.Client | None
) -> list[tuple[date, float]]:
    url = URL.format(serie=numero, de=de.strftime("%d/%m/%Y"), ate=ate.strftime("%d/%m/%Y"))
    try:
        try:
            resposta = baixar(FONTE, url, cliente=cliente)
        except FonteIndisponivelError as exc:
            if exc.status is None or exc.status < 500:
                raise
            time.sleep(ESPERA_APOS_5XX)
            resposta = baixar(FONTE, url, cliente=cliente)
    except FonteIndisponivelError as exc:
        # Periodo sem dado volta 404 com {"erro": ...}: e "nao ha pontos", nao falha.
        if exc.status == 404:
            return []
        raise
    try:
        return ler_sgs(resposta.json())
    except ValueError as exc:
        raise FonteIndisponivelError(FONTE, "resposta nao e JSON") from exc


def indicadores(semana: Semana, *, cliente: httpx.Client | None = None) -> dict[str, Any]:
    """Selic meta, CDI no mes e no ano, e IPCA em 12 meses ate o fim da semana."""
    fim = semana.fim
    return montar_indicadores(
        fim,
        _serie(SELIC_META, fim - timedelta(days=30), fim, cliente),
        _serie(CDI_DIARIO, date(fim.year, fim.month, 1), fim, cliente),
        _serie(CDI_DIARIO, date(fim.year, 1, 1), fim, cliente),
        _serie(IPCA_12M, fim - timedelta(days=400), fim, cliente),
    )
