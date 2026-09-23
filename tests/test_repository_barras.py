"""A leitura das barras por COPY tem de devolver o que o `read_sql` devolvia.

O `load_bars` trocou `pd.read_sql` por `COPY ... TO STDOUT` por desempenho. A
troca so vale se o DataFrame sair identico -- o calculo inteiro do pregao vem
dele. Estes testes leem a MESMA tabela pelos dois caminhos e exigem igualdade
coluna por coluna, tipo por tipo.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import Engine, delete, select

from scanner.storage.engine import session_scope
from scanner.storage.models import DailyBar
from scanner.storage.repository import BARRAS_DO_CALCULO, load_bars

TICKERS = ("ZCPY3", "ZCPY4")
DIAS = (date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4))


def _pelo_read_sql(engine: Engine, *, since: date | None = None) -> pd.DataFrame:
    """O `load_bars` como era antes do COPY, para servir de referencia."""
    stmt = select(*(getattr(DailyBar, nome) for nome in BARRAS_DO_CALCULO))
    if since is not None:
        stmt = stmt.where(DailyBar.trade_date >= since)
    with engine.connect() as conn:
        frame = pd.read_sql(stmt, conn)
    for coluna in ("open", "high", "low", "close", "avg_price", "volume_financial"):
        frame[coluna] = pd.to_numeric(frame[coluna], errors="coerce").astype(float)
    return frame


def _ordenado(frame: pd.DataFrame) -> pd.DataFrame:
    """A ordem das linhas nao e garantida por nenhum dos dois caminhos."""
    return frame.sort_values(["ticker", "trade_date"]).reset_index(drop=True)


@pytest.fixture
def barras(engine: Engine) -> Iterator[None]:
    """Seis barras, com nulo em `avg_price` e em `trades_count`.

    Os nulos nao sao enfeite: o COPY em CSV escreve nulo como campo vazio, e
    coluna inteira com nulo muda de tipo. Sem uma linha assim, o teste passaria
    sem tocar no caso que quebra.
    """
    with session_scope(engine) as s:
        s.execute(delete(DailyBar).where(DailyBar.ticker.in_(TICKERS)))
        for ticker in TICKERS:
            for i, dia in enumerate(DIAS):
                vazio = ticker == TICKERS[1] and i == 1
                s.add(
                    DailyBar(
                        ticker=ticker,
                        trade_date=dia,
                        open=10.10 + i,
                        high=11.25 + i,
                        low=9.05 + i,
                        close=10.75 + i,
                        avg_price=None if vazio else 10.4321,
                        volume_shares=1_000_000 + i,
                        volume_financial=12_345_678.90 + i,
                        trades_count=None if vazio else 4_321,
                        trades_censored=i == 2,
                    )
                )
    yield
    with session_scope(engine) as s:
        s.execute(delete(DailyBar).where(DailyBar.ticker.in_(TICKERS)))


@pytest.mark.db
def test_copy_devolve_o_mesmo_que_read_sql(engine: Engine, barras: None) -> None:
    """Igualdade exata: valores, tipos e nomes de coluna."""
    pd.testing.assert_frame_equal(_ordenado(load_bars(engine)), _ordenado(_pelo_read_sql(engine)))


@pytest.mark.db
def test_copy_respeita_o_corte_de_since(engine: Engine, barras: None) -> None:
    """O `since` e parametro do COPY, nao texto interpolado na consulta."""
    corte = DIAS[1]
    pelo_copy = _ordenado(load_bars(engine, since=corte))
    pd.testing.assert_frame_equal(pelo_copy, _ordenado(_pelo_read_sql(engine, since=corte)))
    assert set(pelo_copy["trade_date"]) == {DIAS[1], DIAS[2]}


@pytest.mark.db
def test_trade_date_continua_sendo_date(engine: Engine, barras: None) -> None:
    """`date`, e nao `Timestamp`: o pipeline compara com `datetime.date`."""
    frame = load_bars(engine)
    assert all(isinstance(v, date) and not isinstance(v, pd.Timestamp) for v in frame["trade_date"])


@pytest.mark.db
def test_trades_censored_volta_a_ser_booleano(engine: Engine, barras: None) -> None:
    """O COPY escreve "t"/"f"; o cast para int e de volta a bool desfaz isso."""
    frame = load_bars(engine)
    assert frame["trades_censored"].dtype == bool
    assert frame["trades_censored"].sum() == len(TICKERS)


@pytest.mark.db
def test_volume_shares_ficou_de_fora(engine: Engine, barras: None) -> None:
    """Nenhuma etapa do calculo a le; sao 140 mil valores a menos no fio."""
    assert "volume_shares" not in load_bars(engine).columns
    assert "volume_shares" not in BARRAS_DO_CALCULO


@pytest.mark.db
def test_banco_sem_barra_nenhuma_devolve_as_colunas(engine: Engine) -> None:
    """Frame vazio ainda precisa ter as colunas: o calculo indexa por nome."""
    with session_scope(engine) as s:
        s.execute(delete(DailyBar))
    frame = load_bars(engine)
    assert frame.empty
    assert list(frame.columns) == list(BARRAS_DO_CALCULO)
