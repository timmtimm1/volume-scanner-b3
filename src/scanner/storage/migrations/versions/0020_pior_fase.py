"""A pior fase de cada combinacao do backtest (secao 14 do plano).

Pedido do usuario em 11/11/2026, para o cartao da aba Setups: alem da perda no
stop, a pior fase que o setup ja teve. A grade soma todos os papeis, e isso nao
e a conta de uma pessoa; as duas colunas novas medem quem opera um trade por
vez (`scanner.backtest.metricas.pior_fase`): a maior sequencia de perdas e o
maior recuo do R acumulado, mediana de caminhos sorteados.

Nulas nas rodadas enviadas antes: o cartao so mostra a linha quando ha numero.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    for coluna in ("pior_sequencia", "pior_recuo"):
        op.add_column("backtest_resultados", sa.Column(coluna, sa.Float()), schema=SCHEMA)


def downgrade() -> None:
    for coluna in ("pior_recuo", "pior_sequencia"):
        op.drop_column("backtest_resultados", coluna, schema=SCHEMA)
