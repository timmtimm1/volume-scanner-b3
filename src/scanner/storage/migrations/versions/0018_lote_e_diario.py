"""Calculadora de lote e diario ligado ao setup (secao 14 do plano, fase 4).

Decisoes do usuario em 05/11/2026:

- `perfil_de_risco`: o capital e o risco por trade (padrao 1%), salvos na conta.
  Uma linha so (id = 1): o site tem um dono. A calculadora de lote de cada
  setup sai daqui: acoes inteiras (mercado fracionario), o menor entre
  capital x risco / (entrada - stop) e capital / entrada;
- `trades.setup_id`: o setup que originou o trade (botao "Entrei" no setup
  confirmado). ON DELETE SET NULL: o setup e dado derivado; o trade e do usuario
  e nao some se a linha do setup sumir;
- `trades.categoria_setup`: a familia do setup (a mesma `categoria` de
  `setups`), escolhida no formulario para trade feito fora do site. NULL = sem
  setup;
- `trades.stop`: o stop do trade. Com ele, o resultado vira R: resultado total
  sobre o risco em reais (soma das compras x (preco - stop)).

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"
CATEGORIAS = (
    "'reversao', 'forca', 'media', '9.1', '9.2', '9.3', '9.4', '123', 'pfr', 'mma20', 'pullback'"
)


def upgrade() -> None:
    op.create_table(
        "perfil_de_risco",
        sa.Column("id", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("capital", sa.Numeric(16, 2), nullable=False),
        sa.Column("risco_pct", sa.Numeric(5, 2), server_default=sa.text("1.0"), nullable=False),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 1", name="ck_perfil_de_risco_uma_linha"),
        sa.CheckConstraint("capital > 0", name="ck_perfil_de_risco_capital"),
        sa.CheckConstraint("risco_pct > 0 AND risco_pct <= 10", name="ck_perfil_de_risco_risco"),
        schema=SCHEMA,
    )
    op.add_column("trades", sa.Column("setup_id", sa.BigInteger(), nullable=True), schema=SCHEMA)
    op.create_foreign_key(
        "fk_trades_setup",
        "trades",
        "setups",
        ["setup_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    op.add_column("trades", sa.Column("categoria_setup", sa.Text(), nullable=True), schema=SCHEMA)
    op.create_check_constraint(
        "ck_trades_categoria_setup",
        "trades",
        f"categoria_setup IS NULL OR categoria_setup IN ({CATEGORIAS})",
        schema=SCHEMA,
    )
    op.add_column("trades", sa.Column("stop", sa.Numeric(12, 2), nullable=True), schema=SCHEMA)
    op.create_check_constraint(
        "ck_trades_stop_positivo", "trades", "stop IS NULL OR stop > 0", schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_constraint("ck_trades_stop_positivo", "trades", schema=SCHEMA, type_="check")
    op.drop_column("trades", "stop", schema=SCHEMA)
    op.drop_constraint("ck_trades_categoria_setup", "trades", schema=SCHEMA, type_="check")
    op.drop_column("trades", "categoria_setup", schema=SCHEMA)
    op.drop_constraint("fk_trades_setup", "trades", schema=SCHEMA, type_="foreignkey")
    op.drop_column("trades", "setup_id", schema=SCHEMA)
    op.drop_table("perfil_de_risco", schema=SCHEMA)
