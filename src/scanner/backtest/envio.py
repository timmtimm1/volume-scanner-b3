"""O resultado da suite vai para o banco, numa rodada (migration 0016).

A suite roda na maquina (`scripts/backtest_setups.py processar` e `relatorio`);
aqui so o resultado sobe: a grade, a escolha de cada setup, o ano a ano, a curva
e uma AMOSTRA de trades -- os `AMOSTRA` mais recentes de cada setup e saida. Os
1,4 milhao de trades nao cabem no Neon gratis e o site nao precisa deles.

Tudo numa transacao: ou a rodada entra inteira, ou nao entra. O site le a
rodada de maior id. Ficam as `MANTER` ultimas; as mais antigas sao apagadas
(as tabelas filhas vao junto, por cascade).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine, delete, insert, select
from sqlalchemy.orm import Session

from scanner.backtest.metricas import fechados
from scanner.backtest.simulador import MOTIVOS
from scanner.storage.models import (
    BacktestAno,
    BacktestCurva,
    BacktestEscolha,
    BacktestResultado,
    BacktestRodada,
    BacktestTrade,
)

AMOSTRA = 200
MANTER = 2
LOTE_DE_INSERT = 5_000

COLUNAS_RESULTADO = tuple(
    c.name for c in BacktestResultado.__table__.columns if c.name != "rodada_id"
)
COLUNAS_ESCOLHA = tuple(c.name for c in BacktestEscolha.__table__.columns if c.name != "rodada_id")


def _limpo(v: Any) -> Any:
    """NaN e NaT viram NULL; tipos do numpy viram tipos do Python."""
    if v is None:
        return None
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.date()
    if isinstance(v, np.datetime64):
        return None if np.isnat(v) else pd.Timestamp(v).date()
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if not np.isfinite(v) else float(v)
    return v


def _linhas(frame: pd.DataFrame, colunas: Sequence[str]) -> list[dict[str, Any]]:
    parte = frame.reindex(columns=list(colunas))
    return [
        {c: _limpo(v) for c, v in zip(colunas, linha, strict=True)}
        for linha in parte.itertuples(index=False, name=None)
    ]


def amostra_de_trades(trades: pd.DataFrame, por_combinacao: int = AMOSTRA) -> pd.DataFrame:
    """Os trades mais recentes (pela entrada) de cada setup e saida, prontos para a tabela."""
    if trades.empty:
        return pd.DataFrame(columns=[c.name for c in BacktestTrade.__table__.columns])
    t = trades.sort_values("data_entrada", ascending=False)
    t = t.groupby(["setup", "saida"], observed=True, sort=False).head(por_combinacao)
    aberto = t["motivo"] == 0
    with np.errstate(invalid="ignore"):
        saida = t["entrada"] + t["r_bruto"] * (t["entrada"] - t["stop"])
    return pd.DataFrame(
        {
            "setup": t["setup"].astype(str),
            "saida": t["saida"].astype(str),
            "ticker": t["ticker"].astype(str),
            "data_sinal": t["data_sinal"],
            "data_entrada": t["data_entrada"],
            "data_saida": t["data_saida"].where(~aberto),
            "entrada": t["entrada"].astype(np.float64).round(4),
            "stop": t["stop"].astype(np.float64).round(4),
            "preco_saida": saida.astype(np.float64).round(4).where(~aberto),
            "motivo": t["motivo"].map(MOTIVOS),
            "dias": t["dias"].where(~aberto),
            "r": t["r"].astype(np.float64).where(~aberto),
            "r_controle": t["r_controle"].astype(np.float64).where(~aberto),
            "alta": t["alta"].astype(bool),
            "rvol": t["rvol"].astype(np.float64),
        }
    ).reset_index(drop=True)


def resumo_da_rodada(trades: pd.DataFrame, custo: float, teto: int) -> dict[str, Any]:
    """Os campos de `backtest_rodadas` tirados dos proprios trades."""
    return {
        "dados_de": pd.Timestamp(trades["data_sinal"].min()).date(),
        "dados_ate": pd.Timestamp(trades["data_entrada"].max()).date(),
        "custo": float(custo),
        "teto": int(teto),
        "trades": len(fechados(trades)),
        "papeis": int(trades["ticker"].nunique()),
    }


def _inserir(s: Session, tabela: Any, linhas: list[dict[str, Any]], rodada_id: int) -> None:
    for ini in range(0, len(linhas), LOTE_DE_INSERT):
        bloco = [linha | {"rodada_id": rodada_id} for linha in linhas[ini : ini + LOTE_DE_INSERT]]
        if bloco:
            s.execute(insert(tabela), bloco)


def enviar(
    engine: Engine,
    *,
    rodada: dict[str, Any],
    grade: pd.DataFrame,
    escolha: pd.DataFrame,
    anos: pd.DataFrame,
    curva: pd.DataFrame,
    amostra: pd.DataFrame,
    manter: int = MANTER,
) -> int:
    """Grava uma rodada inteira numa transacao e devolve o id dela."""
    curva = curva.assign(mes=pd.to_datetime(curva["mes"]).dt.date)
    linhas = {
        BacktestResultado: _linhas(grade, COLUNAS_RESULTADO),
        BacktestEscolha: _linhas(escolha, COLUNAS_ESCOLHA),
        BacktestAno: _linhas(
            anos, ("setup", "saida", "grupo", "ano", "n", "expectativa", "soma_r", "controle")
        ),
        BacktestCurva: _linhas(
            curva,
            (
                "setup",
                "saida",
                "grupo",
                "mes",
                "n",
                "r",
                "controle",
                "acumulado",
                "controle_acumulado",
                "recuo",
            ),
        ),
        BacktestTrade: _linhas(
            amostra,
            [c.name for c in BacktestTrade.__table__.columns if c.name not in ("id", "rodada_id")],
        ),
    }
    with Session(engine) as s, s.begin():
        rodada_id = int(
            s.execute(
                insert(BacktestRodada).values(**rodada).returning(BacktestRodada.id)
            ).scalar_one()
        )
        for modelo, ls in linhas.items():
            _inserir(s, modelo.__table__, ls, rodada_id)
        ids = (
            s.execute(select(BacktestRodada.id).order_by(BacktestRodada.id.desc())).scalars().all()
        )
        velhas = [int(i) for i in ids[manter:]]
        if velhas:
            s.execute(delete(BacktestRodada).where(BacktestRodada.id.in_(velhas)))
    return rodada_id
