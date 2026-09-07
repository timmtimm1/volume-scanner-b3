"""Escrita e leitura das barras diarias.

A carga e idempotente: `ON CONFLICT (ticker, trade_date) DO UPDATE`. Recarregar
o mesmo arquivo reescreve os mesmos valores e nao duplica nada. `ingested_at`
NAO e tocado no conflito, para que rodar duas vezes deixe o banco identico.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.dialects.postgresql import insert

from scanner.ingest.cotahist import BAR_COLUMNS
from scanner.storage.models import DailyBar

# Colunas reescritas quando a linha ja existe. `ingested_at` fica de fora.
_UPDATABLE = tuple(c for c in BAR_COLUMNS if c not in ("ticker", "trade_date"))


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    """Converte o DataFrame para linhas prontas para o INSERT."""
    prepared = frame.loc[:, list(BAR_COLUMNS)].copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"]).dt.date
    prepared["volume_shares"] = prepared["volume_shares"].astype("int64")
    prepared["trades_count"] = prepared["trades_count"].astype("int64")
    prepared["trades_censored"] = prepared["trades_censored"].astype(bool)
    return prepared.to_dict(orient="records")  # type: ignore[return-value]


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
