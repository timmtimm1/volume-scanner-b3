"""Marcacao a mercado dos trades reais (fase 1).

O usuario registra compras e vendas parciais de um papel (fase 2, no site). A
conta da posicao -- preco medio, custo comprado, realizado -- e feita por quem
grava a operacao e fica guardada na propria linha, nas colunas `*_apos`. Este
modulo NAO recalcula media nenhuma: so le o estado da ultima operacao ate cada
pregao e marca a mercado com o fechamento do dia.

Vetorizado por construcao: o produto trades x pregoes e filtrado de uma vez, e
o estado e o fechamento entram por `merge_asof` (o "ultimo valor conhecido ate
aqui", por grupo) -- sem loop por trade nem por ticker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy import Engine

SNAPSHOT_COLUMNS = (
    "trade_id",
    "trade_date",
    "quantidade",
    "preco_medio",
    "custo_comprado",
    "realizado",
    "fechamento",
    "valor_posicao",
    "resultado",
    "sem_negocio",
)


def _sem_snapshots() -> pd.DataFrame:
    return pd.DataFrame(columns=list(SNAPSHOT_COLUMNS))


def marcar_a_mercado(
    trades: pd.DataFrame, operacoes: pd.DataFrame, bars: pd.DataFrame, ate: date
) -> pd.DataFrame:
    """Uma linha por (trade, pregao) marcando a posicao a mercado ate `ate`.

    `trades`: id, ticker, aberto_em, encerrado_em, ultimo_snapshot (as duas
    ultimas podem ser nulas). `operacoes`: id, trade_id, data, quantidade_apos,
    preco_medio_apos, custo_comprado_apos, realizado_apos. `bars`: ticker,
    trade_date, close -- o `contexto.bars` do `scanner daily`, todos os papeis.

    Os pregoes sao as datas distintas de `bars.trade_date`. Para cada trade, as
    datas marcadas sao os pregoes com `aberto_em <= D <= min(encerrado_em ou
    ate, ate)` e `D > ultimo_snapshot` (quando houver) -- assim rodar de novo
    nao regrava o que ja foi gravado. Trade aberto depois de `ate` nao gera
    nada.

    O estado em D e o da ultima operacao do trade com `data <= D`, desempate
    por id (maior id vence em caso de mesma data). Sem nenhuma operacao ate D,
    o trade fica de fora daquele pregao -- nao ha o que marcar.

    O fechamento em D e o close do papel em D; se o papel nao negociou naquele
    dia, entra o ultimo close anterior e `sem_negocio=True`. Sem close nenhum
    ate D (papel ainda nao tinha barra), o trade tambem fica de fora.
    """
    if trades.empty or bars.empty or operacoes.empty:
        # Sem operacao nenhuma, nao ha estado em data alguma: nada a marcar.
        return _sem_snapshots()

    limite = pd.Timestamp(ate)
    pregoes = pd.to_datetime(bars["trade_date"]).drop_duplicates()
    pregoes = pregoes[pregoes <= limite].sort_values()
    if pregoes.empty:
        return _sem_snapshots()

    t = trades.loc[:, ["id", "ticker", "aberto_em", "encerrado_em", "ultimo_snapshot"]].copy()
    t["aberto_em"] = pd.to_datetime(t["aberto_em"])
    t["encerrado_em"] = pd.to_datetime(t["encerrado_em"])
    t["ultimo_snapshot"] = pd.to_datetime(t["ultimo_snapshot"])
    # min(encerrado_em ou ate, ate): fillna cobre o caso aberto, where cobre o
    # caso de encerrado_em vir depois de `ate`. `.clip` nao aceita Timestamp
    # nos stubs do pandas, dai o `where` no lugar.
    fim = t["encerrado_em"].fillna(limite)
    t["fim"] = fim.where(fim <= limite, limite)
    t = t[t["aberto_em"] <= limite]
    if t.empty:
        return _sem_snapshots()

    grade = t.merge(pregoes.rename("trade_date").to_frame(), how="cross")
    grade = grade[
        (grade["trade_date"] >= grade["aberto_em"])
        & (grade["trade_date"] <= grade["fim"])
        & (grade["ultimo_snapshot"].isna() | (grade["trade_date"] > grade["ultimo_snapshot"]))
    ]
    if grade.empty:
        return _sem_snapshots()

    # `merge_asof` exige a coluna `on` globalmente monotona nos dois lados,
    # mesmo com `by` -- nao basta estar ordenada dentro de cada grupo. Por
    # isso a chave primaria de ordenacao e sempre a coluna `on`, nunca `by`.
    grade = (
        grade.rename(columns={"id": "trade_id"})
        .loc[:, ["trade_id", "ticker", "trade_date"]]
        .sort_values(["trade_date", "trade_id"])
        .reset_index(drop=True)
    )

    op_cols = (
        "id",
        "trade_id",
        "data",
        "quantidade_apos",
        "preco_medio_apos",
        "custo_comprado_apos",
        "realizado_apos",
    )
    op = operacoes.reindex(columns=list(op_cols)).copy()
    op["data"] = pd.to_datetime(op["data"])
    # Ordenado por (data, id): em empate de data (dentro do mesmo trade_id),
    # merge_asof pega a ultima linha do grupo -- a de maior id, que e o
    # desempate pedido.
    op = op.sort_values(["data", "id"])

    estado = pd.merge_asof(
        grade,
        op,
        left_on="trade_date",
        right_on="data",
        by="trade_id",
        direction="backward",
    )
    estado = estado.dropna(subset=["quantidade_apos"])
    if estado.empty:
        return _sem_snapshots()

    precos = bars.loc[:, ["ticker", "trade_date", "close"]].dropna(subset=["close"]).copy()
    precos["trade_date"] = pd.to_datetime(precos["trade_date"])
    precos = precos.rename(columns={"trade_date": "data_close", "close": "fechamento"})
    precos = precos.sort_values(["data_close", "ticker"])

    # `estado` ja sai do merge anterior ordenado por trade_date (o `merge_asof`
    # preserva a ordem do lado esquerdo): nao precisa reordenar por ticker.
    marcado = pd.merge_asof(
        estado,
        precos,
        left_on="trade_date",
        right_on="data_close",
        by="ticker",
        direction="backward",
    )
    marcado = marcado.dropna(subset=["fechamento"])
    if marcado.empty:
        return _sem_snapshots()

    quantidade = marcado["quantidade_apos"].astype("int64")
    preco_medio = marcado["preco_medio_apos"].astype(float)
    fechamento = marcado["fechamento"].astype(float)
    realizado = marcado["realizado_apos"].astype(float)

    saida = pd.DataFrame(
        {
            "trade_id": marcado["trade_id"].astype("int64"),
            "trade_date": marcado["trade_date"],
            "quantidade": quantidade,
            "preco_medio": preco_medio,
            "custo_comprado": marcado["custo_comprado_apos"].astype(float),
            "realizado": realizado,
            "fechamento": fechamento,
            "valor_posicao": (quantidade * fechamento).round(2),
            "resultado": (realizado + quantidade * (fechamento - preco_medio)).round(2),
            "sem_negocio": marcado["data_close"] != marcado["trade_date"],
        }
    )
    return saida.loc[:, list(SNAPSHOT_COLUMNS)].reset_index(drop=True)


@dataclass(frozen=True)
class RelatorioSnapshots:
    """O que a marcacao a mercado do pregao fez."""

    trades: int
    snapshots: int
    dry_run: bool
    dia: date

    def summary(self) -> str:
        """Uma linha para o log do `scanner daily`."""
        if self.trades == 0:
            base = "trades: nenhum snapshot novo"
        else:
            verbo = "nao gravados" if self.dry_run else "gravados"
            base = (
                f"trades: {self.trades} marcados a mercado, {self.snapshots} snapshots "
                f"{verbo} ate {self.dia.isoformat()}"
            )
        return f"[dry-run] {base}" if self.dry_run else base


def run_snapshots(
    engine: Engine, dia: date, *, bars: pd.DataFrame, dry_run: bool = False
) -> RelatorioSnapshots:
    """Le os trades e operacoes do banco, marca a mercado e grava os snapshots.

    `bars` e o `contexto.bars` que o `scanner daily` ja calculou -- nao ha
    segunda leitura do banco. Bars vazias (ex.: banco ainda sem carga nenhuma)
    significa que nao ha fechamento para marcar nada, e a funcao nao consulta
    trade nenhum.
    """
    from scanner.storage.repository import (
        gravar_snapshots,
        operacoes_dos_trades,
        trades_para_marcar,
    )

    if bars.empty:
        return RelatorioSnapshots(trades=0, snapshots=0, dry_run=dry_run, dia=dia)

    trades = trades_para_marcar(engine)
    if trades.empty:
        return RelatorioSnapshots(trades=0, snapshots=0, dry_run=dry_run, dia=dia)

    operacoes = operacoes_dos_trades(engine, trades["id"].tolist())
    snapshots = marcar_a_mercado(trades, operacoes, bars, dia)

    if snapshots.empty:
        return RelatorioSnapshots(trades=0, snapshots=0, dry_run=dry_run, dia=dia)

    if not dry_run:
        gravar_snapshots(engine, snapshots)

    return RelatorioSnapshots(
        trades=int(snapshots["trade_id"].nunique()),
        snapshots=len(snapshots),
        dry_run=dry_run,
        dia=dia,
    )
