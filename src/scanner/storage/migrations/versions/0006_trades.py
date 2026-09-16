"""Trades reais (compras e vendas parciais de acoes) e a marcacao a mercado.

Primeira tabela do projeto com chave estrangeira de verdade. As outras tabelas
se ligam por (ticker, trade_date) -- coincidencia de chave natural, nao FK --
porque a poda da secao 5 apaga barras antigas sem se importar com quem
apontava para elas. Aqui e diferente: uma operacao ou um snapshot nao fazem
sentido sem o trade que os contem, entao `trade_id` e FK de verdade, com
ON DELETE CASCADE. Apagar um trade errado apaga tudo dele, de proposito.

A conta da posicao (preco medio, custo, realizado) NAO e feita aqui: quem
grava a operacao (o site, na fase 2) ja calcula o estado e guarda nas colunas
`*_apos` da propria linha. O Python desta fase so le esse estado e marca a
mercado -- nunca recalcula media.

`trade_snapshots` fica FORA da poda de 400 pregoes de `prune_bars`: e a razao
dela existir. Sem o snapshot diario, a marcacao a mercado de um trade antigo
se perderia junto com as barras que a poda ja descartou.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("aberto_em", sa.Date(), nullable=False),
        sa.Column("encerrado_em", sa.Date(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "encerrado_em IS NULL OR encerrado_em >= aberto_em",
            name="ck_trades_encerra_depois_de_abrir",
        ),
        schema=SCHEMA,
    )
    # Parcial, e nao UNIQUE(ticker): varios trades encerrados do mesmo papel
    # convivem no historico. So pode haver um em aberto por vez.
    op.create_index(
        "ux_trades_um_aberto_por_ticker",
        "trades",
        ["ticker"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("encerrado_em IS NULL"),
    )

    op.create_table(
        "trade_operacoes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("trade_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("preco", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("quantidade_apos", sa.Integer(), nullable=False),
        sa.Column("preco_medio_apos", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("custo_comprado_apos", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("realizado_apos", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["trade_id"], [f"{SCHEMA}.trades.id"], ondelete="CASCADE"),
        sa.CheckConstraint("tipo IN ('compra', 'venda')", name="ck_trade_operacoes_tipo"),
        sa.CheckConstraint("quantidade > 0", name="ck_trade_operacoes_quantidade_positiva"),
        sa.CheckConstraint("preco > 0", name="ck_trade_operacoes_preco_positivo"),
        sa.CheckConstraint(
            "quantidade_apos >= 0", name="ck_trade_operacoes_quantidade_apos_nao_negativa"
        ),
        schema=SCHEMA,
    )
    # O estado em qualquer data e "a ultima operacao com data <= D": este e o
    # indice que essa busca usa, por trade.
    op.create_index(
        "ix_trade_operacoes_trade_data",
        "trade_operacoes",
        ["trade_id", "data"],
        schema=SCHEMA,
    )

    op.create_table(
        "trade_snapshots",
        sa.Column("trade_id", sa.BigInteger(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("preco_medio", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("custo_comprado", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("realizado", sa.Numeric(precision=16, scale=2), nullable=False),
        # Mesma precisao de daily_bars.close: e de onde este valor vem.
        sa.Column("fechamento", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("valor_posicao", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("resultado", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("sem_negocio", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "gravado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("trade_id", "trade_date"),
        sa.ForeignKeyConstraint(["trade_id"], [f"{SCHEMA}.trades.id"], ondelete="CASCADE"),
        sa.CheckConstraint("quantidade >= 0", name="ck_trade_snapshots_quantidade_nao_negativa"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("trade_snapshots", schema=SCHEMA)
    op.drop_index("ix_trade_operacoes_trade_data", table_name="trade_operacoes", schema=SCHEMA)
    op.drop_table("trade_operacoes", schema=SCHEMA)
    op.drop_index("ux_trades_um_aberto_por_ticker", table_name="trades", schema=SCHEMA)
    op.drop_table("trades", schema=SCHEMA)
