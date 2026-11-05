"""Resultado da suite de backtest dos setups (secao 14 do plano).

A suite roda na maquina do usuario, sobre 30 anos de COTAHIST
(`scripts/backtest_setups.py`); so o resultado vem para o banco, numa
"rodada". O site mostra sempre a rodada mais recente. As tabelas filhas
dependem da rodada (FK com ON DELETE CASCADE): apagar uma rodada leva tudo
dela, e o envio guarda so as duas ultimas.

- `backtest_resultados`: a grade -- setup x saida x grupo (tendencia) x periodo;
- `backtest_escolhas`: por setup, a combinacao escolhida em 1995-2015 e o nivel
  (firme, fraco, falhou) da conferencia em 2016-2026;
- `backtest_anos`: ano a ano;
- `backtest_curvas`: R acumulado por mes de saida, do setup e do controle;
- `backtest_trades`: uma amostra -- os trades mais recentes de cada setup e
  saida, para a lista do app (os 1,4 milhao de trades ficam na maquina).

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"
SAIDAS = "saida IN ('alvo1', 'alvo2', 'alvo3', 'minimas', 'mme9')"
GRUPOS = "grupo IN ('todos', 'alta', 'contra')"


def _rodada() -> sa.Column[int]:
    return sa.Column(
        "rodada_id",
        sa.BigInteger(),
        sa.ForeignKey(f"{SCHEMA}.backtest_rodadas.id", ondelete="CASCADE"),
        nullable=False,
    )


def _numeros(*nomes: str) -> list[sa.Column[float]]:
    return [sa.Column(n, sa.Float(), nullable=True) for n in nomes]


def upgrade() -> None:
    op.create_table(
        "backtest_rodadas",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("dados_de", sa.Date(), nullable=False),
        sa.Column("dados_ate", sa.Date(), nullable=False),
        sa.Column("custo", sa.Float(), nullable=False),
        sa.Column("teto", sa.Integer(), nullable=False),
        sa.Column("trades", sa.Integer(), nullable=False),
        sa.Column("papeis", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_table(
        "backtest_resultados",
        _rodada(),
        sa.Column("setup", sa.Text(), nullable=False),
        sa.Column("saida", sa.Text(), nullable=False),
        sa.Column("grupo", sa.Text(), nullable=False),
        sa.Column("periodo", sa.Text(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        *_numeros(
            "acerto",
            "ganho_medio",
            "perda_media",
            "payoff",
            "expectativa",
            "ic_baixo",
            "ic_alto",
            "fator_lucro",
            "dias_medio",
            "r_por_dia",
            "controle",
            "diferenca",
            "dif_ic_baixo",
            "dif_ic_alto",
            "pct_stop",
            "pct_movel",
            "pct_alvo",
            "pct_mme9",
            "pct_teto",
        ),
        sa.PrimaryKeyConstraint("rodada_id", "setup", "saida", "grupo", "periodo"),
        sa.CheckConstraint(SAIDAS, name="ck_backtest_resultados_saida"),
        sa.CheckConstraint(GRUPOS, name="ck_backtest_resultados_grupo"),
        sa.CheckConstraint(
            "periodo IN ('1995-2015', '2016-2026', 'tudo')", name="ck_backtest_resultados_periodo"
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "backtest_escolhas",
        _rodada(),
        sa.Column("setup", sa.Text(), nullable=False),
        sa.Column("nivel", sa.Text(), nullable=False),
        sa.Column("saida", sa.Text(), nullable=True),
        sa.Column("grupo", sa.Text(), nullable=True),
        sa.Column("combinacoes", sa.Integer(), nullable=False),
        sa.Column("n_escolha", sa.Integer(), nullable=True),
        sa.Column("n_conferencia", sa.Integer(), nullable=True),
        *_numeros(
            "exp_escolha",
            "dif_escolha",
            "exp_conferencia",
            "ic_conf_baixo",
            "ic_conf_alto",
            "dif_conferencia",
        ),
        sa.PrimaryKeyConstraint("rodada_id", "setup"),
        sa.CheckConstraint(
            "nivel IN ('firme', 'fraco', 'falhou')", name="ck_backtest_escolhas_nivel"
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "backtest_anos",
        _rodada(),
        sa.Column("setup", sa.Text(), nullable=False),
        sa.Column("saida", sa.Text(), nullable=False),
        sa.Column("grupo", sa.Text(), nullable=False),
        sa.Column("ano", sa.SmallInteger(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        *_numeros("expectativa", "soma_r", "controle"),
        sa.PrimaryKeyConstraint("rodada_id", "setup", "saida", "grupo", "ano"),
        schema=SCHEMA,
    )
    op.create_table(
        "backtest_curvas",
        _rodada(),
        sa.Column("setup", sa.Text(), nullable=False),
        sa.Column("saida", sa.Text(), nullable=False),
        sa.Column("grupo", sa.Text(), nullable=False),
        sa.Column("mes", sa.Date(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        *_numeros("r", "controle", "acumulado", "controle_acumulado", "recuo"),
        sa.PrimaryKeyConstraint("rodada_id", "setup", "saida", "grupo", "mes"),
        schema=SCHEMA,
    )
    op.create_table(
        "backtest_trades",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        _rodada(),
        sa.Column("setup", sa.Text(), nullable=False),
        sa.Column("saida", sa.Text(), nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("data_sinal", sa.Date(), nullable=False),
        sa.Column("data_entrada", sa.Date(), nullable=False),
        sa.Column("data_saida", sa.Date(), nullable=True),
        sa.Column("entrada", sa.Float(), nullable=False),
        sa.Column("stop", sa.Float(), nullable=False),
        sa.Column("preco_saida", sa.Float(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("dias", sa.SmallInteger(), nullable=True),
        sa.Column("r", sa.Float(), nullable=True),
        sa.Column("r_controle", sa.Float(), nullable=True),
        sa.Column("alta", sa.Boolean(), nullable=False),
        sa.Column("rvol", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(SAIDAS, name="ck_backtest_trades_saida"),
        sa.CheckConstraint(
            "motivo IN ('aberto', 'stop', 'movel', 'alvo', 'mme9', 'teto')",
            name="ck_backtest_trades_motivo",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_backtest_trades_lista",
        "backtest_trades",
        ["rodada_id", "setup", "saida", "data_entrada"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_backtest_trades_lista", "backtest_trades", schema=SCHEMA)
    for tabela in (
        "backtest_trades",
        "backtest_curvas",
        "backtest_anos",
        "backtest_escolhas",
        "backtest_resultados",
        "backtest_rodadas",
    ):
        op.drop_table(tabela, schema=SCHEMA)
