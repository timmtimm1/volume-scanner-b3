"""Modelo de dados (secao 8 do plano).

O schema `volume_scanner` isola as tabelas do projeto do `public` do banco.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "volume_scanner"


class Base(DeclarativeBase):
    """Base declarativa, com todas as tabelas presas ao schema do projeto."""

    metadata = MetaData(schema=SCHEMA)


class DailyBar(Base):
    """Barra diaria de um papel, como veio do COTAHIST.

    Dias sem negociacao nao viram linha com zero: simplesmente nao existem.
    """

    __tablename__ = "daily_bars"
    __table_args__ = (Index("ix_daily_bars_trade_date", "trade_date"),)

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    avg_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    volume_shares: Mapped[int | None] = mapped_column(BigInteger)
    volume_financial: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    trades_count: Mapped[int | None] = mapped_column(Integer)
    # TOTNEG e N(05) e satura em 99999: valor censurado, nao valor real.
    trades_censored: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class VolumeMetric(Base):
    """Z-scores de uma janela para um papel num pregao (secao 3.1)."""

    __tablename__ = "volume_metrics"
    # A PK comeca por `ticker`, e nao serve para filtro so por data -- que e o
    # que o site faz para achar o ultimo pregao. Barras e contexto ja tinham o
    # seu; esta, que e a maior das tres em linhas, nao tinha.
    __table_args__ = (Index("ix_volume_metrics_trade_date", "trade_date"),)

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    window_size: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    z_log: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    z_raw: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    z_robust: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    rvol: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))


class DailyFeature(Base):
    """Contexto da secao 3.2 de um papel num pregao, tenha ele virado evento ou nao.

    Existe porque a tela mostra uma faixa de z maior que a do alerta, e uma
    linha sem contexto nao serve para ler nada. `Event.features` continua sendo
    a verdade do que foi notificado; esta tabela e o contexto de tudo que se
    calculou.
    """

    __tablename__ = "daily_features"
    __table_args__ = (Index("ix_daily_features_trade_date", "trade_date"),)

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class Event(Base):
    """Evento que cruzou o limiar. Dedupe por (ticker, trade_date)."""

    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("ticker", "trade_date", name="uq_events_ticker_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    max_z_log: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    triggered_windows: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), nullable=False)
    volume_financial: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    # Todo o contexto da secao 3.2 do plano.
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DigestSend(Base):
    """Carimbo de que o resumo de um pregao ja saiu.

    O alerta se protege de reenvio com `events.notified_at`; o resumo nao tinha
    equivalente e ia de novo a cada execucao. Isso acontece sozinho, sem ninguem
    reprocessar nada a mao: o `daily` roda de terca a sabado pedindo `ultimo`, e
    numa segunda de feriado a terca resolve para a mesma sexta que o sabado ja
    tinha processado. Na semana de carnaval, tres vezes.

    Tabela propria, e nao uma coluna em outra: o resumo existe por pregao e nao
    por papel, e num pregao em que nada cruzou o limiar `events` fica vazia --
    nao haveria linha onde carimbar justamente no dia em que o resumo e a unica
    coisa que sai.
    """

    __tablename__ = "digest_sends"

    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PriceAlert(Base):
    """Alerta de rompimento de preco, criado a mao a partir de um evento.

    Nasce de um papel que apareceu no scanner: o usuario olha o grafico, escolhe
    um nivel e pede para ser avisado quando o preco chegar la. Nada aqui e
    calculado pelo sistema -- e a leitura do usuario virando gatilho, e por isso
    o alerta guarda `trade_date`: o pregao do evento que motivou ele.

    `direcao` e 'acima' ou 'abaixo'. Um alerta so olha para um lado; para vigiar
    os dois extremos de um papel, criam-se dois alertas.

    Dispara uma vez e se desativa (`disparado_em` preenchido). `preco_disparo`
    guarda a cotacao que causou o disparo, nao o nivel pedido: com checagem de
    15 em 15 minutos, um pavio pode furar o nivel e voltar, e ver o preco real
    e o que permite distinguir rompimento de ruido depois do fato.
    """

    __tablename__ = "price_alerts"
    __table_args__ = (
        Index("ix_price_alerts_ativo", "disparado_em"),
        CheckConstraint("direcao IN ('acima', 'abaixo')", name="ck_price_alerts_direcao"),
        CheckConstraint("preco > 0", name="ck_price_alerts_preco_positivo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    # O pregao do evento que motivou o alerta. Serve para a ficha do papel
    # mostrar a linha no contexto certo, e para saber o quanto ele envelheceu.
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    preco: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    direcao: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    disparado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preco_disparo: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # De qual fornecedor veio a cotacao que disparou. Quando um alerta parecer
    # errado, a primeira pergunta e "que dado o sistema viu?".
    fonte_disparo: Mapped[str | None] = mapped_column(Text)


class Trade(Base):
    """Um trade real: compras e vendas parciais de um papel, do usuario.

    So existe um trade aberto por ticker (`ux_trades_um_aberto_por_ticker`,
    indice unico parcial em `encerrado_em IS NULL`) -- historico de trades
    encerrados do mesmo papel convive sem problema, so nao dois em aberto.
    """

    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint(
            "encerrado_em IS NULL OR encerrado_em >= aberto_em",
            name="ck_trades_encerra_depois_de_abrir",
        ),
        Index(
            "ux_trades_um_aberto_por_ticker",
            "ticker",
            unique=True,
            postgresql_where=text("encerrado_em IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    aberto_em: Mapped[date] = mapped_column(Date, nullable=False)
    encerrado_em: Mapped[date | None] = mapped_column(Date)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TradeOperacao(Base):
    """Uma compra ou venda dentro de um trade, com o estado da posicao apos ela.

    Quem grava a operacao (o site, na fase 2) ja calculou preco medio, custo
    comprado e realizado e gravou nas colunas `*_apos` desta propria linha. O
    scanner NAO recalcula media: so le o estado da ultima operacao ate cada
    pregao para marcar a mercado. `ON DELETE CASCADE` porque uma operacao sem
    o trade que a contem nao tem sentido nenhum.
    """

    __tablename__ = "trade_operacoes"
    __table_args__ = (
        CheckConstraint("tipo IN ('compra', 'venda')", name="ck_trade_operacoes_tipo"),
        CheckConstraint("quantidade > 0", name="ck_trade_operacoes_quantidade_positiva"),
        CheckConstraint("preco > 0", name="ck_trade_operacoes_preco_positivo"),
        CheckConstraint(
            "quantidade_apos >= 0", name="ck_trade_operacoes_quantidade_apos_nao_negativa"
        ),
        Index("ix_trade_operacoes_trade_data", "trade_id", "data"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.trades.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    preco: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantidade_apos: Mapped[int] = mapped_column(Integer, nullable=False)
    preco_medio_apos: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    custo_comprado_apos: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    realizado_apos: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TradeSnapshot(Base):
    """Marcacao a mercado diaria de um trade -- a etapa noturna grava uma por pregao.

    Fica de fora da poda de `prune_bars`: e a razao desta tabela existir.
    `daily_bars` guarda so os ultimos 400 pregoes, e sem o snapshot a marcacao
    a mercado de um trade mais antigo desapareceria junto com as barras podadas.
    """

    __tablename__ = "trade_snapshots"
    __table_args__ = (
        CheckConstraint("quantidade >= 0", name="ck_trade_snapshots_quantidade_nao_negativa"),
    )

    trade_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.trades.id", ondelete="CASCADE"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    preco_medio: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    custo_comprado: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    realizado: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    # Mesma precisao de DailyBar.close: e de onde este valor vem.
    fechamento: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    valor_posicao: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    resultado: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    sem_negocio: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    gravado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Empresa(Base):
    """Empresa do cadastro da CVM que tem papel negociado no banco (fundamentos fase 1).

    Todos os campos vem do cadastro da CVM (`cad_cia_aberta.csv`). So entram
    empresas alcancadas por algum ticker de `daily_bars`, via
    `empresa_tickers`: a tabela nao guarda o cadastro inteiro, so a fatia que
    interessa ao scanner.

    `situacao` e o `SIT` do cadastro, guardado para exibicao. Empresa fora de
    ATIVO continua valendo: um papel em recuperacao ou saindo da bolsa ainda
    tem evento de volume e ficha no site.
    """

    __tablename__ = "empresas"

    cd_cvm: Mapped[int] = mapped_column(Integer, primary_key=True)
    cnpj: Mapped[str] = mapped_column(Text, nullable=False)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    nome_comercial: Mapped[str | None] = mapped_column(Text)
    setor_cvm: Mapped[str | None] = mapped_column(Text)
    situacao: Mapped[str | None] = mapped_column(Text)
    # Como a B3 chama a empresa nos endpoints dela (fundamentos fase 2). Vem do
    # detalhe da propria B3, nunca deduzido do ticker: a consulta de proventos
    # recentes so aceita `emissor_b3`, e a do historico so aceita `nome_pregao`.
    emissor_b3: Mapped[str | None] = mapped_column(Text)
    nome_pregao: Mapped[str | None] = mapped_column(Text)
    # Quando cada consulta a B3 foi feita, para nao repetir a mesma pergunta
    # todo dia: o detalhe e o historico mudam pouco, os recentes mudam sempre.
    detalhe_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proventos_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    historico_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EmpresaTicker(Base):
    """De qual empresa e cada ticker -- a ligacao entre o COTAHIST e a CVM.

    NAO se liga por prefixo do ticker. O codigo de emissor da B3 nem sempre e
    o prefixo: o emissor "EMBR" la e a EMBRAST, e nao a Embraer (que aparece
    como "EMBJ"), e ligar por prefixo colaria o balanco de uma empresa no
    papel de outra. A ligacao vem do FCA da CVM, que declara o codigo de
    negociacao de cada empresa (`fonte='fca'`), e, para o que o FCA nao cobre,
    de uma busca na B3 conferida contra os codigos que a propria B3 lista para
    aquela empresa (`fonte='b3'`).

    `cd_cvm` nulo e cache negativo: "ja procurei e nao achei". Sem ele, todo
    ticker sem empresa (um ETF, por exemplo) refaria a busca na B3 todo dia.
    """

    __tablename__ = "empresa_tickers"
    __table_args__ = (
        CheckConstraint("fonte IS NULL OR fonte IN ('fca', 'b3')", name="ck_empresa_tickers_fonte"),
        CheckConstraint(
            "(cd_cvm IS NULL) = (fonte IS NULL)", name="ck_empresa_tickers_fonte_com_empresa"
        ),
    )

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    cd_cvm: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.empresas.cd_cvm", ondelete="CASCADE")
    )
    fonte: Mapped[str | None] = mapped_column(Text)
    # ISIN e classe (ON, PN, PNA, UNT...) que a B3 declara para o papel. E o
    # que liga um provento ao ticker certo: a consulta de proventos recentes
    # identifica a acao pelo ISIN, e a do historico pela classe.
    isin: Mapped[str | None] = mapped_column(Text)
    classe: Mapped[str | None] = mapped_column(Text)
    verificado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Provento(Base):
    """Um provento em dinheiro de um papel: dividendo, JCP ou rendimento.

    Uma linha por provento POR PAPEL, porque o valor por acao e diferente em
    cada classe: em 05/12/2025 a Unipar pagou R$ 5,48 na ON e R$ 6,03 nas PN.

    Nao ha chave unica natural: um provento pago em parcelas aparece uma vez
    por parcela, com a mesma data com e o mesmo valor (visto na Iguatemi). A
    carga troca a janela inteira de datas que a B3 devolveu, em vez de tentar
    casar linha a linha.

    `fonte` diz de qual consulta a linha veio: 'recente' (ultimos ~12 meses,
    com data de pagamento) ou 'historico' (o resto, sem data de pagamento).
    """

    __tablename__ = "proventos"
    __table_args__ = (
        CheckConstraint("valor > 0", name="ck_proventos_valor_positivo"),
        CheckConstraint("fonte IN ('recente', 'historico')", name="ck_proventos_fonte"),
        Index("ix_proventos_ticker_data", "ticker", "data_com"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(
        Text, ForeignKey(f"{SCHEMA}.empresa_tickers.ticker", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    # Onze casas: a B3 publica o valor por acao com essa precisao, e truncar
    # mudaria o dividend yield de quem paga centavos por acao todo mes.
    valor: Mapped[Decimal] = mapped_column(Numeric(20, 11), nullable=False)
    # A data com e o que decide se o provento conta para quem tinha o papel:
    # e por ela que o yield de 12 meses e somado, nao pela data de pagamento.
    data_com: Mapped[date] = mapped_column(Date, nullable=False)
    data_aprovacao: Mapped[date | None] = mapped_column(Date)
    data_pagamento: Mapped[date | None] = mapped_column(Date)
    fonte: Mapped[str] = mapped_column(Text, nullable=False)
    carregado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CvmDocumento(Base):
    """Um documento (ITR ou DFP) entregue por uma empresa para uma data de referencia.

    A CVM reapresenta documentos: uma versao nova troca os numeros de uma
    versao antiga da mesma `dt_refer`. Aqui so fica o resumo das versoes
    (`versao`, `recebido_original`, `recebido_ultima`); os valores das contas
    ficam em `cvm_resultados` e `cvm_balancos`, sempre da versao mais recente
    -- a CVM so publica o documento de contas com a ultima versao, entao nao ha
    historico de valor por versao para guardar.
    """

    __tablename__ = "cvm_documentos"
    __table_args__ = (
        CheckConstraint("tipo IN ('ITR', 'DFP')", name="ck_cvm_documentos_tipo"),
        CheckConstraint("escopo IN ('con', 'ind')", name="ck_cvm_documentos_escopo"),
        CheckConstraint("layout IN ('geral', 'financeiro')", name="ck_cvm_documentos_layout"),
        CheckConstraint(
            "recebido_ultima >= recebido_original",
            name="ck_cvm_documentos_recebido_em_ordem",
        ),
    )

    cd_cvm: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.empresas.cd_cvm", ondelete="CASCADE"), primary_key=True
    )
    tipo: Mapped[str] = mapped_column(Text, primary_key=True)
    dt_refer: Mapped[date] = mapped_column(Date, primary_key=True)
    # Maior versao vista no indice da CVM para este (empresa, tipo, dt_refer).
    versao: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # DT_RECEB da primeira versao: quando o mercado soube pela primeira vez.
    recebido_original: Mapped[date] = mapped_column(Date, nullable=False)
    # DT_RECEB da versao vigente (a maior): quando os numeros atuais chegaram.
    recebido_ultima: Mapped[date] = mapped_column(Date, nullable=False)
    escopo: Mapped[str] = mapped_column(Text, nullable=False)
    layout: Mapped[str] = mapped_column(Text, nullable=False)
    id_doc: Mapped[int | None] = mapped_column(BigInteger)
    carregado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CvmResultado(Base):
    """Uma linha de DRE/DVA de um documento, por periodo reportado (tri ou acumulado).

    O ITR traz duas linhas por conta: o trimestre e o acumulado do ano (no 1T
    as duas coincidem). `dt_ini`/`dt_fim` sao o que distingue as duas -- por
    isso entram na chave primaria, e nao so `dt_refer`.
    """

    __tablename__ = "cvm_resultados"
    __table_args__ = (
        ForeignKeyConstraint(
            ["cd_cvm", "tipo", "dt_refer"],
            [
                f"{SCHEMA}.cvm_documentos.cd_cvm",
                f"{SCHEMA}.cvm_documentos.tipo",
                f"{SCHEMA}.cvm_documentos.dt_refer",
            ],
            ondelete="CASCADE",
        ),
        CheckConstraint("dt_ini <= dt_fim", name="ck_cvm_resultados_periodo_em_ordem"),
    )

    cd_cvm: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(Text, primary_key=True)
    dt_refer: Mapped[date] = mapped_column(Date, primary_key=True)
    dt_ini: Mapped[date] = mapped_column(Date, primary_key=True)
    dt_fim: Mapped[date] = mapped_column(Date, primary_key=True)
    receita: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    resultado_bruto: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    ebit: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    lucro_liquido: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    lucro_controladores: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    # Sinal como reportado: na DVA a D&A vem negativa. So existe na linha do
    # acumulado -- no trimestre fica NULL, porque a DVA do ITR so traz o
    # acumulado.
    depreciacao_amortizacao: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))


class CvmBalanco(Base):
    """Contas de saldo (BPA/BPP) e composicao do capital de um documento.

    Uma linha por documento -- BPA e BPP nao tem trimestre vs acumulado, so a
    posicao na data de referencia.
    """

    __tablename__ = "cvm_balancos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["cd_cvm", "tipo", "dt_refer"],
            [
                f"{SCHEMA}.cvm_documentos.cd_cvm",
                f"{SCHEMA}.cvm_documentos.tipo",
                f"{SCHEMA}.cvm_documentos.dt_refer",
            ],
            ondelete="CASCADE",
        ),
    )

    cd_cvm: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(Text, primary_key=True)
    dt_refer: Mapped[date] = mapped_column(Date, primary_key=True)
    ativo_total: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    ativo_circulante: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    caixa: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    aplicacoes_financeiras: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    passivo_circulante: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    # Como a CVM reporta: emprestimos_cp/lp INCLUEM o arrendamento.
    # arrendamento_* vem separado para a fase 3 poder tirar, se quiser.
    emprestimos_cp: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    arrendamento_cp: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    emprestimos_lp: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    arrendamento_lp: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    # Total, e INCLUI participacao de nao controladores.
    patrimonio_liquido: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    pl_nao_controladores: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    acoes_on: Mapped[int | None] = mapped_column(BigInteger)
    acoes_pn: Mapped[int | None] = mapped_column(BigInteger)
    tesouraria_on: Mapped[int | None] = mapped_column(BigInteger)
    tesouraria_pn: Mapped[int | None] = mapped_column(BigInteger)


class ArquivoExterno(Base):
    """Controle de download condicional dos arquivos da CVM (fundamentos fase 1).

    `etag`/`last_modified` sao os headers crus, reenviados como
    `If-None-Match`/`If-Modified-Since` na proxima checagem. `modificado_em` e
    o mesmo `Last-Modified` convertido para timestamp -- e a "data dos dados da
    CVM" que a ficha do papel mostra na fase 4, nao a data em que o scanner
    rodou. `escopo_hash` guarda contra qual lista de empresas o arquivo foi
    processado por ultimo: mudou a lista, um 304 nao basta mais.
    """

    __tablename__ = "arquivos_externos"

    url: Mapped[str] = mapped_column(Text, primary_key=True)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    modificado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escopo_hash: Mapped[str | None] = mapped_column(Text)
    verificado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
