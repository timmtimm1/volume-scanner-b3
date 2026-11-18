"""Venda a descoberto no diario de trades (18/11/2026).

Pedido do usuario: registrar trade VENDIDO em cripto (abre com uma venda,
fecha com a recompra), com a taxa dos futuros da Binance. A B3 continua so
comprada; quem decide isso e o site (`regrasDoDiario(mercado).vendido`).

A posicao vendida e guardada com quantidade NEGATIVA, nas colunas que ja
existem: assim a mesma formula do resultado, `realizado + quantidade x
(fechamento - preco_medio)`, marca os dois lados, no site e no
`marcar_a_mercado` do Python, sem conta nova. Por isso caem as duas travas de
quantidade nao negativa:

- `ck_trade_operacoes_quantidade_apos_nao_negativa`;
- `ck_trade_snapshots_quantidade_nao_negativa`.

A quantidade de cada OPERACAO continua positiva (`quantidade > 0`): o sinal e
so da posicao. O lado do trade nao ganha coluna: e o tipo da primeira
operacao, que o site sempre le junto com o trade.

Revision ID: 0029
Revises: 0028
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from scanner import mercado

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = mercado.schema()

TRAVAS = (
    ("trade_operacoes", "ck_trade_operacoes_quantidade_apos_nao_negativa", "quantidade_apos >= 0"),
    ("trade_snapshots", "ck_trade_snapshots_quantidade_nao_negativa", "quantidade >= 0"),
)


def upgrade() -> None:
    for tabela, nome, _ in TRAVAS:
        op.drop_constraint(nome, tabela, schema=SCHEMA, type_="check")


def downgrade() -> None:
    # A volta nao cabe com trade vendido gravado: a trava recusaria a posicao
    # negativa. Melhor parar explicando do que apagar.
    vendido = op.get_bind().execute(
        sa.text(
            f'SELECT EXISTS (SELECT 1 FROM "{SCHEMA}".trade_operacoes WHERE quantidade_apos < 0)'
        )
    )
    if vendido.scalar():
        raise RuntimeError(
            f"{SCHEMA}.trade_operacoes tem posicao vendida (negativa): a migration 0028 nao "
            "guarda isso. Apague (ou exporte) os trades vendidos antes de voltar."
        )
    for tabela, nome, condicao in TRAVAS:
        op.create_check_constraint(nome, tabela, condicao, schema=SCHEMA)
