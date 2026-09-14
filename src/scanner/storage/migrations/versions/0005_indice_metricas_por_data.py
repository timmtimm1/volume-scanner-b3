"""Indice em volume_metrics(trade_date).

A chave primaria e (ticker, trade_date, window_size): comeca por `ticker`, e
consulta filtrando so por data -- como a do site que acha o ultimo pregao --
lia a tabela inteira. Medido no banco local com 534 mil linhas: 344 ms de
leitura sequencial. `daily_bars` e `daily_features` ja tinham o indice.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    op.create_index("ix_volume_metrics_trade_date", "volume_metrics", ["trade_date"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_volume_metrics_trade_date", table_name="volume_metrics", schema=SCHEMA)
