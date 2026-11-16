"""A grade do backtest aceita os periodos de cripto (aba Cripto, 16/11/2026).

Na B3 a escolha e feita em 1995-2015 e conferida em 2016-2026. A Binance so
existe desde 2017: em cripto a escolha e 2017-2021 e a conferencia 2022-2026.
A tabela e a mesma nos dois schemas, entao a restricao aceita os quatro
rotulos (e `tudo`).

Revision ID: 0024
Revises: 0023
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from scanner import mercado

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = mercado.schema()
NOME = "ck_backtest_resultados_periodo"
ANTES = "periodo IN ('1995-2015', '2016-2026', 'tudo')"
DEPOIS = "periodo IN ('1995-2015', '2016-2026', '2017-2021', '2022-2026', 'tudo')"


def _trocar(condicao: str) -> None:
    op.drop_constraint(NOME, "backtest_resultados", schema=SCHEMA, type_="check")
    op.create_check_constraint(NOME, "backtest_resultados", condicao, schema=SCHEMA)


def upgrade() -> None:
    _trocar(DEPOIS)


def downgrade() -> None:
    _trocar(ANTES)
