"""Fundamentos fase 3: o trimestre calculado que a ficha le.

As tabelas da fase 1 guardam o dado bruto da CVM, do jeito que ele vem: o 4T
nao existe, a depreciacao so aparece acumulada no ano, e cada layout de
empresa usa codigos de conta diferentes. Nenhuma tela quer lidar com isso.

Esta tabela e o resultado ja mastigado: um trimestre por linha, com receita,
EBITDA e lucro do trimestre e dos ultimos 12 meses, e os saldos que os
indicadores usam. Nada aqui depende de preco -- P/L, P/VP, EV/EBITDA e
dividend yield saem na hora de desenhar a ficha, porque dependem da data que o
usuario esta olhando.

E derivada: pode ser apagada e recalculada a partir das tabelas da fase 1 sem
perder nada. E o que o recalculo faz quando a CVM publica arquivo novo.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"

_VALORES = (
    "receita_tri",
    "ebitda_tri",
    "lucro_tri",
    "receita_12m",
    "ebitda_12m",
    "lucro_12m",
    "patrimonio_liquido",
    "ativo_total",
    "divida_liquida",
    "divida_liquida_sem_arrendamento",
)


def upgrade() -> None:
    colunas = [
        sa.Column("cd_cvm", sa.Integer(), nullable=False),
        sa.Column("dt_fim", sa.Date(), nullable=False),
        sa.Column("rotulo", sa.Text(), nullable=False),
        sa.Column("origem", sa.Text(), nullable=False),
        sa.Column("publicado_em", sa.Date(), nullable=True),
        sa.Column("layout", sa.Text(), nullable=True),
    ]
    colunas += [
        sa.Column(nome, sa.Numeric(precision=20, scale=2), nullable=True) for nome in _VALORES
    ]
    colunas += [
        sa.Column("liquidez_corrente", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("acoes_em_circulacao", sa.BigInteger(), nullable=True),
        sa.Column(
            "calculado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]

    op.create_table(
        "fundamentos_trimestre",
        *colunas,
        sa.PrimaryKeyConstraint("cd_cvm", "dt_fim"),
        sa.ForeignKeyConstraint(["cd_cvm"], [f"{SCHEMA}.empresas.cd_cvm"], ondelete="CASCADE"),
        sa.CheckConstraint("origem IN ('ITR', 'DFP', 'derivado')", name="ck_fundamentos_origem"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("fundamentos_trimestre", schema=SCHEMA)
