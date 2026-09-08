"""Orquestracao do recalculo, contra o Postgres local."""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import Engine, delete

from scanner.calendar import sessions_before
from scanner.config import AlertConfig, ScannerConfig
from scanner.recompute import refresh_metrics, ticker_history
from scanner.storage.engine import session_scope
from scanner.storage.models import DailyBar, VolumeMetric

pytestmark = pytest.mark.db

TICKERS = ("ZQA3", "ZQB4")
FIM = date(2026, 6, 30)
CONFIG = ScannerConfig(alert=AlertConfig(windows=[30]))


@pytest.fixture
def carga(engine: Engine) -> Iterator[list[str]]:
    """Insere dois papeis sinteticos e limpa no fim."""
    dias = sessions_before(FIM, 40, inclusive=True)
    linhas = [
        DailyBar(
            ticker=t,
            trade_date=d,
            open=10.0,
            high=11.0,
            low=9.0,
            close=10.0,
            avg_price=10.0,
            volume_shares=100_000,
            volume_financial=1_000_000 * (1 + 0.1 * math.sin(i)),
            trades_count=500,
            trades_censored=False,
        )
        for t in TICKERS
        for i, d in enumerate(dias)
    ]
    with session_scope(engine) as s:
        s.add_all(linhas)
    yield list(TICKERS)
    with session_scope(engine) as s:
        s.execute(delete(VolumeMetric).where(VolumeMetric.ticker.in_(TICKERS)))
        s.execute(delete(DailyBar).where(DailyBar.ticker.in_(TICKERS)))


def test_modo_invalido_falha_alto(engine: Engine) -> None:
    with pytest.raises(ValueError, match="incremental"):
        refresh_metrics(engine, CONFIG, mode="turbo")


def test_full_calcula_e_grava(engine: Engine, carga: list[str]) -> None:
    relatorio = refresh_metrics(engine, CONFIG, mode="full")
    assert relatorio.mode == "full"
    assert relatorio.rows_written == relatorio.rows_computed
    assert relatorio.rows_written > 0
    assert "metricas calculadas" in relatorio.summary()


def test_full_e_idempotente(engine: Engine, carga: list[str]) -> None:
    primeiro = refresh_metrics(engine, CONFIG, mode="full")
    segundo = refresh_metrics(engine, CONFIG, mode="full")
    assert primeiro.rows_computed == segundo.rows_computed
    assert primeiro.last_written == segundo.last_written


def test_incremental_grava_menos_que_full(engine: Engine, carga: list[str]) -> None:
    cheio = refresh_metrics(engine, CONFIG, mode="full")
    incremental = refresh_metrics(engine, CONFIG, mode="incremental")
    assert incremental.rows_computed == cheio.rows_computed
    assert incremental.rows_written < cheio.rows_written


def test_ticker_history_traz_metrica_e_contexto(engine: Engine, carga: list[str]) -> None:
    linhas = ticker_history(engine, "ZQA3", 30, limit=5)
    assert len(linhas) == 5
    assert {"z_log", "rvol", "avg_ticket", "ret_day"} <= set(linhas.columns)
    assert bool(linhas["z_log"].notna().any())
    assert linhas["trade_date"].is_monotonic_increasing


def test_ticker_history_de_papel_inexistente_e_vazio(engine: Engine) -> None:
    assert ticker_history(engine, "NAOEXISTE9", 30).empty


def test_ticker_history_aceita_minusculo(engine: Engine, carga: list[str]) -> None:
    assert not ticker_history(engine, "zqa3", 30, limit=3).empty


def test_metricas_gravadas_batem_com_o_calculo(engine: Engine, carga: list[str]) -> None:
    refresh_metrics(engine, CONFIG, mode="full")
    with engine.connect() as conn:
        gravado = pd.read_sql(
            "SELECT ticker, trade_date, window_size, z_log FROM volume_scanner.volume_metrics "
            "WHERE ticker = 'ZQA3' ORDER BY trade_date",
            conn,
        )
    assert len(gravado) > 0
    assert set(gravado["window_size"]) == {30}
