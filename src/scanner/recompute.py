"""Orquestracao do calculo: ler barras, calcular, gravar.

O calculo sempre le o historico inteiro, mesmo em modo incremental: sem os N
pregoes anteriores nao existe baseline. O que o modo muda e quanto se grava.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy import Engine

from scanner.config import ScannerConfig
from scanner.metrics import compute_zscores
from scanner.storage.repository import (
    last_metric_date,
    load_bars,
    upsert_metrics,
)


@dataclass(frozen=True)
class RecomputeReport:
    """O que o recalculo fez."""

    mode: str
    bars_read: int
    rows_computed: int
    rows_written: int
    first_written: date | None
    last_written: date | None

    def summary(self) -> str:
        """Uma linha para log e CLI."""
        faixa = (
            f" de {self.first_written} a {self.last_written}"
            if self.first_written and self.last_written
            else ""
        )
        return (
            f"modo {self.mode}: {self.bars_read:,} barras lidas, "
            f"{self.rows_computed:,} metricas calculadas, "
            f"{self.rows_written:,} gravadas{faixa}"
        )


def refresh_metrics(
    engine: Engine, config: ScannerConfig, *, mode: str = "incremental"
) -> RecomputeReport:
    """Recalcula os z-scores e grava.

    `full` regrava tudo. `incremental` grava apenas os pregoes posteriores ao
    ultimo ja calculado -- util quando so entrou o pregao do dia.
    """
    if mode not in {"incremental", "full"}:
        raise ValueError("mode aceita 'incremental' ou 'full'")

    bars = load_bars(engine)
    metrics = compute_zscores(bars, config.alert.windows)

    to_write = metrics
    if mode == "incremental" and not metrics.empty:
        marker = last_metric_date(engine)
        if marker is not None:
            # Recalcula do ultimo dia gravado em diante: se aquele pregao foi
            # recarregado, seus valores tambem precisam ser atualizados.
            to_write = metrics[metrics["trade_date"] >= pd.Timestamp(marker)]

    written = upsert_metrics(engine, to_write, replace_all=(mode == "full"))
    dates = pd.to_datetime(to_write["trade_date"]) if not to_write.empty else None
    return RecomputeReport(
        mode=mode,
        bars_read=len(bars),
        rows_computed=len(metrics),
        rows_written=written,
        first_written=dates.min().date() if dates is not None else None,
        last_written=dates.max().date() if dates is not None else None,
    )


def ticker_history(engine: Engine, ticker: str, window: int, *, limit: int = 30) -> pd.DataFrame:
    """Os pregoes mais recentes de um papel, com metrica e contexto.

    Alimenta o `scanner report ticker` e, mais adiante, a ficha do papel.
    """
    from scanner.features import compute_features

    bars = load_bars(engine)
    alvo = bars[bars["ticker"] == ticker.upper()]
    if alvo.empty:
        return pd.DataFrame()

    metrics = compute_zscores(bars, [window])
    features = compute_features(bars, window, metrics)

    linhas = (
        alvo.assign(trade_date=pd.to_datetime(alvo["trade_date"]))
        .merge(
            metrics[metrics["window_size"] == window].drop(columns=["window_size"]),
            on=["ticker", "trade_date"],
            how="left",
        )
        .merge(features, on=["ticker", "trade_date"], how="left")
        .sort_values("trade_date")
    )
    return linhas.tail(limit)
