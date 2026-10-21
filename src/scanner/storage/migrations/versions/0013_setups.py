"""Setups (candle de reversao no suporte, filtrado) e niveis de suporte/resistencia.

`setups`: um gatilho por (papel, dia do candle, categoria), com o ciclo de vida
-- armado na noite do candle, confirmado (o dia seguinte passou da maxima) ou
nao confirmou, e encerrado por stop (fechou abaixo da minima do padrao) ou por
prazo (20 pregoes depois de confirmar). A linha nasce uma vez e o que o usuario
viu naquela noite fica congelado: so o estado e os resultados mudam depois.
`ao_vivo` separa o que foi detectado na propria noite do que entrou na carga
retroativa da estreia. Precos na escala do dia do candle, como no COTAHIST.

`niveis`: os segmentos de suporte e resistencia que a ficha desenha. Tabela
derivada, trocada inteira a cada pregao.

Nada aqui alimenta o alerta de 6 sigma.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"
PRECO = sa.Numeric(18, 4)
RETORNO = sa.Numeric(12, 6)


def upgrade() -> None:
    op.create_table(
        "setups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("categoria", sa.Text(), nullable=False),
        sa.Column("padroes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("toques", sa.SmallInteger(), nullable=False),
        sa.Column("virou", sa.Boolean(), nullable=False),
        sa.Column("furou", sa.Boolean(), nullable=False),
        sa.Column("rvol", sa.Numeric(10, 4), nullable=False),
        sa.Column("destaque", sa.Boolean(), nullable=False),
        sa.Column("contexto", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("fechamento", PRECO, nullable=False),
        sa.Column("maxima", PRECO, nullable=False),
        sa.Column("minima", PRECO, nullable=False),
        sa.Column("suporte", PRECO, nullable=False),
        sa.Column("resistencia", PRECO),
        sa.Column("espaco_r", sa.Numeric(10, 2)),
        sa.Column("risco_pct", sa.Numeric(8, 3), nullable=False),
        sa.Column("ao_vivo", sa.Boolean(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False, server_default="armado"),
        sa.Column("confirmado_em", sa.Date()),
        sa.Column("entrada", PRECO),
        sa.Column("encerrado_em", sa.Date()),
        sa.Column("saida", PRECO),
        *(sa.Column(f"{p}{h}", RETORNO) for p in ("r", "m", "rc") for h in (5, 10, 20)),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "trade_date", "categoria", name="uq_setups_papel_dia"),
        sa.CheckConstraint("categoria IN ('reversao', 'forca')", name="ck_setups_categoria"),
        sa.CheckConstraint(
            "estado IN ('armado', 'confirmado', 'nao_confirmou', 'stop', 'prazo')",
            name="ck_setups_estado",
        ),
        sa.CheckConstraint(
            "(estado IN ('armado', 'nao_confirmou')) = (confirmado_em IS NULL)",
            name="ck_setups_confirmacao",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_setups_estado", "setups", ["estado"], schema=SCHEMA)
    op.create_index("ix_setups_ticker", "setups", ["ticker", "trade_date"], schema=SCHEMA)

    op.create_table(
        "niveis",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("lado", sa.Text(), nullable=False),
        sa.Column("preco", PRECO, nullable=False),
        sa.Column("de", sa.Date(), nullable=False),
        sa.Column("ate", sa.Date(), nullable=False),
        sa.Column("vale_desde", sa.Date()),
        sa.Column("rompido_em", sa.Date()),
        sa.Column("virou", sa.Boolean(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("toques", postgresql.JSONB(), nullable=False),
        sa.Column(
            "calculado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("lado IN ('suporte', 'resistencia')", name="ck_niveis_lado"),
        sa.CheckConstraint("de <= ate", name="ck_niveis_periodo"),
        schema=SCHEMA,
    )
    op.create_index("ix_niveis_ticker", "niveis", ["ticker"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_niveis_ticker", table_name="niveis", schema=SCHEMA)
    op.drop_table("niveis", schema=SCHEMA)
    op.drop_index("ix_setups_ticker", table_name="setups", schema=SCHEMA)
    op.drop_index("ix_setups_estado", table_name="setups", schema=SCHEMA)
    op.drop_table("setups", schema=SCHEMA)
