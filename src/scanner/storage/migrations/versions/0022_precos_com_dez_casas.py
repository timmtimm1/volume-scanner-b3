"""Precos com dez casas decimais (aba Cripto, 16/11/2026).

As colunas de preco nasceram `Numeric(18, 4)`: quatro casas sobram para a B3,
onde o preco tem duas. Em cripto ha moeda cotada a 0,00001 dolar, e com quatro
casas ela seria gravada como zero. As tabelas sao as mesmas nos dois mercados
(cada um no seu schema, ver `scanner.mercado`), entao a coluna alarga nos dois:
`Numeric(28, 10)`.

Para a B3 nada muda no valor: `numeric` guarda o numero exato, e 34,5 continua
34,5. O `ALTER` reescreve a tabela uma vez; a maior, `daily_bars`, tem os 400
pregoes do banco (algumas dezenas de MB).

Ficam de fora, de proposito: alertas de preco e o diario de trades (duas casas,
quantidade inteira). Cripto nesses dois e outra fase.

Revision ID: 0022
Revises: 0021
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from scanner import mercado

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = mercado.schema()

COLUNAS: dict[str, tuple[str, ...]] = {
    "daily_bars": ("open", "high", "low", "close", "avg_price"),
    "setups": ("fechamento", "maxima", "minima", "suporte", "resistencia", "entrada", "saida"),
    "niveis": ("preco",),
    "trade_snapshots": ("fechamento",),
}


def _trocar(precisao: int, casas: int) -> None:
    # Um ALTER TABLE por tabela, com todas as colunas: uma reescrita so.
    for tabela, colunas in COLUNAS.items():
        partes = ", ".join(f'ALTER COLUMN "{c}" TYPE numeric({precisao}, {casas})' for c in colunas)
        op.execute(sa.text(f'ALTER TABLE "{SCHEMA}"."{tabela}" {partes}'))


def upgrade() -> None:
    _trocar(28, 10)


def downgrade() -> None:
    _trocar(18, 4)
