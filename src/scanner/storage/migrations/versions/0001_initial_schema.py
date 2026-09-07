"""Schema inicial: daily_bars, volume_metrics, events (secao 8 do plano).

Revision ID: 0001
Revises:
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')

    op.create_table(
        "daily_bars",
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(18, 4), nullable=True),
        sa.Column("high", sa.Numeric(18, 4), nullable=True),
        sa.Column("low", sa.Numeric(18, 4), nullable=True),
        sa.Column("close", sa.Numeric(18, 4), nullable=False),
        sa.Column("avg_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("volume_shares", sa.BigInteger(), nullable=True),
        sa.Column("volume_financial", sa.Numeric(20, 2), nullable=False),
        sa.Column("trades_count", sa.Integer(), nullable=True),
        sa.Column("trades_censored", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("ticker", "trade_date"),
        schema=SCHEMA,
    )
    op.create_index("ix_daily_bars_trade_date", "daily_bars", ["trade_date"], schema=SCHEMA)

    op.create_table(
        "volume_metrics",
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("window_size", sa.SmallInteger(), nullable=False),
        sa.Column("z_log", sa.Numeric(10, 4), nullable=True),
        sa.Column("z_raw", sa.Numeric(10, 4), nullable=True),
        sa.Column("z_robust", sa.Numeric(10, 4), nullable=True),
        sa.Column("rvol", sa.Numeric(10, 4), nullable=True),
        sa.PrimaryKeyConstraint("ticker", "trade_date", "window_size"),
        schema=SCHEMA,
    )

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("max_z_log", sa.Numeric(10, 4), nullable=False),
        sa.Column("triggered_windows", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("volume_financial", sa.Numeric(20, 2), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "trade_date", name="uq_events_ticker_date"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("events", schema=SCHEMA)
    op.drop_table("volume_metrics", schema=SCHEMA)
    op.drop_index("ix_daily_bars_trade_date", table_name="daily_bars", schema=SCHEMA)
    op.drop_table("daily_bars", schema=SCHEMA)
