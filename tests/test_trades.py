"""Marcacao a mercado dos trades reais (fase 1): funcao pura e persistencia.

A conta da posicao (preco medio, realizado) NAO e feita pelo Python -- quem
grava a operacao ja calcula e guarda nas colunas `*_apos`. Os fixtures abaixo
usam o exemplo de referencia da especificacao: compra 100 x 38,20, compra 50 x
37,60, venda 80 x 39,90 -> (qtd 70, pm 38,00, custo 5700, realizado 152,00).
Com fechamento 39,10, valor_posicao = 2737,00 e resultado = 229,00.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import Engine, delete, inspect, select
from sqlalchemy.exc import IntegrityError

from scanner.calendar import sessions_before
from scanner.storage.engine import session_scope
from scanner.storage.models import SCHEMA, DailyBar, Trade, TradeOperacao, TradeSnapshot
from scanner.storage.repository import gravar_snapshots, prune_bars
from scanner.trades import SNAPSHOT_COLUMNS, marcar_a_mercado, run_snapshots

PETR4 = "PETR4"


def _trades_df(**override: object) -> pd.DataFrame:
    linha: dict[str, object] = {
        "id": 1,
        "ticker": PETR4,
        "aberto_em": date(2024, 1, 2),
        "encerrado_em": None,
        "ultimo_snapshot": None,
    }
    linha.update(override)
    return pd.DataFrame([linha])


def _operacoes_df() -> pd.DataFrame:
    """As tres operacoes do exemplo de referencia da especificacao."""
    return pd.DataFrame(
        [
            {
                "id": 1,
                "trade_id": 1,
                "data": date(2024, 1, 2),
                "quantidade_apos": 100,
                "preco_medio_apos": Decimal("38.20"),
                "custo_comprado_apos": Decimal("3820.00"),
                "realizado_apos": Decimal("0.00"),
            },
            {
                "id": 2,
                "trade_id": 1,
                "data": date(2024, 1, 3),
                "quantidade_apos": 150,
                "preco_medio_apos": Decimal("38.00"),
                "custo_comprado_apos": Decimal("5700.00"),
                "realizado_apos": Decimal("0.00"),
            },
            {
                "id": 3,
                "trade_id": 1,
                "data": date(2024, 1, 4),
                "quantidade_apos": 70,
                "preco_medio_apos": Decimal("38.00"),
                "custo_comprado_apos": Decimal("5700.00"),
                "realizado_apos": Decimal("152.00"),
            },
        ]
    )


def _bars_df(closes: dict[date, float], ticker: str = PETR4) -> pd.DataFrame:
    return pd.DataFrame(
        {"ticker": ticker, "trade_date": list(closes.keys()), "close": list(closes.values())}
    )


REFERENCIA_BARS = {date(2024, 1, 2): 38.5, date(2024, 1, 3): 38.7, date(2024, 1, 4): 39.10}


# --- Funcao pura --------------------------------------------------------------


def test_marca_a_mercado_bate_o_exemplo_de_referencia() -> None:
    saida = marcar_a_mercado(
        _trades_df(), _operacoes_df(), _bars_df(REFERENCIA_BARS), date(2024, 1, 4)
    )

    assert list(saida.columns) == list(SNAPSHOT_COLUMNS)
    assert len(saida) == 3  # um snapshot por pregao entre a abertura e `ate`

    ultimo = saida[saida["trade_date"] == pd.Timestamp(2024, 1, 4)].iloc[0]
    assert ultimo["quantidade"] == 70
    assert float(ultimo["preco_medio"]) == pytest.approx(38.00)
    assert float(ultimo["custo_comprado"]) == pytest.approx(5700.00)
    assert float(ultimo["realizado"]) == pytest.approx(152.00)
    assert float(ultimo["fechamento"]) == pytest.approx(39.10)
    assert float(ultimo["valor_posicao"]) == pytest.approx(2737.00)
    assert float(ultimo["resultado"]) == pytest.approx(229.00)
    assert bool(ultimo["sem_negocio"]) is False


def test_estado_e_o_da_ultima_operacao_ate_cada_data() -> None:
    saida = marcar_a_mercado(
        _trades_df(), _operacoes_df(), _bars_df(REFERENCIA_BARS), date(2024, 1, 4)
    )

    primeiro = saida[saida["trade_date"] == pd.Timestamp(2024, 1, 2)].iloc[0]
    assert primeiro["quantidade"] == 100
    assert float(primeiro["preco_medio"]) == pytest.approx(38.20)
    assert float(primeiro["realizado"]) == pytest.approx(0.0)

    segundo = saida[saida["trade_date"] == pd.Timestamp(2024, 1, 3)].iloc[0]
    assert segundo["quantidade"] == 150
    assert float(segundo["preco_medio"]) == pytest.approx(38.00)


def test_desempate_por_id_quando_duas_operacoes_tem_a_mesma_data() -> None:
    operacoes = pd.DataFrame(
        [
            {
                "id": 5,
                "trade_id": 1,
                "data": date(2024, 1, 2),
                "quantidade_apos": 100,
                "preco_medio_apos": Decimal("10.00"),
                "custo_comprado_apos": Decimal("1000.00"),
                "realizado_apos": Decimal("0.00"),
            },
            {
                # Mesma data, id maior: e esta que vale.
                "id": 6,
                "trade_id": 1,
                "data": date(2024, 1, 2),
                "quantidade_apos": 150,
                "preco_medio_apos": Decimal("12.00"),
                "custo_comprado_apos": Decimal("1800.00"),
                "realizado_apos": Decimal("0.00"),
            },
        ]
    )
    saida = marcar_a_mercado(
        _trades_df(), operacoes, _bars_df({date(2024, 1, 2): 15.0}), date(2024, 1, 2)
    )

    assert len(saida) == 1
    assert saida.iloc[0]["quantidade"] == 150
    assert float(saida.iloc[0]["preco_medio"]) == pytest.approx(12.00)


def test_sem_negocio_usa_o_ultimo_fechamento_anterior() -> None:
    # AAAA3 negocia todo dia e cria os pregoes 02, 03 e 04; PETR4 fica sem
    # negocio no dia 03 e herda o fechamento do dia 02, com sem_negocio=True.
    petr4 = _bars_df({date(2024, 1, 2): 38.5, date(2024, 1, 4): 39.10})
    outro = _bars_df(
        {date(2024, 1, 2): 10.0, date(2024, 1, 3): 10.0, date(2024, 1, 4): 10.0}, ticker="AAAA3"
    )
    bars = pd.concat([petr4, outro], ignore_index=True)

    saida = marcar_a_mercado(_trades_df(), _operacoes_df(), bars, date(2024, 1, 4))

    dia_3 = saida[saida["trade_date"] == pd.Timestamp(2024, 1, 3)].iloc[0]
    assert bool(dia_3["sem_negocio"]) is True
    assert float(dia_3["fechamento"]) == pytest.approx(38.5)

    dia_4 = saida[saida["trade_date"] == pd.Timestamp(2024, 1, 4)].iloc[0]
    assert bool(dia_4["sem_negocio"]) is False


def test_sem_close_nenhum_ate_a_data_fica_sem_snapshot() -> None:
    # ZZZZ3 nunca teve barra: mesmo com operacao registrada, nao ha fechamento
    # para marcar, em nenhum pregao.
    trades = _trades_df(ticker="ZZZZ3")
    bars = _bars_df(
        {date(2024, 1, 2): 10.0, date(2024, 1, 3): 10.0, date(2024, 1, 4): 10.0}, ticker="AAAA3"
    )

    saida = marcar_a_mercado(trades, _operacoes_df(), bars, date(2024, 1, 4))

    assert saida.empty


def test_sem_operacao_ate_a_data_fica_sem_snapshot_nessa_data() -> None:
    # Trade aberto em 01/01, mas a primeira operacao so em 02/01: 01/01 nao
    # tem estado nenhum, entao nao vira linha.
    trades = _trades_df(aberto_em=date(2024, 1, 1))
    bars = _bars_df({date(2024, 1, 1): 38.0, **REFERENCIA_BARS})

    saida = marcar_a_mercado(trades, _operacoes_df(), bars, date(2024, 1, 4))

    assert pd.Timestamp(2024, 1, 1) not in set(saida["trade_date"])
    assert len(saida) == 3


def test_trade_encerrado_para_no_encerrado_em() -> None:
    trades = _trades_df(encerrado_em=date(2024, 1, 3))

    saida = marcar_a_mercado(trades, _operacoes_df(), _bars_df(REFERENCIA_BARS), date(2024, 1, 4))

    assert set(saida["trade_date"]) == {pd.Timestamp(2024, 1, 2), pd.Timestamp(2024, 1, 3)}


def test_ultimo_snapshot_pula_datas_ja_gravadas() -> None:
    trades = _trades_df(ultimo_snapshot=date(2024, 1, 3))

    saida = marcar_a_mercado(trades, _operacoes_df(), _bars_df(REFERENCIA_BARS), date(2024, 1, 4))

    assert list(saida["trade_date"]) == [pd.Timestamp(2024, 1, 4)]


def test_rodar_de_novo_ate_o_mesmo_dia_nao_gera_linha() -> None:
    # Simula uma segunda passada: ultimo_snapshot ja e o proprio `ate`.
    trades = _trades_df(ultimo_snapshot=date(2024, 1, 4))

    saida = marcar_a_mercado(trades, _operacoes_df(), _bars_df(REFERENCIA_BARS), date(2024, 1, 4))

    assert saida.empty
    assert list(saida.columns) == list(SNAPSHOT_COLUMNS)


def test_trade_aberto_depois_de_ate_nao_gera_nada() -> None:
    trades = _trades_df(aberto_em=date(2024, 1, 10))

    saida = marcar_a_mercado(trades, _operacoes_df(), _bars_df(REFERENCIA_BARS), date(2024, 1, 4))

    assert saida.empty


TRADES_COLS = ["id", "ticker", "aberto_em", "encerrado_em", "ultimo_snapshot"]
OPERACOES_COLS = [
    "id",
    "trade_id",
    "data",
    "quantidade_apos",
    "preco_medio_apos",
    "custo_comprado_apos",
    "realizado_apos",
]
BARS_COLS = ["ticker", "trade_date", "close"]


@pytest.mark.parametrize(
    "trades_vazio,operacoes_vazio,bars_vazio",
    [(True, False, False), (False, True, False), (False, False, True), (True, True, True)],
)
def test_entradas_vazias_devolvem_dataframe_vazio(
    trades_vazio: bool, operacoes_vazio: bool, bars_vazio: bool
) -> None:
    trades = pd.DataFrame(columns=TRADES_COLS) if trades_vazio else _trades_df()
    operacoes = pd.DataFrame(columns=OPERACOES_COLS) if operacoes_vazio else _operacoes_df()
    bars = pd.DataFrame(columns=BARS_COLS) if bars_vazio else _bars_df({date(2024, 1, 2): 38.5})

    saida = marcar_a_mercado(trades, operacoes, bars, date(2024, 1, 4))

    assert saida.empty
    assert list(saida.columns) == list(SNAPSHOT_COLUMNS)


# --- Persistencia ---------------------------------------------------------
#
# O banco de teste e criado uma vez e persiste entre rodadas do pytest (nao e
# recriado a cada execucao): cada helper limpa a sobra do proprio ticker antes
# de inserir, senao o indice unico de trade aberto rejeitaria a segunda rodada.


def _criar_trade(engine: Engine, ticker: str, *, encerrado_em: date | None = None) -> int:
    with session_scope(engine) as s:
        s.execute(delete(Trade).where(Trade.ticker == ticker))
    with session_scope(engine) as s:
        trade = Trade(ticker=ticker, aberto_em=date(2024, 1, 2), encerrado_em=encerrado_em)
        s.add(trade)
        s.flush()
        return int(trade.id)


def _operacao_compra(
    trade_id: int,
    *,
    data: date,
    quantidade: int,
    preco: str,
    quantidade_apos: int,
    pm_apos: str,
    custo_apos: str,
) -> TradeOperacao:
    return TradeOperacao(
        trade_id=trade_id,
        tipo="compra",
        data=data,
        quantidade=quantidade,
        preco=Decimal(preco),
        quantidade_apos=quantidade_apos,
        preco_medio_apos=Decimal(pm_apos),
        custo_comprado_apos=Decimal(custo_apos),
        realizado_apos=Decimal("0.00"),
    )


@pytest.mark.db
def test_tabelas_de_trades_existem(engine: Engine) -> None:
    nomes = set(inspect(engine).get_table_names(schema=SCHEMA))
    assert {"trades", "trade_operacoes", "trade_snapshots"} <= nomes


@pytest.mark.db
def test_segundo_trade_aberto_no_mesmo_ticker_viola_indice_unico(engine: Engine) -> None:
    ticker = "ZTRD3"
    _criar_trade(engine, ticker)
    with pytest.raises(IntegrityError), session_scope(engine) as s:
        s.add(Trade(ticker=ticker, aberto_em=date(2024, 2, 1)))


@pytest.mark.db
def test_apagar_trade_apaga_operacoes_e_snapshots(engine: Engine) -> None:
    ticker = "ZCSC3"
    trade_id = _criar_trade(engine, ticker)
    with session_scope(engine) as s:
        s.add(
            _operacao_compra(
                trade_id,
                data=date(2024, 1, 2),
                quantidade=100,
                preco="10.00",
                quantidade_apos=100,
                pm_apos="10.000000",
                custo_apos="1000.00",
            )
        )
        s.add(
            TradeSnapshot(
                trade_id=trade_id,
                trade_date=date(2024, 1, 2),
                quantidade=100,
                preco_medio=Decimal("10.000000"),
                custo_comprado=Decimal("1000.00"),
                realizado=Decimal("0.00"),
                fechamento=Decimal("10.5000"),
                valor_posicao=Decimal("1050.00"),
                resultado=Decimal("50.00"),
            )
        )

    with session_scope(engine) as s:
        s.execute(delete(Trade).where(Trade.id == trade_id))

    with engine.connect() as conn:
        assert (
            conn.execute(select(TradeOperacao).where(TradeOperacao.trade_id == trade_id)).first()
            is None
        )
        assert (
            conn.execute(select(TradeSnapshot).where(TradeSnapshot.trade_id == trade_id)).first()
            is None
        )


@pytest.mark.db
def test_gravar_snapshots_e_upsert(engine: Engine) -> None:
    ticker = "ZUPS3"
    trade_id = _criar_trade(engine, ticker)
    frame = pd.DataFrame(
        [
            {
                "trade_id": trade_id,
                "trade_date": date(2024, 1, 2),
                "quantidade": 100,
                "preco_medio": 10.0,
                "custo_comprado": 1000.0,
                "realizado": 0.0,
                "fechamento": 10.5,
                "valor_posicao": 1050.0,
                "resultado": 50.0,
                "sem_negocio": False,
            }
        ]
    )
    assert gravar_snapshots(engine, frame) == 1

    frame2 = frame.copy()
    frame2.loc[0, ["fechamento", "valor_posicao", "resultado"]] = [11.0, 1100.0, 100.0]
    assert gravar_snapshots(engine, frame2) == 1

    with engine.connect() as conn:
        linhas = conn.execute(select(TradeSnapshot).where(TradeSnapshot.trade_id == trade_id)).all()
    assert len(linhas) == 1
    assert float(linhas[0].fechamento) == pytest.approx(11.0)
    assert float(linhas[0].resultado) == pytest.approx(100.0)


@pytest.mark.db
def test_gravar_snapshots_vazio_nao_faz_nada(engine: Engine) -> None:
    assert gravar_snapshots(engine, pd.DataFrame(columns=list(SNAPSHOT_COLUMNS))) == 0


@pytest.mark.db
def test_run_snapshots_ponta_a_ponta_e_idempotente(engine: Engine) -> None:
    ticker = "ZRUN3"
    trade_id = _criar_trade(engine, ticker)
    with session_scope(engine) as s:
        s.add(
            _operacao_compra(
                trade_id,
                data=date(2024, 1, 2),
                quantidade=100,
                preco="38.20",
                quantidade_apos=100,
                pm_apos="38.200000",
                custo_apos="3820.00",
            )
        )

    bars = _bars_df({date(2024, 1, 2): 39.0}, ticker=ticker)
    relatorio = run_snapshots(engine, date(2024, 1, 2), bars=bars)

    assert relatorio.trades == 1
    assert relatorio.snapshots == 1
    assert relatorio.dry_run is False
    assert (
        relatorio.summary() == "trades: 1 marcados a mercado, 1 snapshots gravados ate 2024-01-02"
    )

    with engine.connect() as conn:
        linhas = conn.execute(select(TradeSnapshot).where(TradeSnapshot.trade_id == trade_id)).all()
    assert len(linhas) == 1
    assert linhas[0].quantidade == 100

    # Rodar de novo para o mesmo pregao nao gera linha nova: ultimo_snapshot
    # ja e 2024-01-02, entao nao ha data nova a marcar.
    outra_vez = run_snapshots(engine, date(2024, 1, 2), bars=bars)
    assert outra_vez.trades == 0
    assert outra_vez.snapshots == 0
    assert outra_vez.summary() == "trades: nenhum snapshot novo"

    with engine.connect() as conn:
        total = conn.execute(select(TradeSnapshot).where(TradeSnapshot.trade_id == trade_id)).all()
    assert len(total) == 1


@pytest.mark.db
def test_run_snapshots_dry_run_nao_grava(engine: Engine) -> None:
    ticker = "ZDRY3"
    trade_id = _criar_trade(engine, ticker)
    with session_scope(engine) as s:
        s.add(
            _operacao_compra(
                trade_id,
                data=date(2024, 1, 2),
                quantidade=50,
                preco="20.00",
                quantidade_apos=50,
                pm_apos="20.000000",
                custo_apos="1000.00",
            )
        )

    bars = _bars_df({date(2024, 1, 2): 21.0}, ticker=ticker)
    relatorio = run_snapshots(engine, date(2024, 1, 2), bars=bars, dry_run=True)

    assert relatorio.trades == 1
    assert relatorio.snapshots == 1
    assert relatorio.summary().startswith("[dry-run]")
    assert "nao gravados" in relatorio.summary()

    with engine.connect() as conn:
        linhas = conn.execute(select(TradeSnapshot).where(TradeSnapshot.trade_id == trade_id)).all()
    assert linhas == []


@pytest.mark.db
def test_run_snapshots_bars_vazias_nao_faz_nada(engine: Engine) -> None:
    relatorio = run_snapshots(engine, date(2024, 1, 2), bars=pd.DataFrame(columns=BARS_COLS))
    assert relatorio.trades == 0
    assert relatorio.snapshots == 0
    assert relatorio.summary() == "trades: nenhum snapshot novo"


@pytest.mark.db
def test_prune_bars_nao_apaga_snapshots(engine: Engine) -> None:
    # As barras de um papel qualquer, o bastante para a poda ter o que cortar.
    ticker_barras = "ZPRU3"
    ticker_trade = "ZPRT3"
    dias = sessions_before(date(2026, 6, 30), 15, inclusive=True)

    with session_scope(engine) as s:
        s.execute(delete(DailyBar).where(DailyBar.ticker == ticker_barras))
        s.add_all(
            [
                DailyBar(
                    ticker=ticker_barras,
                    trade_date=dia,
                    close=10.0,
                    volume_financial=1_000_000.0,
                    volume_shares=10_000,
                    trades_count=10,
                    trades_censored=False,
                )
                for dia in dias
            ]
        )

    trade_id = _criar_trade(engine, ticker_trade)
    with session_scope(engine) as s:
        s.add(
            TradeSnapshot(
                trade_id=trade_id,
                trade_date=dias[0],  # o pregao mais antigo, que a poda vai deixar para tras
                quantidade=10,
                preco_medio=Decimal("10.000000"),
                custo_comprado=Decimal("100.00"),
                realizado=Decimal("0.00"),
                fechamento=Decimal("10.0000"),
                valor_posicao=Decimal("100.00"),
                resultado=Decimal("0.00"),
            )
        )

    try:
        poda = prune_bars(engine, 5)
        assert poda.barras > 0

        with engine.connect() as conn:
            restante = conn.execute(
                select(TradeSnapshot).where(TradeSnapshot.trade_id == trade_id)
            ).first()
        assert restante is not None
    finally:
        with session_scope(engine) as s:
            s.execute(delete(DailyBar).where(DailyBar.ticker == ticker_barras))
