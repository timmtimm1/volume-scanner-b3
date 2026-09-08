"""Regra de alerta e dedupe (secao 4 do plano).

Cruzou o limiar, avisa. Nao ha filtro de qualidade, score de confianca, ranking
de "melhores", classificacao de padrao, cooldown nem teto diario. O unico filtro
e o piso absoluto de volume do `config.yaml`, que existe para papel que negocia
tres mil reais por dia nao encher a lista ao negociar quarenta mil.

Em dia de estresse de mercado isto produz dezenas de alertas de uma vez, porque a
correlacao entre papeis dispara junto. E o comportamento pedido: o `z_excess` na
mensagem e o que permite descartar a enxurrada rapidamente.

Dedupe e apenas por (ticker, trade_date), para o mesmo evento nao notificar duas
vezes se o job rodar de novo.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import Engine

from scanner.config import AlertConfig, ScannerConfig
from scanner.features import FEATURE_COLUMNS
from scanner.recompute import Contexto, carregar_contexto
from scanner.storage.repository import (
    insert_events,
    mark_notified,
    pending_events,
)

EVENT_COLUMNS = (
    "ticker",
    "trade_date",
    "max_z_log",
    "triggered_windows",
    "volume_financial",
    "features",
)


@dataclass(frozen=True)
class ScanReport:
    """O que o scan de um pregao fez."""

    trade_date: date
    evaluated: int
    crossed: int
    below_volume_floor: int
    new_events: int
    notified: int
    dry_run: bool

    def summary(self) -> str:
        """Uma linha para log e CLI."""
        modo = " (dry-run)" if self.dry_run else ""
        return (
            f"{self.trade_date.isoformat()}{modo}: {self.evaluated:,} papeis avaliados, "
            f"{self.crossed} cruzaram o limiar, {self.below_volume_floor} barrados pelo "
            f"piso de volume, {self.new_events} eventos novos, {self.notified} notificados"
        )


def _features_dict(row: pd.Series) -> dict[str, Any]:
    """Features do evento como dicionario, com NaN virando None para o JSONB."""
    saida: dict[str, Any] = {}
    for nome in FEATURE_COLUMNS:
        valor = row.get(nome)
        saida[nome] = None if valor is None or pd.isna(valor) else float(valor)
    return saida


def select_events(
    metrics: pd.DataFrame,
    bars: pd.DataFrame,
    features: pd.DataFrame,
    config: AlertConfig,
    *,
    trade_date: date | None = None,
) -> pd.DataFrame:
    """Eventos que cruzaram o limiar, um por (ticker, pregao).

    `require_all_windows=False` dispara com qualquer janela cruzando; `True`
    exige todas as janelas configuradas.
    """
    vazio = pd.DataFrame({c: pd.Series(dtype="object") for c in EVENT_COLUMNS})
    if metrics.empty:
        return vazio

    janelas = list(config.windows)
    escopo = metrics[metrics["window_size"].isin(janelas)]
    if trade_date is not None:
        escopo = escopo[escopo["trade_date"] == pd.Timestamp(trade_date)]
    if escopo.empty:
        return vazio

    # A regra inteira: a metrica escolhida alcancou o limiar.
    cruzou = escopo[escopo[config.metric] >= config.threshold]
    if cruzou.empty:
        return vazio

    agrupado = cruzou.groupby(["ticker", "trade_date"], sort=False)
    resumo = agrupado.agg(max_z_log=("z_log", "max"), janelas_cruzadas=("window_size", "nunique"))
    resumo["triggered_windows"] = agrupado["window_size"].apply(
        lambda s: sorted({int(w) for w in s})
    )
    resumo = resumo.reset_index()

    if config.require_all_windows:
        resumo = resumo[resumo["janelas_cruzadas"] == len(janelas)]
    if resumo.empty:
        return vazio

    barras = bars.loc[:, ["ticker", "trade_date", "volume_financial"]].copy()
    barras["trade_date"] = pd.to_datetime(barras["trade_date"])
    resumo = resumo.merge(barras, on=["ticker", "trade_date"], how="left")

    # Unico filtro: papel morto nao interessa.
    resumo = resumo[resumo["volume_financial"] >= config.min_volume_brl]
    if resumo.empty:
        return vazio

    contexto = features.copy()
    contexto["trade_date"] = pd.to_datetime(contexto["trade_date"])
    resumo = resumo.merge(contexto, on=["ticker", "trade_date"], how="left")
    resumo["features"] = pd.Series(
        [_features_dict(linha) for _, linha in resumo.iterrows()],
        index=resumo.index,
        dtype="object",
    )

    resumo = resumo.sort_values("max_z_log", ascending=False)
    return resumo.loc[:, list(EVENT_COLUMNS)].reset_index(drop=True)


def count_below_floor(
    metrics: pd.DataFrame, bars: pd.DataFrame, config: AlertConfig, *, trade_date: date | None
) -> int:
    """Quantos cruzaram o limiar mas ficaram abaixo do piso de volume.

    Existe para o relatorio do scan dizer o que o piso barrou, em vez de o
    numero sumir em silencio.
    """
    if metrics.empty:
        return 0
    escopo = metrics[metrics["window_size"].isin(list(config.windows))]
    if trade_date is not None:
        escopo = escopo[escopo["trade_date"] == pd.Timestamp(trade_date)]
    cruzou = escopo[escopo[config.metric] >= config.threshold]
    if cruzou.empty:
        return 0

    barras = bars.loc[:, ["ticker", "trade_date", "volume_financial"]].copy()
    barras["trade_date"] = pd.to_datetime(barras["trade_date"])
    juntos = (
        cruzou[["ticker", "trade_date"]]
        .drop_duplicates()
        .merge(barras, on=["ticker", "trade_date"], how="left")
    )
    return int((juntos["volume_financial"] < config.min_volume_brl).sum())


def alert_payload(
    event: pd.Series, metrics: pd.DataFrame, bars: pd.DataFrame, windows: Sequence[int]
) -> dict[str, Any]:
    """Junta ao evento o que a mensagem precisa e a tabela `events` nao guarda.

    O schema da secao 8 guarda max_z_log, as janelas disparadas e as features da
    secao 3.2. A mensagem tambem mostra o rvol e o z de cada janela, que vivem em
    `volume_metrics`, e o fechamento, que vive em `daily_bars`. Em vez de inflar
    o schema, o alerta e enriquecido na hora do envio.
    """
    ticker = str(event["ticker"])
    dia = pd.Timestamp(event["trade_date"])

    do_papel = metrics[(metrics["ticker"] == ticker) & (metrics["trade_date"] == dia)]
    z_por_janela = {
        int(linha["window_size"]): (None if pd.isna(linha["z_log"]) else float(linha["z_log"]))
        for _, linha in do_papel.iterrows()
    }

    # "o normal" e a mediana da maior janela: a estimativa mais estavel.
    maior = max(windows)
    na_maior = do_papel[do_papel["window_size"] == maior]
    if na_maior.empty:
        na_maior = do_papel.nlargest(1, "window_size")
    rvol = (
        None
        if na_maior.empty or pd.isna(na_maior.iloc[0]["rvol"])
        else float(na_maior.iloc[0]["rvol"])
    )

    barras = bars.copy()
    barras["trade_date"] = pd.to_datetime(barras["trade_date"])
    linha_barra = barras[(barras["ticker"] == ticker) & (barras["trade_date"] == dia)]
    fechamento = None if linha_barra.empty else float(linha_barra.iloc[0]["close"])

    features = event.get("features") or {}
    return {
        "ticker": ticker,
        "trade_date": dia.date(),
        "rvol": rvol,
        "z_by_window": z_por_janela,
        "volume_financial": float(event["volume_financial"]),
        "close": fechamento,
        **{nome: features.get(nome) for nome in FEATURE_COLUMNS},
    }


def run_scan(
    engine: Engine,
    config: ScannerConfig,
    trade_date: date,
    *,
    dry_run: bool = False,
    notifier: Any = None,
    bars: pd.DataFrame | None = None,
    contexto: Contexto | None = None,
) -> tuple[ScanReport, pd.DataFrame]:
    """Avalia um pregao, grava os eventos novos e notifica.

    O dedupe e a chave unica (ticker, trade_date): rodar de novo nao gera evento
    repetido nem segunda notificacao.

    `bars` permite passar as barras prontas em vez de reler o banco; os testes
    usam para nao recalcular sobre a base inteira. `contexto` vai um passo
    alem: o calculo ja veio pronto de fora, como no `scanner daily`.
    """
    ctx = carregar_contexto(engine, config, bars=bars) if contexto is None else contexto
    if ctx.vazio:
        return ScanReport(trade_date, 0, 0, 0, 0, 0, dry_run), pd.DataFrame()

    bars, metrics, features = ctx.bars, ctx.metrics, ctx.features
    # O contexto pode trazer a janela do resumo junto; o alerta so olha as suas.
    janelas = list(config.alert.windows)
    eventos = select_events(metrics, bars, features, config.alert, trade_date=trade_date)

    do_dia = metrics[metrics["trade_date"] == pd.Timestamp(trade_date)]
    avaliados = int(do_dia["ticker"].nunique())
    barrados = count_below_floor(metrics, bars, config.alert, trade_date=trade_date)

    if dry_run:
        # Mostra o que sairia, sem gravar evento nem carimbar notificacao.
        if notifier is not None:
            for _, linha in eventos.iterrows():
                notifier.send_event(alert_payload(linha, metrics, bars, janelas))
        relatorio = ScanReport(trade_date, avaliados, len(eventos), barrados, 0, 0, dry_run=True)
        return relatorio, eventos

    novos = insert_events(engine, eventos)
    pendentes = pending_events(engine, trade_date)

    enviados: list[int] = []
    if notifier is not None:
        for _, linha in pendentes.iterrows():
            if notifier.send_event(alert_payload(linha, metrics, bars, janelas)):
                enviados.append(int(linha["id"]))
        mark_notified(engine, enviados)

    relatorio = ScanReport(
        trade_date, avaliados, len(eventos), barrados, novos, len(enviados), dry_run=False
    )
    return relatorio, eventos
