"""Setups na media movel: categoria `media` e o tipo de suporte.

Pedido de 21/10/2026: o candle de reversao que encosta numa media movel em
tendencia de alta (MME 9 ou MMA 20) entra como categoria propria, `media`, ao
lado da reversao no suporte horizontal e do candle de forca.

`suporte_tipo` diz o que segurou o candle: `nivel` (suporte horizontal, o caso
de todos os setups gravados antes desta migration) ou o nome das medias
tocadas (`mme9`, `mma20`, ou `mme9,mma20` quando encostou nas duas).

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    op.drop_constraint("ck_setups_categoria", "setups", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_setups_categoria",
        "setups",
        "categoria IN ('reversao', 'forca', 'media')",
        schema=SCHEMA,
    )
    op.add_column(
        "setups",
        sa.Column("suporte_tipo", sa.Text(), nullable=False, server_default="nivel"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.setups WHERE categoria = 'media'")
    op.drop_column("setups", "suporte_tipo", schema=SCHEMA)
    op.drop_constraint("ck_setups_categoria", "setups", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_setups_categoria", "setups", "categoria IN ('reversao', 'forca')", schema=SCHEMA
    )
