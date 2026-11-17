"""Os sinais dos dois setups do estudo de cripto (17/11/2026).

Reversao no RSI (compra, diario) e rompimento de compressao (venda, 4h), com a
entrada na abertura do candle seguinte. Tabela propria, e nao a `setups`: a de
setups e toda feita em torno de "comprar acima da maxima no dia seguinte", e
estes nao tem gatilho, tem timeframe de 4h e tem venda. Existe nos dois schemas
porque as migrations sao as mesmas; so o de cripto tem linhas.

Revision ID: 0026
Revises: 0025
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from scanner import mercado

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = mercado.schema()
PRECO = sa.Numeric(28, 10)


def upgrade() -> None:
    op.create_table(
        "sinais_estudo",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("moeda", sa.Text(), nullable=False),
        sa.Column("setup", sa.Text(), nullable=False),
        sa.Column("timeframe", sa.Text(), nullable=False),
        sa.Column("lado", sa.Text(), nullable=False),
        sa.Column("sinal_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fechamento", PRECO, nullable=False),
        sa.Column("stop", PRECO, nullable=False),
        sa.Column("alvo", PRECO, nullable=False),
        sa.Column("prazo_candles", sa.SmallInteger(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False, server_default="aguardando"),
        sa.Column("entrada", PRECO),
        sa.Column("saida", PRECO),
        sa.Column("saida_em", sa.DateTime(timezone=True)),
        sa.Column("resultado_r", sa.Numeric(10, 4)),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("moeda", "setup", "sinal_em", name="uq_sinais_estudo"),
        sa.CheckConstraint("lado IN ('compra', 'venda')", name="ck_sinais_estudo_lado"),
        sa.CheckConstraint(
            "estado IN ('aguardando', 'aberto', 'alvo', 'stop', 'prazo')",
            name="ck_sinais_estudo_estado",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_sinais_estudo_estado", "sinais_estudo", ["estado"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_sinais_estudo_estado", table_name="sinais_estudo", schema=SCHEMA)
    op.drop_table("sinais_estudo", schema=SCHEMA)
