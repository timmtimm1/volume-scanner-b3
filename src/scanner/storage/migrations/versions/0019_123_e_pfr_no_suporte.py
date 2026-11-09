"""Categorias `123_suporte` e `pfr_suporte` (secao 14 do plano).

Pedido do usuario em 09/11/2026: o 1-2-3 e o PFR com a minima do padrao num
suporte de 3+ toques viram setups a parte (o 123 e o PFR de sempre continuam).
So muda a lista de categorias aceitas em `setups`, `setup_preferencias` e
`trades.categoria_setup`.

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"
ANTES = (
    "'reversao', 'forca', 'media', '9.1', '9.2', '9.3', '9.4', '123', 'pfr', 'mma20', 'pullback'"
)
DEPOIS = (
    "'reversao', 'forca', 'media', '9.1', '9.2', '9.3', '9.4', '123', 'pfr', "
    "'123_suporte', 'pfr_suporte', 'mma20', 'pullback'"
)
NOVAS = "'123_suporte', 'pfr_suporte'"


def _trocar(categorias: str) -> None:
    for nome, tabela, regra in (
        ("ck_setups_categoria", "setups", f"categoria IN ({categorias})"),
        (
            "ck_setup_preferencias_categoria",
            "setup_preferencias",
            f"categoria IN ({categorias})",
        ),
        (
            "ck_trades_categoria_setup",
            "trades",
            f"categoria_setup IS NULL OR categoria_setup IN ({categorias})",
        ),
    ):
        op.drop_constraint(nome, tabela, schema=SCHEMA, type_="check")
        op.create_check_constraint(nome, tabela, regra, schema=SCHEMA)


def upgrade() -> None:
    _trocar(DEPOIS)


def downgrade() -> None:
    # o trade e do usuario: perde so a etiqueta; setup e preferencia sao derivados
    op.execute(
        f"UPDATE {SCHEMA}.trades SET categoria_setup = NULL WHERE categoria_setup IN ({NOVAS})"
    )
    op.execute(f"DELETE FROM {SCHEMA}.setup_preferencias WHERE categoria IN ({NOVAS})")
    op.execute(f"DELETE FROM {SCHEMA}.setups WHERE categoria IN ({NOVAS})")
    _trocar(ANTES)
