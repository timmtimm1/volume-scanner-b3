"""Regra de alerta e dedupe.

O criterio de aceite da F4 esta em `test_spike_de_20x_dispara_um_alerta_completo`.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import Engine, delete

from scanner.alerts import alert_payload, count_below_floor, run_scan, select_events
from scanner.calendar import sessions_before
from scanner.config import AlertConfig, ScannerConfig
from scanner.features import FEATURE_COLUMNS, compute_features
from scanner.metrics import compute_zscores
from scanner.notify.telegram import ConsoleNotifier
from scanner.storage.engine import session_scope
from scanner.storage.models import Event
from scanner.storage.repository import insert_events, mark_notified, pending_events

# Historico longo o bastante para pos252 existir: sem 252 pregoes anteriores,
# "todas as features preenchidas" seria inalcancavel.
SESSOES = 280
FIM = date(2026, 6, 30)
JANELAS = [30, 45, 60]
CONFIG = ScannerConfig(alert=AlertConfig(windows=JANELAS, threshold=6.0, min_volume_brl=500_000))


def historico(ticker: str, *, nivel: float = 2_000_000.0) -> pd.DataFrame:
    """Barras planas com dispersao pequena, e preco oscilando dentro do ano."""
    dias = sessions_before(FIM, SESSOES, inclusive=True)
    return pd.DataFrame(
        {
            "ticker": ticker,
            "trade_date": dias,
            "open": [10.0 + (i % 20) * 0.1 for i in range(SESSOES)],
            "high": [10.6 + (i % 20) * 0.1 for i in range(SESSOES)],
            "low": [9.4 + (i % 20) * 0.1 for i in range(SESSOES)],
            "close": [10.2 + (i % 20) * 0.1 for i in range(SESSOES)],
            "avg_price": [10.1 + (i % 20) * 0.1 for i in range(SESSOES)],
            "volume_shares": 200_000,
            "volume_financial": [nivel * (1 + 0.1 * math.sin(i)) for i in range(SESSOES)],
            "trades_count": 800,
            "trades_censored": False,
        }
    )


def com_spike(bars: pd.DataFrame, ticker: str, dia: date, fator: float) -> pd.DataFrame:
    """Multiplica o volume de um papel num pregao."""
    saida = bars.copy()
    saida["trade_date"] = pd.to_datetime(saida["trade_date"])
    alvo = (saida["ticker"] == ticker) & (saida["trade_date"] == pd.Timestamp(dia))
    assert bool(alvo.any()), f"sem barra de {ticker} em {dia}"
    saida.loc[alvo, "volume_financial"] = saida.loc[alvo, "volume_financial"] * fator
    return saida


def avaliar(bars: pd.DataFrame, config: ScannerConfig, dia: date) -> pd.DataFrame:
    """Pipeline completo em memoria: metricas, features e regra."""
    metrics = compute_zscores(bars, config.alert.windows)
    features = compute_features(bars, max(config.alert.windows), metrics)
    return select_events(metrics, bars, features, config.alert, trade_date=dia)


@pytest.fixture
def mercado() -> pd.DataFrame:
    """Tres papeis, para o volume agregado do mercado existir."""
    return pd.concat(
        [historico("AAAA3"), historico("BBBB4", nivel=5_000_000.0), historico("CCCC3")],
        ignore_index=True,
    )


# --- Criterio de aceite da F4 ------------------------------------------------


def test_spike_de_20x_dispara_um_alerta_completo(mercado: pd.DataFrame) -> None:
    bars = com_spike(mercado, "AAAA3", FIM, 20.0)
    eventos = avaliar(bars, CONFIG, FIM)

    assert len(eventos) == 1, f"esperado 1 alerta, veio {len(eventos)}"
    evento = eventos.iloc[0]
    assert evento["ticker"] == "AAAA3"

    faltando = [nome for nome, valor in evento["features"].items() if valor is None]
    assert not faltando, f"features vazias no alerta: {faltando}"
    assert set(evento["features"]) == set(FEATURE_COLUMNS)

    assert evento["max_z_log"] >= CONFIG.alert.threshold
    assert evento["triggered_windows"] == JANELAS
    assert evento["volume_financial"] >= CONFIG.alert.min_volume_brl


def test_payload_do_alerta_traz_rvol_e_z_por_janela(mercado: pd.DataFrame) -> None:
    bars = com_spike(mercado, "AAAA3", FIM, 20.0)
    metrics = compute_zscores(bars, JANELAS)
    features = compute_features(bars, max(JANELAS), metrics)
    evento = select_events(metrics, bars, features, CONFIG.alert, trade_date=FIM).iloc[0]

    payload = alert_payload(evento, metrics, bars, JANELAS)
    assert payload["rvol"] is not None and payload["rvol"] > 10
    assert set(payload["z_by_window"]) == set(JANELAS)
    assert payload["close"] is not None


# --- A regra e so o limiar ---------------------------------------------------


def test_sem_spike_nao_ha_alerta(mercado: pd.DataFrame) -> None:
    assert avaliar(mercado, CONFIG, FIM).empty


def test_piso_de_volume_e_o_unico_filtro(mercado: pd.DataFrame) -> None:
    # Papel minusculo com spike enorme: z altissimo, volume irrisorio.
    minusculo = historico("DDDD3", nivel=3_000.0)
    bars = com_spike(pd.concat([mercado, minusculo], ignore_index=True), "DDDD3", FIM, 20.0)

    com_piso = avaliar(bars, CONFIG, FIM)
    assert "DDDD3" not in set(com_piso["ticker"])

    sem_piso = ScannerConfig(alert=AlertConfig(windows=JANELAS, min_volume_brl=0))
    assert "DDDD3" in set(avaliar(bars, sem_piso, FIM)["ticker"])


def test_count_below_floor_reporta_o_que_o_piso_barrou(mercado: pd.DataFrame) -> None:
    minusculo = historico("DDDD3", nivel=3_000.0)
    bars = com_spike(pd.concat([mercado, minusculo], ignore_index=True), "DDDD3", FIM, 20.0)
    metrics = compute_zscores(bars, JANELAS)
    assert count_below_floor(metrics, bars, CONFIG.alert, trade_date=FIM) == 1


def test_require_all_windows(mercado: pd.DataFrame) -> None:
    bars = com_spike(mercado, "AAAA3", FIM, 20.0)
    metrics = compute_zscores(bars, JANELAS)
    features = compute_features(bars, max(JANELAS), metrics)

    # Limiar entre o z da janela de 30 e o da de 60: so uma parte cruza.
    zs = metrics[(metrics["ticker"] == "AAAA3") & (metrics["trade_date"] == pd.Timestamp(FIM))]
    meio = float((zs["z_log"].max() + zs["z_log"].min()) / 2)

    qualquer = AlertConfig(windows=JANELAS, threshold=meio, require_all_windows=False)
    todas = AlertConfig(windows=JANELAS, threshold=meio, require_all_windows=True)

    assert len(select_events(metrics, bars, features, qualquer, trade_date=FIM)) == 1
    assert select_events(metrics, bars, features, todas, trade_date=FIM).empty


def test_nao_ha_cooldown_nem_teto_diario(mercado: pd.DataFrame) -> None:
    # Dois pregoes seguidos com spike geram dois eventos. O plano e explicito:
    # todo evento acima do limiar entra na lista.
    anterior = sessions_before(FIM, 1)[0]
    bars = com_spike(com_spike(mercado, "AAAA3", anterior, 20.0), "AAAA3", FIM, 20.0)

    assert len(avaliar(bars, CONFIG, anterior)) == 1
    assert len(avaliar(bars, CONFIG, FIM)) == 1


def test_todos_os_papeis_acima_do_limiar_entram(mercado: pd.DataFrame) -> None:
    bars = com_spike(com_spike(mercado, "AAAA3", FIM, 20.0), "CCCC3", FIM, 25.0)
    eventos = avaliar(bars, CONFIG, FIM)
    assert set(eventos["ticker"]) == {"AAAA3", "CCCC3"}


def test_ordenado_do_maior_z_para_o_menor(mercado: pd.DataFrame) -> None:
    bars = com_spike(com_spike(mercado, "AAAA3", FIM, 20.0), "CCCC3", FIM, 60.0)
    eventos = avaliar(bars, CONFIG, FIM)
    assert list(eventos["max_z_log"]) == sorted(eventos["max_z_log"], reverse=True)


def test_metrica_alternativa_e_respeitada(mercado: pd.DataFrame) -> None:
    bars = com_spike(mercado, "AAAA3", FIM, 20.0)
    metrics = compute_zscores(bars, JANELAS)
    features = compute_features(bars, max(JANELAS), metrics)

    robusto = AlertConfig(windows=JANELAS, metric="z_robust", threshold=6.0)
    assert len(select_events(metrics, bars, features, robusto, trade_date=FIM)) == 1

    inatingivel = AlertConfig(windows=JANELAS, metric="z_robust", threshold=10_000.0)
    assert select_events(metrics, bars, features, inatingivel, trade_date=FIM).empty


def test_sem_metricas_nao_ha_evento() -> None:
    vazio = pd.DataFrame(
        columns=["ticker", "trade_date", "window_size", "z_log", "z_raw", "z_robust", "rvol"]
    )
    assert select_events(vazio, vazio, vazio, CONFIG.alert).empty


# --- Dedupe, contra o Postgres real ------------------------------------------


@pytest.fixture
def limpa_eventos(engine: Engine) -> Iterator[None]:
    tickers = ["AAAA3", "BBBB4", "CCCC3", "DDDD3"]
    yield
    with session_scope(engine) as s:
        s.execute(delete(Event).where(Event.ticker.in_(tickers)))


@pytest.mark.db
@pytest.mark.usefixtures("limpa_eventos")
def test_dedupe_por_ticker_e_data(engine: Engine, mercado: pd.DataFrame) -> None:
    bars = com_spike(mercado, "AAAA3", FIM, 20.0)
    eventos = avaliar(bars, CONFIG, FIM)

    assert insert_events(engine, eventos) == 1
    # Segunda vez: o mesmo evento nao entra de novo.
    assert insert_events(engine, eventos) == 0


@pytest.mark.db
@pytest.mark.usefixtures("limpa_eventos")
def test_scan_nao_notifica_duas_vezes(engine: Engine, mercado: pd.DataFrame) -> None:
    bars = com_spike(mercado, "AAAA3", FIM, 20.0)
    enviadas: list[str] = []
    notifier = ConsoleNotifier(sent=enviadas)

    primeiro, _ = run_scan(engine, CONFIG, FIM, notifier=notifier, bars=bars)
    assert primeiro.new_events == 1
    assert primeiro.notified == 1

    segundo, _ = run_scan(engine, CONFIG, FIM, notifier=notifier, bars=bars)
    assert segundo.new_events == 0
    assert segundo.notified == 0
    assert len(enviadas) == 1, "o mesmo evento foi notificado duas vezes"


@pytest.mark.db
@pytest.mark.usefixtures("limpa_eventos")
def test_dry_run_nao_grava_nem_carimba(engine: Engine, mercado: pd.DataFrame) -> None:
    bars = com_spike(mercado, "AAAA3", FIM, 20.0)
    enviadas: list[str] = []

    relatorio, _eventos = run_scan(
        engine, CONFIG, FIM, dry_run=True, notifier=ConsoleNotifier(sent=enviadas), bars=bars
    )
    assert relatorio.dry_run is True
    assert relatorio.crossed == 1
    assert relatorio.new_events == 0
    assert len(enviadas) == 1  # mostra o que sairia
    assert pending_events(engine, FIM).empty


@pytest.mark.db
@pytest.mark.usefixtures("limpa_eventos")
def test_mark_notified_esvazia_a_fila(engine: Engine, mercado: pd.DataFrame) -> None:
    bars = com_spike(mercado, "AAAA3", FIM, 20.0)
    insert_events(engine, avaliar(bars, CONFIG, FIM))

    pendentes = pending_events(engine, FIM)
    assert len(pendentes) == 1
    assert mark_notified(engine, [int(pendentes.iloc[0]["id"])]) == 1
    assert pending_events(engine, FIM).empty


@pytest.mark.db
@pytest.mark.usefixtures("limpa_eventos")
def test_features_sobrevivem_ao_jsonb(engine: Engine, mercado: pd.DataFrame) -> None:
    bars = com_spike(mercado, "AAAA3", FIM, 20.0)
    insert_events(engine, avaliar(bars, CONFIG, FIM))

    guardado = pending_events(engine, FIM).iloc[0]
    assert set(guardado["features"]) == set(FEATURE_COLUMNS)
    assert all(valor is not None for valor in guardado["features"].values())
    assert guardado["triggered_windows"] == JANELAS
