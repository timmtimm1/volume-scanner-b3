"""Yields do Tesouro americano (Daily Treasury Par Yield Curve Rates).

O CSV traz um ano por arquivo, a data mais nova primeiro, colunas por
vencimento ("3 Mo", "2 Yr", "10 Yr"...). Dia sem pregao nos EUA simplesmente
nao tem linha, entao "fim" e "base" sao sempre o ultimo dia COM linha ate o
limite. Numa semana de janeiro a base cai em dezembro, no arquivo do ano
anterior: o arquivo anterior so e baixado quando precisa.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from typing import Any

import httpx
import pandas as pd

from scanner.semana.fontes import FonteIndisponivelError, baixar
from scanner.semana.periodo import Semana

FONTE = "treasury"
URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{ano}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={ano}&page&_format=csv"
)
DEFASAGEM_MAXIMA_DIAS = 7


def ler_csv(texto: str) -> pd.DataFrame:
    """Tabela com indice = data e uma coluna de taxa (% a.a.) por vencimento."""
    leitor = csv.reader(io.StringIO(texto.lstrip("﻿")))
    linhas = list(leitor)
    if not linhas or not linhas[0] or linhas[0][0].strip() != "Date":
        raise FonteIndisponivelError(FONTE, "cabecalho ausente (1a coluna nao e 'Date')")
    cabecalho = [c.strip() for c in linhas[0]]

    datas: list[date] = []
    valores: list[list[float]] = []
    for linha in linhas[1:]:
        if not linha or not linha[0].strip():
            continue
        try:
            datas.append(datetime.strptime(linha[0].strip(), "%m/%d/%Y").date())
            valores.append([float(c) if c.strip() else float("nan") for c in linha[1:]])
        except ValueError as exc:
            raise FonteIndisponivelError(FONTE, f"linha ilegivel: {linha[:3]!r}") from exc
    if not datas:
        raise FonteIndisponivelError(FONTE, "csv sem nenhuma linha de dados")
    tabela = pd.DataFrame(valores, index=pd.to_datetime(datas), columns=cabecalho[1:])
    return tabela.sort_index()


def _ultima_linha_ate(tabela: pd.DataFrame, limite: date) -> tuple[date, pd.Series] | None:
    ate = tabela.loc[: pd.Timestamp(limite)]
    if ate.empty:
        return None
    return ate.index[-1].date(), ate.iloc[-1]


def montar_treasuries(tabela: pd.DataFrame, semana: Semana, prazos: list[str]) -> dict[str, Any]:
    """Yield de cada prazo na sexta e a variacao em pontos-base contra o fim da semana anterior."""
    ultima = _ultima_linha_ate(tabela, semana.sexta)
    anterior_ = _ultima_linha_ate(tabela, semana.segunda - timedelta(days=1))
    if ultima is None:
        raise FonteIndisponivelError(FONTE, "sem linha ate a sexta da semana")
    if anterior_ is None:
        raise FonteIndisponivelError(FONTE, "sem linha antes da segunda da semana")
    (data_fim, fim), (data_base, base) = ultima, anterior_
    if (semana.sexta - data_fim).days > DEFASAGEM_MAXIMA_DIAS:
        raise FonteIndisponivelError(FONTE, f"ultima linha e de {data_fim}, velha demais")

    vencimentos: list[dict[str, Any]] = []
    for prazo in prazos:
        if prazo not in tabela.columns:
            raise FonteIndisponivelError(FONTE, f"vencimento {prazo!r} nao existe no csv")
        taxa, anterior = float(fim[prazo]), float(base[prazo])
        if pd.isna(taxa) or pd.isna(anterior):
            raise FonteIndisponivelError(FONTE, f"vencimento {prazo!r} sem valor em {data_fim}")
        vencimentos.append(
            {
                "prazo": prazo,
                "taxa": taxa,
                "taxa_anterior": anterior,
                "variacao_bp": (taxa - anterior) * 100,
            }
        )
    return {
        "data": data_fim.isoformat(),
        "data_anterior": data_base.isoformat(),
        "vencimentos": vencimentos,
    }


def _baixar_ano(ano: int, cliente: httpx.Client | None) -> pd.DataFrame:
    resposta = baixar(FONTE, URL.format(ano=ano), cliente=cliente)
    return ler_csv(resposta.text)


def treasuries(
    semana: Semana, prazos: list[str], *, cliente: httpx.Client | None = None
) -> dict[str, Any]:
    """Baixa o ano da sexta (e o anterior, se a base cair la) e monta o bloco."""
    tabela = _baixar_ano(semana.sexta.year, cliente)
    limite_base = semana.segunda - timedelta(days=1)
    if tabela.index.min() > pd.Timestamp(limite_base):
        tabela = pd.concat([_baixar_ano(semana.sexta.year - 1, cliente), tabela]).sort_index()
    return montar_treasuries(tabela, semana, prazos)
