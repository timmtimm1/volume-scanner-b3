"""Tabela das criptomoedas acompanhadas (aba Cripto, 16/11/2026).

Nome, par na Binance e posicao no ranking de cada moeda. Existe nos dois
schemas porque as migrations sao as mesmas; so o de cripto tem linhas.

Revision ID: 0023
Revises: 0022
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from scanner import mercado

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = mercado.schema()


def upgrade() -> None:
    op.create_table(
        "moedas",
        sa.Column("ticker", sa.Text(), primary_key=True),
        sa.Column("par", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("posicao", sa.SmallInteger()),
        sa.Column("valor_de_mercado", sa.Numeric(24, 2)),
        sa.Column("no_top", sa.Boolean(), nullable=False),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("moedas", schema=SCHEMA)
