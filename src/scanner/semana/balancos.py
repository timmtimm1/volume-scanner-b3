"""Balancos da semana seguinte: os confirmados (Nasdaq) e os provaveis (CVM).

CONFIRMADOS: so empresa com ADR (tabela escrita a mao em `adrs.py`), e so a data
que a propria empresa anunciou. A Nasdaq tambem devolve datas ESTIMADAS por
algoritmo; essas ficam de fora, porque "estimada" nao e "confirmada".

PROVAVEIS: o historico da CVM. Quem entregou o ITR/DFP do ano passado nos mesmos
dias da semana (364 dias antes, para cair na mesma segunda a sexta) tende a
entregar de novo. E so uma tendencia, e a saida diz isso com o documento e a data
do ano passado, sem prometer data.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any, NamedTuple

import httpx
import numpy as np
import pandas as pd
from sqlalchemy import Engine

from scanner.semana.adrs import ADRS
from scanner.semana.fontes import FonteIndisponivelError, nasdaq
from scanner.storage import repository

logger = logging.getLogger(__name__)

# Pausa entre ADRs: a Nasdaq nao documenta limite; 19 chamadas seguidas com 0,5 s
# de folga passaram em 17/10/2026.
PAUSA_NASDAQ = 0.5
UM_ANO_EM_DIAS = 364  # 52 semanas: mesmos dias da semana um ano antes


def _tickers(valor: Any) -> list[str]:
    return [str(t) for t in valor]


class Confirmados(NamedTuple):
    lista: list[dict[str, Any]]  # os balancos anunciados para a semana
    avisos: list[str]  # ADRs que a Nasdaq nao respondeu
    # Empresas com data anunciada em QUALQUER semana. Quem anunciou o balanco
    # para outra semana nao e "provavel" nesta, mesmo tendo entregue nesta
    # semana no ano passado: o anuncio vale mais que o historico.
    anunciadas: frozenset[int]


def confirmados(
    inicio: date,
    fim: date,
    empresas: pd.DataFrame,
    *,
    cliente: httpx.Client | None = None,
    pausa: float = PAUSA_NASDAQ,
) -> Confirmados:
    """Os balancos anunciados para a semana, os avisos e quem anunciou para qualquer data.

    `empresas` e o resultado de `repository.papeis_por_empresa`: so empresa com
    papel no universo entra, as demais nao interessam ao scanner.
    """
    por_cvm = empresas.set_index("cd_cvm") if not empresas.empty else empresas
    achados: list[dict[str, Any]] = []
    avisos: list[str] = []
    anunciadas: set[int] = set()
    for i, (adr, info) in enumerate(ADRS.items()):
        if i:
            time.sleep(pausa)
        try:
            resultado = nasdaq.data_do_adr(adr, cliente=cliente)
        except FonteIndisponivelError as exc:
            logger.warning("[semana] nasdaq %s: %s", adr, exc)
            avisos.append(f"Nasdaq sem resposta para {adr} ({info.empresa}): {exc.motivo}")
            continue
        if resultado is None:
            continue
        anunciadas.add(info.cd_cvm)
        if not inicio <= resultado.data <= fim:
            continue
        if info.cd_cvm not in por_cvm.index:
            continue
        linha = por_cvm.loc[info.cd_cvm]
        achados.append(
            {
                "empresa": str(linha["empresa"]),
                "cd_cvm": info.cd_cvm,
                "tickers": _tickers(linha["tickers"]),
                "data": resultado.data.isoformat(),
                "horario": resultado.horario,
                "trimestre": resultado.trimestre,
                "fonte": "Nasdaq",
            }
        )
    achados.sort(key=lambda b: (b["data"], b["empresa"]))
    return Confirmados(achados, avisos, frozenset(anunciadas))


def provaveis(
    engine: Engine,
    universo: list[str],
    inicio: date,
    fim: date,
    fim_da_semana: date,
    ja_confirmados: set[int],
) -> list[dict[str, Any]]:
    """Empresas que entregaram nesta semana do ano passado e ainda nao entregaram este ano."""
    frame = repository.balancos_do_ano_anterior(
        engine,
        universo,
        inicio - timedelta(days=UM_ANO_EM_DIAS),
        fim - timedelta(days=UM_ANO_EM_DIAS),
        fim_da_semana,
    )
    frame = frame[~frame["cd_cvm"].isin(ja_confirmados)]
    if frame.empty:
        return []
    tipo = frame["tipo"].astype(str)
    dt = pd.to_datetime(frame["dt_refer"])
    trimestre = ((dt.dt.month - 1) // 3 + 1).astype(str)
    documento = pd.Series(
        np.where(
            tipo == "DFP",
            "DFP " + dt.dt.year.astype(str),
            tipo + " " + trimestre + "T" + (dt.dt.year % 100).astype(str).str.zfill(2),
        ),
        index=frame.index,
    )
    saida = pd.DataFrame(
        {
            "empresa": frame["empresa"].astype(str),
            "cd_cvm": frame["cd_cvm"].astype(int),
            "tickers": frame["tickers"].map(_tickers),
            "documento": documento,
            "entregue_em": pd.to_datetime(frame["entregue_em"]).dt.strftime("%Y-%m-%d"),
        }
    ).sort_values(["entregue_em", "empresa"])
    registros: list[dict[str, Any]] = saida.to_dict(orient="records")  # type: ignore[assignment]
    return registros


def montar_balancos(
    engine: Engine,
    universo: list[str],
    inicio: date,
    fim: date,
    fim_da_semana: date,
    *,
    cliente: httpx.Client | None = None,
    pausa: float = PAUSA_NASDAQ,
) -> dict[str, Any]:
    """{"confirmados", "provaveis", "avisos"} da semana [inicio, fim]."""
    empresas = repository.papeis_por_empresa(engine, universo)
    conf = confirmados(inicio, fim, empresas, cliente=cliente, pausa=pausa)
    return {
        "confirmados": conf.lista,
        "provaveis": provaveis(engine, universo, inicio, fim, fim_da_semana, set(conf.anunciadas)),
        "avisos": conf.avisos,
    }
