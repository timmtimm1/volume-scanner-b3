"""Alertas de rompimento de preco.

Nao faz parte da secao 8 do plano: e a primeira tabela que guarda uma decisao
do usuario, e nao dado derivado do COTAHIST. O scanner detecta e apresenta; o
alerta e o usuario dizendo "me avise quando este papel chegar aqui".

O CHECK em `direcao` existe porque a coluna e Text e nao enum: um valor errado
gravado ali nao daria erro, so faria o alerta nunca disparar -- falha silenciosa,
que e a pior especie num sistema cujo proposito e avisar.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("preco", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("direcao", sa.Text(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("disparado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preco_disparo", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("fonte_disparo", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("direcao IN ('acima', 'abaixo')", name="ck_price_alerts_direcao"),
        sa.CheckConstraint("preco > 0", name="ck_price_alerts_preco_positivo"),
        schema=SCHEMA,
    )
    # O job de 15 em 15 minutos pergunta sempre a mesma coisa: quais estao
    # ativos? `disparado_em IS NULL` e o filtro quente.
    op.create_index(
        "ix_price_alerts_ativo",
        "price_alerts",
        ["disparado_em"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_price_alerts_ativo", table_name="price_alerts", schema=SCHEMA)
    op.drop_table("price_alerts", schema=SCHEMA)
