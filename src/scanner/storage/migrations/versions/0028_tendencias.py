"""Tendencia de cada ativo pela inclinacao das medias moveis (17/11/2026).

Pedido do usuario: escolher, no scanner e na aba Cripto, os ativos em alta,
baixa ou lateral pela direcao das medias. O pipeline grava, para o ultimo
pregao, se cada media (MME e MMA de 9, 20, 50, 80 e 200) esta subindo (+1),
caindo (-1) ou sem historico (0); o site combina as que o usuario escolher.
Uma linha por ativo, trocada a cada noite: nao ha historico a guardar.

Existe nos dois schemas porque as migrations sao as mesmas.

Revision ID: 0028
Revises: 0027
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from scanner import mercado

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = mercado.schema()
MEDIAS = ("mme9", "mme20", "mme50", "mme80", "mme200", "mma9", "mma20", "mma50", "mma80", "mma200")


def upgrade() -> None:
    op.create_table(
        "tendencias",
        sa.Column("ticker", sa.Text(), primary_key=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("fechamento", sa.Numeric(28, 10), nullable=False),
        sa.Column("variacao", sa.Float()),
        sa.Column("volume_mediano", sa.Float()),
        sa.Column("liquido", sa.Boolean(), nullable=False),
        *(sa.Column(m, sa.SmallInteger(), nullable=False) for m in MEDIAS),
        sa.Column(
            "gravado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("tendencias", schema=SCHEMA)
