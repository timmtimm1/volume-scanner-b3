"""Carimbo de envio do resumo diario.

O resumo nao tinha dedupe: `run_resumo` mandava a cada execucao, enquanto o
alerta ja se protegia com `events.notified_at`. Uma linha por pregao enviado
fecha isso.

A chave primaria e o proprio `trade_date`: o resumo e um por pregao, e deixar o
banco recusar a segunda linha e mais barato do que confiar que ninguem vai
chamar duas vezes.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    op.create_table(
        "digest_sends",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("trade_date"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("digest_sends", schema=SCHEMA)
