"""Estudo sazonal: quando comprar e quando vender a cesta das criptos (24/11/2026).

Pedido do usuario: a melhor epoca do ano para operar comprado e vendido na media
das 50 criptos mais negociadas, com janelas de 1 a 6 meses escolhidas em
2017-2021 e conferidas em 2022-2026 (`scanner.cripto.sazonal`). Tres tabelas,
trocadas a cada noite junto com as da analise:

- `analise_cesta`: o retorno da cesta em cada mes, o do BTC e quantas moedas
  entraram (~110 linhas);
- `analise_janelas`: cada janela (lado x mes de comeco x duracao, 144 linhas)
  com os numeros da escolha, da conferencia e de todos os anos, a posicao na
  escolha e o veredito ("repetiu", "em parte", "nao repetiu");
- `analise_janela_anos`: o resultado de cada janela em cada ano (~1.300 linhas),
  para a tela mostrar de onde vem a media.

Existe nos dois schemas porque as migrations sao as mesmas; so o de cripto tem
linha.

Revision ID: 0031
Revises: 0030
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from scanner import mercado

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = mercado.schema()


def _janela() -> list[sa.Column[object]]:
    return [
        sa.Column("lado", sa.Text(), primary_key=True),
        sa.Column("inicio_mes", sa.SmallInteger(), primary_key=True),
        sa.Column("meses", sa.SmallInteger(), primary_key=True),
    ]


def _numeros(prefixo: str, *, com_controle: bool) -> list[sa.Column[object]]:
    colunas: list[sa.Column[object]] = [
        sa.Column(f"{prefixo}_media", sa.Float()),
        sa.Column(f"{prefixo}_mediana", sa.Float()),
        sa.Column(f"{prefixo}_positivos", sa.SmallInteger(), nullable=False),
        sa.Column(f"{prefixo}_anos", sa.SmallInteger(), nullable=False),
    ]
    if com_controle:
        colunas.append(sa.Column(f"{prefixo}_controle", sa.Float()))
    return colunas


def upgrade() -> None:
    op.create_table(
        "analise_cesta",
        sa.Column("mes", sa.Date(), primary_key=True),
        sa.Column("retorno", sa.Float(), nullable=False),
        sa.Column("retorno_btc", sa.Float()),
        sa.Column("moedas", sa.SmallInteger(), nullable=False),
        schema=SCHEMA,
    )
    op.create_table(
        "analise_janelas",
        *_janela(),
        sa.Column("posicao", sa.SmallInteger()),
        sa.Column("veredito", sa.Text(), nullable=False),
        *_numeros("escolha", com_controle=True),
        *_numeros("conferencia", com_controle=True),
        *_numeros("todos", com_controle=False),
        schema=SCHEMA,
    )
    op.create_table(
        "analise_janela_anos",
        *_janela(),
        sa.Column("ano", sa.SmallInteger(), primary_key=True),
        sa.Column("periodo", sa.Text(), nullable=False),
        sa.Column("resultado", sa.Float(), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for tabela in ("analise_janela_anos", "analise_janelas", "analise_cesta"):
        op.drop_table(tabela, schema=SCHEMA)
