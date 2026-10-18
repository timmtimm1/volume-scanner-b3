"""Arranjo das caixas de cada pagina do site, escolhido pelo dono.

O site deixa o dono arrastar as caixas de cada pagina no computador (botao
Organizar). O arranjo fica no banco para valer em qualquer computador, nao so
no navegador onde foi feito.

Ha uma linha por tipo de pagina: a ficha vale para todo papel e a Semana para
toda edicao. Quem escreve e o site, pela rota /api/arranjos, protegida pelo
login do dono; o pipeline em Python nunca le nem escreve nesta tabela.

Sem linha, vale o arranjo padrao do codigo, e "Restaurar padrao" apaga a linha.
`itens` e a lista ordenada [{"id", "coluna", "largura"}], validada pela rota; o
CHECK so garante que e uma lista.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    op.create_table(
        "arranjos",
        sa.Column("pagina", sa.Text(), nullable=False),
        sa.Column("itens", postgresql.JSONB(), nullable=False),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("pagina"),
        sa.CheckConstraint(
            "pagina IN ('semana', 'inicio', 'ficha', 'historico', 'trades', 'trade')",
            name="ck_arranjos_pagina",
        ),
        sa.CheckConstraint("jsonb_typeof(itens) = 'array'", name="ck_arranjos_itens"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("arranjos", schema=SCHEMA)
