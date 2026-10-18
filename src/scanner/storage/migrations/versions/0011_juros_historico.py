"""Historico semanal de juros: o dado do grafico de 10 anos da aba Semana.

O resumo semanal guarda so a foto da semana (`resumos_semanais.payload`); um
grafico no tempo precisa de uma linha por semana e por serie, consultavel sem
abrir 520 payloads. A ANBIMA nao serve de fonte (o download gratis guarda so as
ultimas semanas), entao a serie vem do Tesouro Direto e da Selic meta do BCB.

A chave e (semana, serie): `semana` e a sexta-feira nominal; `data_base` e o dia
de onde o numero saiu. Cada montagem regrava tudo (upsert), entao a tabela se
conserta sozinha e cresce uma semana por sabado. O CHECK trava os nomes de
serie que o site sabe desenhar.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    op.create_table(
        "juros_historico",
        sa.Column("semana", sa.Date(), nullable=False),
        sa.Column("serie", sa.Text(), nullable=False),
        sa.Column("taxa", sa.Numeric(8, 4), nullable=False),
        sa.Column("data_base", sa.Date(), nullable=False),
        sa.Column("fonte", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("semana", "serie"),
        sa.CheckConstraint(
            "serie IN ('pre_1a', 'pre_2a', 'pre_5a', 'pre_10a', 'ipca_5a', 'ipca_10a', 'selic')",
            name="ck_juros_historico_serie",
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("juros_historico", schema=SCHEMA)
