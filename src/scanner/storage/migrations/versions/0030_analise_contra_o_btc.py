"""Analise: cada cripto contra o Bitcoin, por mes e ano (24/11/2026).

Pedido do usuario: a pagina Analise, com o retorno de cada moeda que ja passou
pela Binance contra o do Bitcoin, mes a mes e ano a ano, e o beta e a
correlacao com ele (por ano, no periodo todo e numa janela movel de 90 dias).

Quatro tabelas, trocadas inteiras a cada noite pelo `scanner cripto analise`:

- `analise_moedas`: uma linha por moeda com o historico diario dela em duas
  listas compactas (fechamento e volume em dolar, um valor por dia desde o
  `primeiro_dia`, NaN no dia sem candle). E o estado da carga: a noite seguinte
  so pede a Binance os dias novos. As ~700 moedas desde 2017 cabem em ~13 MB;
  como linhas soltas seriam ~800 mil, e o banco gratis tem 0,5 GB.
- `analise_anual`: moeda x ano; `ano = 0` e o periodo todo.
- `analise_mensal`: moeda x mes (o primeiro dia do mes).
- `analise_movel`: beta e correlacao dos ultimos 90 dias, um ponto por semana.

O site so le. Existe nos dois schemas porque as migrations sao as mesmas; so o
de cripto tem linha.

Revision ID: 0030
Revises: 0029
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from scanner import mercado

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = mercado.schema()


def _periodo() -> list[sa.Column[object]]:
    return [
        sa.Column("inicio", sa.Date(), nullable=False),
        sa.Column("fim", sa.Date(), nullable=False),
        sa.Column("parcial", sa.Boolean(), nullable=False),
        sa.Column("retorno", sa.Float(), nullable=False),
        sa.Column("retorno_btc", sa.Float()),
        sa.Column("relativo", sa.Float()),
    ]


def upgrade() -> None:
    op.create_table(
        "analise_moedas",
        sa.Column("moeda", sa.Text(), primary_key=True),
        sa.Column("par", sa.Text(), nullable=False),
        sa.Column("fonte", sa.Text(), nullable=False),
        sa.Column("negociando", sa.Boolean(), nullable=False),
        sa.Column("fora_por", sa.Text()),
        sa.Column("primeiro_dia", sa.Date(), nullable=False),
        sa.Column("ultimo_dia", sa.Date(), nullable=False),
        sa.Column("volume_12m", sa.Float()),
        sa.Column("fechamentos", postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column("volumes", postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "analise_anual",
        sa.Column("moeda", sa.Text(), primary_key=True),
        sa.Column("ano", sa.SmallInteger(), primary_key=True),
        *_periodo(),
        sa.Column("beta", sa.Float()),
        sa.Column("correlacao", sa.Float()),
        sa.Column("dias", sa.Integer(), nullable=False),
        schema=SCHEMA,
    )
    op.create_table(
        "analise_mensal",
        sa.Column("moeda", sa.Text(), primary_key=True),
        sa.Column("mes", sa.Date(), primary_key=True),
        *_periodo(),
        schema=SCHEMA,
    )
    op.create_table(
        "analise_movel",
        sa.Column("moeda", sa.Text(), primary_key=True),
        sa.Column("dia", sa.Date(), primary_key=True),
        sa.Column("beta", sa.Float(), nullable=False),
        sa.Column("correlacao", sa.Float(), nullable=False),
        sa.Column("dias", sa.SmallInteger(), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for tabela in ("analise_movel", "analise_mensal", "analise_anual", "analise_moedas"):
        op.drop_table(tabela, schema=SCHEMA)
