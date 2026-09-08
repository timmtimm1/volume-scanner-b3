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
from scanner.features import compute_features
from scanner.metrics import compute_zscores
from scanner.storage.repository import (
    last_metric_date,
    load_bars,
    upsert_features,
    upsert_metrics,
)


@dataclass(frozen=True)
class Contexto:
    """Barras, metricas e contexto do historico inteiro, calculados uma vez.

    O pregao diario precisa das tres coisas em tres lugares: gravar metricas,
    avaliar alertas e montar o resumo. Cada um deles lia as barras do banco e
    refazia o mesmo calculo -- tres viagens ate o Neon e tres passadas sobre as
    mesmas 130 mil linhas, para chegar aos mesmos numeros.

    Passar este objeto adiante nao e so economia de tempo: enquanto cada etapa
    calculava por conta propria, nada garantia que o alerta e o resumo do mesmo
    pregao estavam olhando para os mesmos valores.
    """

    bars: pd.DataFrame
    metrics: pd.DataFrame
    features: pd.DataFrame
    janelas: tuple[int, ...]

    @property
    def vazio(self) -> bool:
        return self.bars.empty


def carregar_contexto(
    engine: Engine, config: ScannerConfig, *, bars: pd.DataFrame | None = None
) -> Contexto:
    """Le as barras e calcula tudo que o pregao precisa, de uma vez so.

    As janelas sao a uniao das do alerta com a do resumo: se o resumo for
    configurado para uma janela que o alerta nao usa, ela precisa existir aqui
    -- do contrario o resumo ficaria sem metrica e sairia vazio.

    `bars` permite passar as barras prontas em vez de reler o banco; os testes
    usam para nao depender do Postgres.
    """
    barras = load_bars(engine) if bars is None else bars
    janelas = sorted({*config.alert.windows, config.digest.window})
    metrics = compute_zscores(barras, janelas)
    features = compute_features(barras, max(janelas), metrics)
    return Contexto(barras, metrics, features, tuple(janelas))


@dataclass(frozen=True)
class RecomputeReport:
    """O que o recalculo fez."""

    mode: str
    bars_read: int
    rows_computed: int
    rows_written: int
    features_written: int
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
            f"{self.rows_written:,} gravadas{faixa}; "
            f"{self.features_written:,} linhas de contexto"
        )


def refresh_metrics(
    engine: Engine,
    config: ScannerConfig,
    *,
    mode: str = "incremental",
    contexto: Contexto | None = None,
) -> RecomputeReport:
    """Recalcula os z-scores e grava.

    `full` regrava tudo. `incremental` grava apenas os pregoes posteriores ao
    ultimo ja calculado -- util quando so entrou o pregao do dia.

    `contexto` evita reler e recalcular quando quem chama ja tem tudo em maos.
    """
    if mode not in {"incremental", "full"}:
        raise ValueError("mode aceita 'incremental' ou 'full'")

    ctx = carregar_contexto(engine, config) if contexto is None else contexto
    bars, metrics = ctx.bars, ctx.metrics

    to_write = metrics
    if mode == "incremental" and not metrics.empty:
        marker = last_metric_date(engine)
        if marker is not None:
            # Recalcula do ultimo dia gravado em diante: se aquele pregao foi
            # recarregado, seus valores tambem precisam ser atualizados.
            to_write = metrics[metrics["trade_date"] >= pd.Timestamp(marker)]

    written = upsert_metrics(engine, to_write, replace_all=(mode == "full"))

    # O contexto da secao 3.2 e persistido para tudo que se calculou, nao so
    # para o que virou alerta: a tela mostra uma faixa de z maior que a do
    # Telegram, e linha sem contexto nao serve para ler nada.
    features = ctx.features
    if not to_write.empty:
        janela = set(pd.to_datetime(to_write["trade_date"]).unique())
        features = features[pd.to_datetime(features["trade_date"]).isin(janela)]
    features_written = upsert_features(engine, features)

    dates = pd.to_datetime(to_write["trade_date"]) if not to_write.empty else None
    return RecomputeReport(
        mode=mode,
        bars_read=len(bars),
        rows_computed=len(metrics),
        rows_written=written,
        features_written=features_written,
        first_written=dates.min().date() if dates is not None else None,
        last_written=dates.max().date() if dates is not None else None,
    )


def ticker_history(engine: Engine, ticker: str, window: int, *, limit: int = 30) -> pd.DataFrame:
    """Os pregoes mais recentes de um papel, com metrica e contexto.

    Alimenta o `scanner report ticker` e a ficha do papel.
    """
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
