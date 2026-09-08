"""Tabela daily_features: contexto da secao 3.2 para todo pregao avaliado.

A secao 8 do plano guarda as features so dentro de `events`, que recebe linha
apenas quando o papel cruza o limiar. Isso basta para o alerta do Telegram, mas
deixa sem contexto tudo que fica abaixo do limiar -- e a tela do scanner mostra
uma faixa maior de propósito, para o filtro de z ter onde passear.

Recalcular esse contexto no build do site duplicaria a matematica da secao 3.2
em Python e em SQL, e uma das duas envelheceria errado. Persistir e mais barato:
sao ~300 linhas por pregao.

`events.features` continua existindo e continua sendo a verdade do que foi
notificado -- esta tabela nao a substitui.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    op.create_table(
        "daily_features",
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("ticker", "trade_date"),
        schema=SCHEMA,
    )
    op.create_index("ix_daily_features_trade_date", "daily_features", ["trade_date"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_daily_features_trade_date", table_name="daily_features", schema=SCHEMA)
    op.drop_table("daily_features", schema=SCHEMA)
