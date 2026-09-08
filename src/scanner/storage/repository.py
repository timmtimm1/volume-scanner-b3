"""Escrita e leitura das barras diarias.

A carga e idempotente: `ON CONFLICT (ticker, trade_date) DO UPDATE`. Recarregar
o mesmo arquivo reescreve os mesmos valores e nao duplica nada. `ingested_at`
NAO e tocado no conflito, para que rodar duas vezes deixe o banco identico.
"""

from __future__ import annotations

import io
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.dialects.postgresql import insert

from scanner.ingest.cotahist import BAR_COLUMNS
from scanner.storage.models import SCHEMA, DailyBar, VolumeMetric

# Colunas reescritas quando a linha ja existe. `ingested_at` fica de fora.
_UPDATABLE = tuple(c for c in BAR_COLUMNS if c not in ("ticker", "trade_date"))


def _to_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame para lista de dicionarios, no formato que o INSERT espera."""
    return [{str(k): v for k, v in row.items()} for row in frame.to_dict(orient="records")]


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Converte o DataFrame para linhas prontas para o INSERT."""
    prepared = frame.loc[:, list(BAR_COLUMNS)].copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"]).dt.date
    prepared["volume_shares"] = prepared["volume_shares"].astype("int64")
    prepared["trades_count"] = prepared["trades_count"].astype("int64")
    prepared["trades_censored"] = prepared["trades_censored"].astype(bool)
    return _to_rows(prepared)


def upsert_bars(engine: Engine, frame: pd.DataFrame, *, chunk_size: int = 5_000) -> int:
    """Grava as barras, sobrescrevendo as que ja existirem. Devolve linhas enviadas."""
    if frame.empty:
        return 0

    rows = _records(frame)
    statement = insert(DailyBar)
    statement = statement.on_conflict_do_update(
        index_elements=["ticker", "trade_date"],
        set_={name: statement.excluded[name] for name in _UPDATABLE},
    )

    with engine.begin() as conn:
        for start in range(0, len(rows), chunk_size):
            conn.execute(statement, rows[start : start + chunk_size])
    return len(rows)


def count_bars(engine: Engine) -> int:
    """Total de barras armazenadas."""
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(DailyBar)).scalar_one())


def stored_range(engine: Engine) -> tuple[date | None, date | None]:
    """Primeiro e ultimo pregao presentes no banco."""
    with engine.connect() as conn:
        row = conn.execute(
            select(func.min(DailyBar.trade_date), func.max(DailyBar.trade_date))
        ).one()
    return row[0], row[1]


def sessions_stored(engine: Engine) -> int:
    """Quantidade de pregoes distintos no banco."""
    with engine.connect() as conn:
        return int(
            conn.execute(select(func.count(func.distinct(DailyBar.trade_date)))).scalar_one()
        )


def load_bars(engine: Engine, *, since: date | None = None) -> pd.DataFrame:
    """Barras completas para o calculo, em formato longo.

    O calculo precisa do historico inteiro mesmo em modo incremental: sem os N
    pregoes anteriores nao ha baseline.
    """
    stmt = select(
        DailyBar.ticker,
        DailyBar.trade_date,
        DailyBar.open,
        DailyBar.high,
        DailyBar.low,
        DailyBar.close,
        DailyBar.avg_price,
        DailyBar.volume_shares,
        DailyBar.volume_financial,
        DailyBar.trades_count,
        DailyBar.trades_censored,
    )
    if since is not None:
        stmt = stmt.where(DailyBar.trade_date >= since)

    with engine.connect() as conn:
        frame = pd.read_sql(stmt, conn)

    for column in ("open", "high", "low", "close", "avg_price", "volume_financial"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
    return frame


def upsert_metrics(engine: Engine, metrics: pd.DataFrame, *, replace_all: bool = False) -> int:
    """Grava os z-scores.

    O payload vai por COPY em bloco unico: `write_row` linha a linha custava
    dezenas de segundos para meio milhao de linhas, e o recalculo full tem de
    caber em 60s.

    `replace_all` troca a tabela inteira -- e o que o modo full faz, e evita
    meio milhao de ON CONFLICT contra linhas que serao todas sobrescritas.
    """
    if metrics.empty:
        return 0

    prepared = metrics.loc[
        :, ["ticker", "trade_date", "window_size", "z_log", "z_raw", "z_robust", "rvol"]
    ].copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"]).dt.date
    prepared["window_size"] = prepared["window_size"].astype("int64")

    payload = io.StringIO()
    # Formato TEXT do COPY: separador tab e \N para nulo.
    prepared.to_csv(payload, sep="\t", header=False, index=False, na_rep="\\N")

    colunas = "ticker, trade_date, window_size, z_log, z_raw, z_robust, rvol"
    atualizaveis = ("z_log", "z_raw", "z_robust", "rvol")
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in atualizaveis)

    with engine.begin() as conn:
        raw = conn.connection.driver_connection
        with raw.cursor() as cur:  # type: ignore[union-attr]
            if replace_all:
                cur.execute(f"TRUNCATE {SCHEMA}.volume_metrics")
                destino = f"{SCHEMA}.volume_metrics"
            else:
                cur.execute(
                    f"CREATE TEMP TABLE tmp_metrics "
                    f"(LIKE {SCHEMA}.volume_metrics INCLUDING DEFAULTS) ON COMMIT DROP"
                )
                destino = "tmp_metrics"

            with cur.copy(f"COPY {destino} ({colunas}) FROM STDIN") as copy:
                copy.write(payload.getvalue())

            if not replace_all:
                cur.execute(
                    f"INSERT INTO {SCHEMA}.volume_metrics ({colunas}) "
                    f"SELECT {colunas} FROM tmp_metrics "
                    f"ON CONFLICT (ticker, trade_date, window_size) DO UPDATE SET {set_clause}"
                )
    return len(prepared)


def count_metrics(engine: Engine) -> int:
    """Total de linhas de metrica armazenadas."""
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(VolumeMetric)).scalar_one())


def last_metric_date(engine: Engine) -> date | None:
    """Ultimo pregao com metrica calculada."""
    with engine.connect() as conn:
        return conn.execute(select(func.max(VolumeMetric.trade_date))).scalar_one()
