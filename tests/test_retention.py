"""Retencao dos ultimos N pregoes (secao 5 do plano) e o workflow diario."""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import Engine, delete, select

from scanner.calendar import sessions_before
from scanner.storage.engine import session_scope
from scanner.storage.models import DailyBar, DailyFeature, Event, VolumeMetric
from scanner.storage.repository import (
    count_bars,
    prune_bars,
    retention_cutoff,
    sessions_stored,
    upsert_metrics,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "daily.yml"

FIM = date(2026, 6, 30)
SESSOES = 50
TICKER = "ZRET3"


@pytest.fixture
def carga(engine: Engine) -> Iterator[list[date]]:
    """50 pregoes de um papel, com metrica e um evento antigo."""
    dias = sessions_before(FIM, SESSOES, inclusive=True)
    with session_scope(engine) as s:
        s.execute(delete(Event).where(Event.ticker == TICKER))
        s.execute(delete(VolumeMetric).where(VolumeMetric.ticker == TICKER))
        s.execute(delete(DailyBar).where(DailyBar.ticker == TICKER))
        s.add_all(
            [
                DailyBar(
                    ticker=TICKER,
                    trade_date=dia,
                    close=10.0,
                    volume_financial=1_000_000 * (1 + 0.1 * math.sin(i)),
                    volume_shares=100_000,
                    trades_count=300,
                    trades_censored=False,
                )
                for i, dia in enumerate(dias)
            ]
        )
        # Um evento no pregao mais antigo, que a poda vai deixar para tras.
        s.add(
            Event(
                ticker=TICKER,
                trade_date=dias[0],
                max_z_log=7.5,
                triggered_windows=[30],
                volume_financial=9_000_000,
                features={"ret_day": 0.1},
            )
        )
    yield dias
    with session_scope(engine) as s:
        s.execute(delete(Event).where(Event.ticker == TICKER))
        s.execute(delete(DailyFeature).where(DailyFeature.ticker == TICKER))
        s.execute(delete(VolumeMetric).where(VolumeMetric.ticker == TICKER))
        s.execute(delete(DailyBar).where(DailyBar.ticker == TICKER))


pytestmark = pytest.mark.db


def test_retention_cutoff_aponta_o_primeiro_pregao_mantido(
    engine: Engine, carga: list[date]
) -> None:
    assert retention_cutoff(engine, 10) == carga[-10]


def test_sem_pregoes_suficientes_nao_poda(engine: Engine, carga: list[date]) -> None:
    antes = count_bars(engine)
    assert prune_bars(engine, SESSOES + 100) == (0, 0)
    assert count_bars(engine) == antes


def test_poda_deixa_exatamente_a_janela_pedida(engine: Engine, carga: list[date]) -> None:
    prune_bars(engine, 20)
    assert sessions_stored(engine) == 20
    with engine.connect() as conn:
        restantes = set(conn.execute(select(DailyBar.trade_date).distinct()).scalars())
    assert restantes == set(carga[-20:])


def test_poda_leva_as_metricas_junto(engine: Engine, carga: list[date]) -> None:
    import pandas as pd

    metricas = pd.DataFrame(
        {
            "ticker": TICKER,
            "trade_date": carga,
            "window_size": 30,
            "z_log": 1.0,
            "z_raw": 1.0,
            "z_robust": 1.0,
            "rvol": 1.0,
        }
    )
    upsert_metrics(engine, metricas)

    _, removidas = prune_bars(engine, 20)
    assert removidas == SESSOES - 20
    with engine.connect() as conn:
        sobraram = conn.execute(
            select(VolumeMetric.trade_date).where(VolumeMetric.ticker == TICKER)
        ).scalars()
        assert min(sobraram) == carga[-20]


def test_poda_nunca_apaga_evento(engine: Engine, carga: list[date]) -> None:
    # A ficha do papel marca eventos antigos mesmo quando as barras ja sairam.
    prune_bars(engine, 5)
    with engine.connect() as conn:
        eventos = conn.execute(select(Event).where(Event.ticker == TICKER)).all()
    assert len(eventos) == 1


def test_keep_invalido_falha_alto(engine: Engine) -> None:
    with pytest.raises(ValueError, match="ao menos 1"):
        prune_bars(engine, 0)


# --- Workflow diario ---------------------------------------------------------


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    if not WORKFLOW.is_file():
        pytest.skip("daily.yml ainda nao esta no repositorio (falta o escopo workflow no gh)")
    return dict(yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    "comando",
    [
        "alembic upgrade head",
        "scanner ingest daily",
        "scanner metrics compute --mode incremental",
        "scanner scan",
        "scanner db prune",
    ],
)
def test_workflow_roda_o_pipeline_completo(workflow: dict[Any, Any], comando: str) -> None:
    assert comando in WORKFLOW.read_text(encoding="utf-8")


def test_workflow_roda_em_dia_util_as_21h_utc(workflow: dict[Any, Any]) -> None:
    # A chave `on` do YAML e lida como booleano True por ser "on".
    gatilhos = workflow.get("on") or workflow.get(True)
    assert isinstance(gatilhos, dict)
    assert gatilhos["schedule"] == [{"cron": "0 21 * * 1-5"}]
    assert "workflow_dispatch" in gatilhos


def test_workflow_le_os_segredos_pelos_nomes_certos(workflow: dict[Any, Any]) -> None:
    texto = WORKFLOW.read_text(encoding="utf-8")
    for nome in (
        "SCANNER_DATABASE_URL",
        "SCANNER_TELEGRAM_BOT_TOKEN",
        "SCANNER_TELEGRAM_CHAT_ID",
    ):
        assert f"secrets.{nome}" in texto, f"{nome} nao vem de secrets"
    # Nenhum valor de segredo pode estar escrito no arquivo.
    assert "postgresql://" not in texto
    assert "api.telegram.org" not in texto


def test_guarda_impede_teste_de_abrir_o_banco_de_trabalho() -> None:
    """A guarda que fecha o buraco que ja apagou metricas de producao duas vezes.

    Se este teste parar de levantar erro, um teste distraido volta a poder
    truncar a tabela de metricas do banco real.
    """
    from scanner.storage.engine import build_engine

    with pytest.raises(RuntimeError, match="banco de trabalho"):
        build_engine()
