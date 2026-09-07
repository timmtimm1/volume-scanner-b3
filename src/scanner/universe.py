"""Universo de papeis: quais tickers o scanner acompanha.

Dois criterios, ambos no `config.yaml`:

- liquidez: a mediana do volume financeiro na janela precisa alcancar um piso;
- atividade: o papel precisa ter negociado numa fracao minima dos pregoes da
  janela. Sem isso, um papel que negociou 2 de 60 pregoes com volume alto teria
  mediana alta e entraria no universo.

Isto NAO e filtro de merito de evento. O universo define de quem se coleta
historico; a regra de alerta da secao 4 do plano continua sem julgamento.

Tudo vetorizado: nenhum loop por ticker.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import Engine, select

from scanner.calendar import sessions_before
from scanner.config import UniverseConfig
from scanner.storage.models import DailyBar

REQUIRED_COLUMNS = ("ticker", "trade_date", "volume_financial")
STATS_COLUMNS = ("median_volume", "sessions_traded", "coverage")


def _normalize(bars: pd.DataFrame) -> pd.DataFrame:
    """Recorta as colunas usadas e aplica a regra de que volume zero nao existe."""
    missing = [c for c in REQUIRED_COLUMNS if c not in bars.columns]
    if missing:
        raise ValueError(f"colunas ausentes em bars: {missing}")

    out = bars.loc[:, list(REQUIRED_COLUMNS)].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out["volume_financial"] = pd.to_numeric(out["volume_financial"], errors="coerce").astype(float)
    # Dia sem negociacao e buraco, nunca zero.
    out.loc[out["volume_financial"] <= 0, "volume_financial"] = np.nan
    return out


def compute_liquidity(bars: pd.DataFrame, sessions: Sequence[date]) -> pd.DataFrame:
    """Mediana de volume, pregoes negociados e cobertura, por ticker.

    `sessions` e a janela de pregoes considerada; a cobertura e medida contra ela,
    e nao contra o que o papel por acaso tem no banco.
    """
    empty = pd.DataFrame(
        {
            "median_volume": pd.Series(dtype="float64"),
            "sessions_traded": pd.Series(dtype="int64"),
            "coverage": pd.Series(dtype="float64"),
        }
    )
    empty.index.name = "ticker"
    if not sessions:
        return empty

    window = set(pd.to_datetime(pd.Series(list(sessions), dtype="object")))
    frame = _normalize(bars)
    frame = frame[frame["trade_date"].isin(window)]

    if frame.duplicated(subset=["ticker", "trade_date"]).any():
        raise ValueError("bars tem (ticker, trade_date) repetido: a janela ficaria distorcida")
    if frame.empty:
        return empty

    grouped = frame.groupby("ticker", sort=True)["volume_financial"]
    stats = pd.DataFrame(
        {
            # `count` ignora NaN: conta pregoes efetivamente negociados.
            "median_volume": grouped.median(),
            "sessions_traded": grouped.count().astype("int64"),
        }
    )
    stats["coverage"] = stats["sessions_traded"] / float(len(sessions))
    return stats


def select_universe(
    bars: pd.DataFrame, sessions: Sequence[date], config: UniverseConfig
) -> pd.DataFrame:
    """Aplica os cortes de liquidez e atividade, do mais liquido para o menos."""
    stats = compute_liquidity(bars, sessions)
    if stats.empty:
        return stats

    liquid = stats["median_volume"] >= config.min_median_volume_brl
    active = stats["coverage"] >= config.min_session_coverage
    return stats[liquid & active].sort_values("median_volume", ascending=False)


def tickers(universe: pd.DataFrame) -> list[str]:
    """Os codigos do universo, como lista."""
    return [str(t) for t in universe.index]


def load_bars_window(engine: Engine, sessions: Sequence[date]) -> pd.DataFrame:
    """Le do banco as barras dos pregoes da janela."""
    if not sessions:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in REQUIRED_COLUMNS})

    stmt = (
        select(DailyBar.ticker, DailyBar.trade_date, DailyBar.volume_financial)
        .where(DailyBar.trade_date >= min(sessions))
        .where(DailyBar.trade_date <= max(sessions))
    )
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def load_universe(engine: Engine, as_of: date, config: UniverseConfig) -> pd.DataFrame:
    """Universo vigente em `as_of`, lido do banco.

    A janela termina em `as_of` inclusive, quando `as_of` e pregao.
    """
    sessions = sessions_before(as_of, config.lookback_sessions, inclusive=True)
    return select_universe(load_bars_window(engine, sessions), sessions, config)
