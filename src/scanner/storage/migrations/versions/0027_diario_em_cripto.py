"""Diario de trades em cripto (17/11/2026).

As tabelas do diario nasceram para a B3: quantidade inteira de acoes, preco
com duas casas e preco medio com seis. Em cripto compra-se 0,0153 BTC, a taxa
da Binance sai da moeda comprada (0,0153 vira 0,0152847) e ha moeda cotada a
0,000004 dolar. As colunas alargam nos dois schemas, como na migration 0022:

- quantidade e posicao: `integer` -> `numeric(28, 10)`;
- preco da operacao e stop do trade: `numeric(12, 2)` -> `numeric(28, 10)`;
- preco medio: `numeric(18, 6)` -> `numeric(28, 10)`.

Para a B3 nada muda no valor: 100 acoes continuam 100, e o site continua
aceitando so quantidade inteira e preco com duas casas (`web/src/lib/mercado.ts`).

O trade tambem pode nascer do sinal de reversao no RSI do estudo de cripto
(tabela `sinais_estudo`, migration 0026): coluna `sinal_estudo_id`, com a
categoria nova `rsi_estudo`. Existe nos dois schemas porque as migrations sao
as mesmas; so o de cripto usa.

Revision ID: 0027
Revises: 0026
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from scanner import mercado

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = mercado.schema()

NOVO = "numeric(28, 10)"

# tabela -> {coluna: tipo antigo}
COLUNAS: dict[str, dict[str, str]] = {
    "trade_operacoes": {
        "quantidade": "integer",
        "preco": "numeric(12, 2)",
        "quantidade_apos": "integer",
        "preco_medio_apos": "numeric(18, 6)",
    },
    "trades": {"stop": "numeric(12, 2)"},
    "trade_snapshots": {"quantidade": "integer", "preco_medio": "numeric(18, 6)"},
}

CATEGORIAS_ANTIGAS = (
    "'reversao', 'forca', 'media', '9.1', '9.2', '9.3', '9.4', '123', 'pfr', "
    "'123_suporte', 'pfr_suporte', 'mma20', 'pullback', 'contracao', 'rompimento'"
)


def _trocar_tipos(antigo: bool) -> None:
    # Um ALTER TABLE por tabela, com todas as colunas: uma reescrita so.
    for tabela, colunas in COLUNAS.items():
        partes = ", ".join(
            f'ALTER COLUMN "{c}" TYPE {tipo if antigo else NOVO}' for c, tipo in colunas.items()
        )
        op.execute(sa.text(f'ALTER TABLE "{SCHEMA}"."{tabela}" {partes}'))


def _recusar_se_houver_fracao() -> None:
    """A volta nao cabe com trade de cripto gravado: 0,0153 BTC viraria 0 acoes.

    Melhor parar com a explicacao do que apagar posicao ou deixar o Postgres
    reclamar do check `quantidade > 0` sem dizer por que.
    """
    fracao = op.get_bind().execute(
        sa.text(
            f'SELECT EXISTS (SELECT 1 FROM "{SCHEMA}".trade_operacoes '
            "WHERE quantidade <> trunc(quantidade) OR quantidade_apos <> trunc(quantidade_apos))"
        )
    )
    if fracao.scalar():
        raise RuntimeError(
            f"{SCHEMA}.trade_operacoes tem quantidade fracionada: a migration 0026 guarda so "
            "inteiro. Apague (ou exporte) os trades de cripto antes de voltar."
        )


def _categorias(lista: str) -> None:
    op.drop_constraint("ck_trades_categoria_setup", "trades", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_trades_categoria_setup",
        "trades",
        f"categoria_setup IS NULL OR categoria_setup IN ({lista})",
        schema=SCHEMA,
    )


def upgrade() -> None:
    _trocar_tipos(antigo=False)
    op.add_column("trades", sa.Column("sinal_estudo_id", sa.BigInteger()), schema=SCHEMA)
    op.create_foreign_key(
        "fk_trades_sinal_estudo",
        "trades",
        "sinais_estudo",
        ["sinal_estudo_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    _categorias(f"{CATEGORIAS_ANTIGAS}, 'rsi_estudo'")


def downgrade() -> None:
    _recusar_se_houver_fracao()
    op.execute(
        sa.text(
            f'UPDATE "{SCHEMA}".trades SET categoria_setup = NULL '
            "WHERE categoria_setup = 'rsi_estudo'"
        )
    )
    _categorias(CATEGORIAS_ANTIGAS)
    op.drop_constraint("fk_trades_sinal_estudo", "trades", schema=SCHEMA, type_="foreignkey")
    op.drop_column("trades", "sinal_estudo_id", schema=SCHEMA)
    _trocar_tipos(antigo=True)
