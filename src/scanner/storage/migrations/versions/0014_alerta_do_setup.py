"""Alerta de rompimento criado pelo setup, com validade.

Cada setup armado ganha um alerta "acima da maxima do candle", criado pelo
pipeline na noite do candle. Ele so vale no pregao seguinte: e ali que o setup
confirma ou nao. Dai as duas colunas:

- `expira_em`: ultimo pregao em que o alerta vale. Nulo = sem validade, que e
  o caso de todo alerta criado a mao. Depois dessa data o alerta nao e mais
  consultado nem aparece como "vigiando", mesmo sem ter disparado.
- `setup_id`: o setup que criou o alerta. Nulo nos alertas manuais. Apagar o
  setup apaga o alerta junto.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    op.add_column("price_alerts", sa.Column("expira_em", sa.Date()), schema=SCHEMA)
    op.add_column(
        "price_alerts",
        sa.Column(
            "setup_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.setups.id", ondelete="CASCADE"),
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ux_price_alerts_setup", "price_alerts", ["setup_id"], unique=True, schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ux_price_alerts_setup", table_name="price_alerts", schema=SCHEMA)
    op.drop_column("price_alerts", "setup_id", schema=SCHEMA)
    op.drop_column("price_alerts", "expira_em", schema=SCHEMA)
