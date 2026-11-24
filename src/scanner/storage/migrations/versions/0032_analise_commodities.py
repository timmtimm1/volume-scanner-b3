"""Commodities na analise: o grupo de cada moeda (24/11/2026).

Pedido do usuario: ver junto das criptos o ouro tokenizado (PAXG, XAUT) e os
contratos perpetuos de commodity da Binance (ouro, prata, platina, paladio,
cobre, petroleo WTI e Brent, gas natural), contra o mesmo BTC, num grupo
proprio (`scanner.cripto.commodities`). `analise_moedas.grupo` e "cripto" ou
"commodity"; a tela filtra por ele, e a cesta do estudo sazonal continua so
cripto. As linhas que ja existem viram "cripto" e a proxima rodada acerta.

Revision ID: 0032
Revises: 0031
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from scanner import mercado

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = mercado.schema()


def upgrade() -> None:
    op.add_column(
        "analise_moedas",
        sa.Column("grupo", sa.Text(), nullable=False, server_default="cripto"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("analise_moedas", "grupo", schema=SCHEMA)
