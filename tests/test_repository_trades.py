"""`trades_do_pregao`: posicao dos trades reais que alimenta o resumo (fase 3).

So existe contra o banco: a regra depende de um JOIN e de uma condicao sobre
duas datas (`trade_date` do snapshot e `encerrado_em` do trade), e isso nao vale
a pena simular em memoria quando ha um Postgres de teste isolado logo ali.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Engine, delete

from scanner.storage.engine import session_scope
from scanner.storage.models import Trade, TradeSnapshot
from scanner.storage.repository import trades_do_pregao

DIA = date(2026, 9, 15)
ANTES = date(2026, 9, 14)


def _trade(engine: Engine, ticker: str, *, encerrado_em: date | None = None) -> int:
    """Cria o trade, limpando qualquer sobra do mesmo ticker de uma rodada anterior.

    O banco de teste persiste entre execucoes (ver `tests/conftest.py`), e o
    indice unico de trade aberto rejeitaria uma segunda rodada sem isto.
    """
    with session_scope(engine) as s:
        s.execute(delete(Trade).where(Trade.ticker == ticker))
    with session_scope(engine) as s:
        trade = Trade(ticker=ticker, aberto_em=ANTES, encerrado_em=encerrado_em)
        s.add(trade)
        s.flush()
        return int(trade.id)


def _snapshot(trade_id: int, trade_date: date, **override: object) -> TradeSnapshot:
    base: dict[str, object] = {
        "trade_id": trade_id,
        "trade_date": trade_date,
        "quantidade": 70,
        "preco_medio": Decimal("38.000000"),
        "custo_comprado": Decimal("5700.00"),
        "realizado": Decimal("152.00"),
        "fechamento": Decimal("39.1000"),
        "valor_posicao": Decimal("2737.00"),
        "resultado": Decimal("229.00"),
    }
    base.update(override)
    return TradeSnapshot(**base)  # type: ignore[arg-type]


@pytest.mark.db
def test_trade_aberto_entra(engine: Engine) -> None:
    trade_id = _trade(engine, "ZTDP1")
    with session_scope(engine) as s:
        s.add(_snapshot(trade_id, DIA))

    linha = trades_do_pregao(engine, DIA).set_index("ticker").loc["ZTDP1"]
    assert bool(linha["encerrado"]) is False
    assert int(linha["quantidade"]) == 70
    assert float(linha["resultado"]) == pytest.approx(229.00)
    assert float(linha["custo_comprado"]) == pytest.approx(5700.00)


@pytest.mark.db
def test_encerrado_no_dia_entra_marcado(engine: Engine) -> None:
    trade_id = _trade(engine, "ZTDP2", encerrado_em=DIA)
    with session_scope(engine) as s:
        s.add(_snapshot(trade_id, DIA, quantidade=0))

    linha = trades_do_pregao(engine, DIA).set_index("ticker").loc["ZTDP2"]
    assert bool(linha["encerrado"]) is True


@pytest.mark.db
def test_encerrado_antes_nao_entra_mesmo_com_snapshot_no_dia(engine: Engine) -> None:
    # Snapshot em DIA nao deveria existir na pratica para um trade que ja
    # fechou antes, mas a regra e sobre `encerrado_em`, nao sobre o snapshot.
    trade_id = _trade(engine, "ZTDP3", encerrado_em=ANTES)
    with session_scope(engine) as s:
        s.add(_snapshot(trade_id, DIA))

    assert "ZTDP3" not in set(trades_do_pregao(engine, DIA)["ticker"])


@pytest.mark.db
def test_sem_snapshot_no_dia_nao_entra(engine: Engine) -> None:
    trade_id = _trade(engine, "ZTDP4")
    with session_scope(engine) as s:
        s.add(_snapshot(trade_id, ANTES))

    assert "ZTDP4" not in set(trades_do_pregao(engine, DIA)["ticker"])


@pytest.mark.db
def test_ordem_abertos_antes_dos_encerrados_cada_grupo_por_ticker(engine: Engine) -> None:
    aberto_b = _trade(engine, "ZTDPB")
    aberto_a = _trade(engine, "ZTDPA")
    encerrado_d = _trade(engine, "ZTDPD", encerrado_em=DIA)
    encerrado_c = _trade(engine, "ZTDPC", encerrado_em=DIA)
    with session_scope(engine) as s:
        for trade_id in (aberto_b, aberto_a, encerrado_d, encerrado_c):
            s.add(_snapshot(trade_id, DIA))

    tickers = ("ZTDPA", "ZTDPB", "ZTDPC", "ZTDPD")
    frame = trades_do_pregao(engine, DIA)
    ordem = list(frame[frame["ticker"].isin(tickers)]["ticker"])
    assert ordem == ["ZTDPA", "ZTDPB", "ZTDPC", "ZTDPD"]


@pytest.mark.db
def test_colunas_da_saida(engine: Engine) -> None:
    trade_id = _trade(engine, "ZTDP5")
    with session_scope(engine) as s:
        s.add(_snapshot(trade_id, DIA))

    frame = trades_do_pregao(engine, DIA)
    esperadas = {"ticker", "quantidade", "resultado", "custo_comprado", "encerrado"}
    assert set(frame.columns) == esperadas
