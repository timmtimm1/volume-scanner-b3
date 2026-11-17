"""Preco do alerta com dez casas decimais (avisos de cripto, 17/11/2026).

O alerta de preco nasceu para a B3, com duas casas e a regra `preco > 0`. Em
cripto o gatilho de uma moeda de US$ 0,0000042 arredondaria para 0,00: a
gravacao falharia na restricao e derrubaria o pipeline (por isso os alertas de
cripto estavam desligados). Os dois precos do alerta passam a `Numeric(28, 10)`,
como as colunas de preco da 0022. Para a B3 nenhum valor muda.

Revision ID: 0025
Revises: 0024
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from scanner import mercado

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = mercado.schema()


def _trocar(precisao: int, casas: int) -> None:
    op.execute(
        sa.text(
            f'ALTER TABLE "{SCHEMA}"."price_alerts" '
            f'ALTER COLUMN "preco" TYPE numeric({precisao}, {casas}), '
            f'ALTER COLUMN "preco_disparo" TYPE numeric({precisao}, {casas})'
        )
    )


def upgrade() -> None:
    _trocar(28, 10)


def downgrade() -> None:
    _trocar(12, 2)
