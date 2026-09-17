"""Fundamentos fase 2: proventos em dinheiro, por papel.

O dividend yield da ficha e por classe, e nao por empresa: em 05/12/2025 a
Unipar pagou R$ 5,48 por acao ON e R$ 6,03 por acao PN. Por isso `proventos`
guarda uma linha por papel, e nao por empresa.

Quem liga um provento ao papel certo e o ISIN, que a B3 declara tanto no
cadastro do papel quanto em cada provento recente. As colunas `isin` e
`classe` entram em `empresa_tickers` para isso. `emissor_b3` e `nome_pregao`
entram em `empresas` porque sao as chaves que as duas consultas de proventos
da B3 exigem -- e vem do detalhe da propria B3, nunca deduzidas do ticker.

As colunas `*_em` guardam quando cada consulta foi feita. O detalhe e o
historico mudam pouco e sao refeitos por semana; os proventos recentes, todo
dia. Sem elas, cada execucao repetiria as tres perguntas para 321 empresas.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"

_COLUNAS_EMPRESA = (
    ("emissor_b3", sa.Text()),
    ("nome_pregao", sa.Text()),
    ("detalhe_em", sa.DateTime(timezone=True)),
    ("proventos_em", sa.DateTime(timezone=True)),
    ("historico_em", sa.DateTime(timezone=True)),
)

_COLUNAS_TICKER = (("isin", sa.Text()), ("classe", sa.Text()))


def upgrade() -> None:
    for nome, tipo in _COLUNAS_EMPRESA:
        op.add_column("empresas", sa.Column(nome, tipo, nullable=True), schema=SCHEMA)
    for nome, tipo in _COLUNAS_TICKER:
        op.add_column("empresa_tickers", sa.Column(nome, tipo, nullable=True), schema=SCHEMA)

    op.create_table(
        "proventos",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        # Onze casas: e a precisao com que a B3 publica o valor por acao.
        sa.Column("valor", sa.Numeric(precision=20, scale=11), nullable=False),
        sa.Column("data_com", sa.Date(), nullable=False),
        sa.Column("data_aprovacao", sa.Date(), nullable=True),
        sa.Column("data_pagamento", sa.Date(), nullable=True),
        sa.Column("fonte", sa.Text(), nullable=False),
        sa.Column(
            "carregado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["ticker"], [f"{SCHEMA}.empresa_tickers.ticker"], ondelete="CASCADE"
        ),
        sa.CheckConstraint("valor > 0", name="ck_proventos_valor_positivo"),
        sa.CheckConstraint("fonte IN ('recente', 'historico')", name="ck_proventos_fonte"),
        schema=SCHEMA,
    )
    # A consulta da ficha e sempre "os proventos deste papel nos 12 meses ate
    # uma data": ticker primeiro, data depois.
    op.create_index("ix_proventos_ticker_data", "proventos", ["ticker", "data_com"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_proventos_ticker_data", table_name="proventos", schema=SCHEMA)
    op.drop_table("proventos", schema=SCHEMA)
    for nome, _ in _COLUNAS_TICKER:
        op.drop_column("empresa_tickers", nome, schema=SCHEMA)
    for nome, _ in _COLUNAS_EMPRESA:
        op.drop_column("empresas", nome, schema=SCHEMA)
