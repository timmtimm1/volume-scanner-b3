"""Persistencia do contexto da secao 3.2 para todo pregao avaliado."""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import Engine, delete, select

from scanner.calendar import sessions_before
from scanner.config import AlertConfig, ScannerConfig
from scanner.features import FEATURE_COLUMNS
from scanner.recompute import refresh_metrics
from scanner.storage.engine import session_scope
from scanner.storage.models import DailyBar, DailyFeature, VolumeMetric
from scanner.storage.repository import count_features, upsert_features

pytestmark = pytest.mark.db

FIM = date(2026, 6, 30)
SESSOES = 60
TICKERS = ("ZFT3", "ZFT4")
CONFIG = ScannerConfig(alert=AlertConfig(windows=[30]))


@pytest.fixture
def carga(engine: Engine) -> Iterator[list[date]]:
    dias = sessions_before(FIM, SESSOES, inclusive=True)
    with session_scope(engine) as s:
        s.add_all(
            [
                DailyBar(
                    ticker=t,
                    trade_date=dia,
                    open=10.0,
                    high=10.6,
                    low=9.4,
                    close=10.0 + (i % 7) * 0.1,
                    avg_price=10.1,
                    volume_shares=100_000,
                    volume_financial=1_000_000 * (1 + 0.1 * math.sin(i)),
                    trades_count=400,
                    trades_censored=False,
                )
                for t in TICKERS
                for i, dia in enumerate(dias)
            ]
        )
    yield dias
    with session_scope(engine) as s:
        s.execute(delete(DailyFeature).where(DailyFeature.ticker.in_(TICKERS)))
        s.execute(delete(VolumeMetric).where(VolumeMetric.ticker.in_(TICKERS)))
        s.execute(delete(DailyBar).where(DailyBar.ticker.in_(TICKERS)))


def test_recalculo_grava_contexto(engine: Engine, carga: list[date]) -> None:
    relatorio = refresh_metrics(engine, CONFIG, mode="full")
    assert relatorio.features_written > 0
    assert "linhas de contexto" in relatorio.summary()


def test_contexto_existe_para_linha_que_nao_virou_evento(engine: Engine, carga: list[date]) -> None:
    # E a razao da tabela existir: sem spike nenhum, nada aqui cruza o limiar,
    # e mesmo assim a tela precisa de contexto para essas linhas.
    refresh_metrics(engine, CONFIG, mode="full")
    with engine.connect() as conn:
        linhas = conn.execute(select(DailyFeature).where(DailyFeature.ticker == "ZFT3")).all()
    assert linhas, "sem contexto gravado para papel que nunca cruzou o limiar"


def test_chaves_do_json_sao_as_features_da_secao_3_2(engine: Engine, carga: list[date]) -> None:
    refresh_metrics(engine, CONFIG, mode="full")
    with engine.connect() as conn:
        guardado = conn.execute(
            select(DailyFeature.features).where(DailyFeature.ticker == "ZFT3").limit(1)
        ).scalar_one()
    assert set(guardado) == set(FEATURE_COLUMNS)


def test_recalculo_e_idempotente(engine: Engine, carga: list[date]) -> None:
    refresh_metrics(engine, CONFIG, mode="full")
    antes = count_features(engine)
    refresh_metrics(engine, CONFIG, mode="full")
    assert count_features(engine) == antes


def test_linha_sem_nenhuma_feature_nao_e_gravada(engine: Engine) -> None:
    # Papel novo demais para ter qualquer janela: uma linha de nulos so ocuparia
    # espaco e apareceria vazia na tela.
    vazia = pd.DataFrame(
        {
            "ticker": ["ZNADA3"],
            "trade_date": [FIM],
            **{c: [float("nan")] for c in FEATURE_COLUMNS},
        }
    )
    assert upsert_features(engine, vazia) == 0


def test_nan_vira_null_no_json(engine: Engine) -> None:
    parcial = pd.DataFrame(
        {
            "ticker": ["ZPARC3"],
            "trade_date": [FIM],
            **{c: [float("nan")] for c in FEATURE_COLUMNS},
        }
    )
    parcial["ret_day"] = 0.05
    try:
        assert upsert_features(engine, parcial) == 1
        with engine.connect() as conn:
            guardado = conn.execute(
                select(DailyFeature.features).where(DailyFeature.ticker == "ZPARC3")
            ).scalar_one()
        assert guardado["ret_day"] == pytest.approx(0.05)
        assert guardado["pos252"] is None
    finally:
        with session_scope(engine) as s:
            s.execute(delete(DailyFeature).where(DailyFeature.ticker == "ZPARC3"))


def test_sem_features_devolve_zero(engine: Engine) -> None:
    assert upsert_features(engine, pd.DataFrame()) == 0
