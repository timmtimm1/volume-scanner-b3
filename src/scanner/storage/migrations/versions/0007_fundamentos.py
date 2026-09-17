"""Fundamentos fase 1: dado bruto de balanco da CVM.

O usuario quer uma aba "Fundamentos" na ficha do papel (P/L, P/VP, EV/EBITDA,
DY, ROE, margem, divida, resultados trimestrais) mostrando o que se sabia no
dia do evento, com a data em que cada balanco foi publicado. Esta fase so
carrega e guarda o dado bruto -- nenhum indicador e calculado aqui.

`empresa_tickers` liga cada ticker ao CD_CVM, que e a chave que o resto das
tabelas usa. A ligacao NAO e por prefixo do ticker: o codigo de emissor da B3
nem sempre bate com ele (o emissor "EMBR" la e a EMBRAST, nao a Embraer), e
errar isso colaria o balanco de uma empresa no papel de outra. Ela vem do FCA
da CVM, que declara o codigo de negociacao de cada empresa, e de uma busca na
B3 conferida contra os codigos da propria empresa para o que o FCA nao cobre.
`empresas` guarda o cadastro da CVM da empresa alcancada. `cvm_documentos` guarda o
resumo das versoes de cada (empresa, tipo, data de referencia): a CVM
reapresenta documentos, e o site quer mostrar quando o mercado soube pela
primeira vez e quando os numeros atuais chegaram. `cvm_resultados` (DRE/DVA,
por periodo tri ou acumulado) e `cvm_balancos` (BPA/BPP e composicao do
capital, uma linha por documento) guardam as contas em si. `arquivos_externos`
e o controle de download condicional dos zips da CVM -- ETag/Last-Modified
para nao rebaixar o mesmo arquivo a cada execucao.

Nenhuma destas tabelas entra na poda de `prune_bars`: fundamentos nao tem
relacao com a retencao de 400 pregoes de barras, que existe por causa do
tamanho do banco hospedado.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"


def upgrade() -> None:
    op.create_table(
        "empresas",
        sa.Column("cd_cvm", sa.Integer(), nullable=False),
        sa.Column("cnpj", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("nome_comercial", sa.Text(), nullable=True),
        sa.Column("setor_cvm", sa.Text(), nullable=True),
        sa.Column("situacao", sa.Text(), nullable=True),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("cd_cvm"),
        schema=SCHEMA,
    )

    # cd_cvm nulo e cache negativo ("procurei e nao achei"): sem ele, um ETF
    # ou um papel sem empresa na CVM refaria a busca na B3 todo dia.
    op.create_table(
        "empresa_tickers",
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("cd_cvm", sa.Integer(), nullable=True),
        sa.Column("fonte", sa.Text(), nullable=True),
        sa.Column("verificado_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("ticker"),
        sa.ForeignKeyConstraint(["cd_cvm"], [f"{SCHEMA}.empresas.cd_cvm"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "fonte IS NULL OR fonte IN ('fca', 'b3')", name="ck_empresa_tickers_fonte"
        ),
        sa.CheckConstraint(
            "(cd_cvm IS NULL) = (fonte IS NULL)", name="ck_empresa_tickers_fonte_com_empresa"
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "cvm_documentos",
        sa.Column("cd_cvm", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("dt_refer", sa.Date(), nullable=False),
        sa.Column("versao", sa.SmallInteger(), nullable=False),
        sa.Column("recebido_original", sa.Date(), nullable=False),
        sa.Column("recebido_ultima", sa.Date(), nullable=False),
        sa.Column("escopo", sa.Text(), nullable=False),
        sa.Column("layout", sa.Text(), nullable=False),
        sa.Column("id_doc", sa.BigInteger(), nullable=True),
        sa.Column(
            "carregado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("cd_cvm", "tipo", "dt_refer"),
        sa.ForeignKeyConstraint(["cd_cvm"], [f"{SCHEMA}.empresas.cd_cvm"], ondelete="CASCADE"),
        sa.CheckConstraint("tipo IN ('ITR', 'DFP')", name="ck_cvm_documentos_tipo"),
        sa.CheckConstraint("escopo IN ('con', 'ind')", name="ck_cvm_documentos_escopo"),
        sa.CheckConstraint("layout IN ('geral', 'financeiro')", name="ck_cvm_documentos_layout"),
        sa.CheckConstraint(
            "recebido_ultima >= recebido_original", name="ck_cvm_documentos_recebido_em_ordem"
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "cvm_resultados",
        sa.Column("cd_cvm", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("dt_refer", sa.Date(), nullable=False),
        sa.Column("dt_ini", sa.Date(), nullable=False),
        sa.Column("dt_fim", sa.Date(), nullable=False),
        sa.Column("receita", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("resultado_bruto", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("ebit", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("lucro_liquido", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("lucro_controladores", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("depreciacao_amortizacao", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.PrimaryKeyConstraint("cd_cvm", "tipo", "dt_refer", "dt_ini", "dt_fim"),
        sa.ForeignKeyConstraint(
            ["cd_cvm", "tipo", "dt_refer"],
            [
                f"{SCHEMA}.cvm_documentos.cd_cvm",
                f"{SCHEMA}.cvm_documentos.tipo",
                f"{SCHEMA}.cvm_documentos.dt_refer",
            ],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("dt_ini <= dt_fim", name="ck_cvm_resultados_periodo_em_ordem"),
        schema=SCHEMA,
    )

    op.create_table(
        "cvm_balancos",
        sa.Column("cd_cvm", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("dt_refer", sa.Date(), nullable=False),
        sa.Column("ativo_total", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("ativo_circulante", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("caixa", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("aplicacoes_financeiras", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("passivo_circulante", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("emprestimos_cp", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("arrendamento_cp", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("emprestimos_lp", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("arrendamento_lp", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("patrimonio_liquido", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("pl_nao_controladores", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("acoes_on", sa.BigInteger(), nullable=True),
        sa.Column("acoes_pn", sa.BigInteger(), nullable=True),
        sa.Column("tesouraria_on", sa.BigInteger(), nullable=True),
        sa.Column("tesouraria_pn", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("cd_cvm", "tipo", "dt_refer"),
        sa.ForeignKeyConstraint(
            ["cd_cvm", "tipo", "dt_refer"],
            [
                f"{SCHEMA}.cvm_documentos.cd_cvm",
                f"{SCHEMA}.cvm_documentos.tipo",
                f"{SCHEMA}.cvm_documentos.dt_refer",
            ],
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "arquivos_externos",
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.Column("modificado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escopo_hash", sa.Text(), nullable=True),
        sa.Column("verificado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processado_em", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("url"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("arquivos_externos", schema=SCHEMA)
    op.drop_table("cvm_balancos", schema=SCHEMA)
    op.drop_table("cvm_resultados", schema=SCHEMA)
    op.drop_table("cvm_documentos", schema=SCHEMA)
    op.drop_table("empresa_tickers", schema=SCHEMA)
    op.drop_table("empresas", schema=SCHEMA)
