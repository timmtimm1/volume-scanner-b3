"""Orquestracao da carga: baixar, parsear, gravar.

Carga historica usa os arquivos anuais; a incremental usa o arquivo do pregao.
Em ambos os casos a gravacao e idempotente, entao rodar de novo e seguro.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pandas as pd

from scanner.config import IngestConfig
from scanner.ingest.cotahist import parse_file
from scanner.ingest.download import DEFAULT_CACHE, download_annual, download_daily
from scanner.storage.engine import build_engine
from scanner.storage.repository import upsert_bars


def _clip(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Recorta ao intervalo pedido: o arquivo anual traz o ano inteiro."""
    if frame.empty:
        return frame
    days = pd.to_datetime(frame["trade_date"])
    return frame[(days >= pd.Timestamp(start)) & (days <= pd.Timestamp(end))]


def ingest_range(
    start: date, end: date, config: IngestConfig, *, cache: Path = DEFAULT_CACHE
) -> Iterator[str]:
    """Carrega os arquivos anuais que cobrem [start, end], um por vez.

    Rende uma linha de relatorio por ano, para o progresso aparecer durante a
    carga em vez de so no fim.
    """
    engine = build_engine()
    for year in range(start.year, end.year + 1):
        path = download_annual(year, cache)
        frame, report = parse_file(path, config)
        clipped = _clip(frame, start, end)
        written = upsert_bars(engine, clipped)
        yield f"{report.summary()}; {written:,} barras gravadas no intervalo"


def ingest_day(day: date, config: IngestConfig, *, cache: Path = DEFAULT_CACHE) -> str:
    """Carrega o arquivo de um unico pregao."""
    path = download_daily(day, cache)
    frame, report = parse_file(path, config)
    written = upsert_bars(build_engine(), _clip(frame, day, day))
    return f"{report.summary()}; {written:,} barras gravadas"
