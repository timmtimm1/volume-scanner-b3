"""Resumo semanal: o payload que o Telegram e o site vao ler.

Uma linha por semana, com o resumo inteiro em JSONB. O payload e montado uma
vez (sexta depois do pregao ou sabado) e depois so lido; guardar pronto evita
refazer ~300 consultas a B3 e quatro APIs de mercado para reenviar ou mostrar
no site, e congela os numeros como sairam: a CoinGecko, por exemplo, so da a
janela de 7 dias terminando na hora da coleta, e nao da para reconstruir.

A chave e a SEXTA-FEIRA nominal da semana, mesmo quando ela e feriado: e o
identificador que o usuario reconhece ("semana de 16/10"), e fica estavel
quando o ultimo pregao muda (Sexta-feira Santa: fim na quinta, semana na sexta).

`enviado_em` e preenchido pela fase de envio. Com ele preenchido o resumo fica
congelado: regravar so acontece se alguem pedir de proposito.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    op.create_table(
        "resumos_semanais",
        sa.Column("semana", sa.Date(), nullable=False),
        sa.Column("inicio", sa.Date(), nullable=False),
        sa.Column("fim", sa.Date(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column(
            "gerado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("semana"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("resumos_semanais", schema=SCHEMA)
