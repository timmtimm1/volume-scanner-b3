"""Z-scores de volume (secao 3.1 do plano).

A regra mecanica da secao 1, que nao pode ser violada: media, desvio e mediana da
janela usam apenas os N pregoes **anteriores** ao dia avaliado. `shift(1)` antes
do `rolling(N)`.

Se o dia do pico entra na janela que o mede, ele infla o proprio desvio padrao, e
o z-score maximo possivel de uma amostra de N pontos passa a ser `(N-1)/sqrt(N)`
-- 5,29 para N=30. O limiar de 6 sigma nunca dispararia.

Implementacao: as barras viram uma matriz larga (linhas = pregao, colunas =
ticker). Toda estatistica e calculada sobre a matriz inteira de uma vez, entao
nao ha loop por ticker. Dias sem negociacao sao NaN na matriz, nunca zero.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

# Constante que torna o MAD comparavel ao desvio padrao numa normal.
MAD_SCALE = 1.4826

METRIC_COLUMNS = ("z_log", "z_raw", "z_robust", "rvol")
OUTPUT_COLUMNS = ("ticker", "trade_date", "window_size", *METRIC_COLUMNS)


def to_wide(bars: pd.DataFrame, value: str = "volume_financial") -> pd.DataFrame:
    """Matriz pregao x ticker. Ausencia de negocio vira NaN, jamais zero."""
    frame = bars.loc[:, ["ticker", "trade_date", value]].copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    wide = frame.pivot_table(
        index="trade_date", columns="ticker", values=value, aggfunc="last"
    ).sort_index()
    return wide.astype(float)


def rolling_mad(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    """MAD deslizante, vetorizado sobre todas as colunas de uma vez.

    `rolling().apply()` chamaria Python uma vez por janela por ticker. Aqui a
    janela vira uma dimensao extra do array e o numpy resolve tudo de um golpe.
    """
    values = frame.to_numpy(dtype=float)
    out = np.full(values.shape, np.nan, dtype=float)

    if len(values) >= window:
        # (linhas - janela + 1, colunas, janela)
        view = sliding_window_view(values, window, axis=0)
        # Janela toda NaN e o caso normal de ticker antes da listagem ou depois
        # do encerramento; nanmedian avisa e devolve NaN, que e o que queremos.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", "All-NaN slice encountered", RuntimeWarning)
            median = np.nanmedian(view, axis=-1)
            mad = np.nanmedian(np.abs(view - median[..., None]), axis=-1)
        # min_periods=window: a janela precisa estar cheia, sem buraco.
        complete = (~np.isnan(view)).sum(axis=-1) == window
        out[window - 1 :] = np.where(complete, mad, np.nan)

    return pd.DataFrame(out, index=frame.index, columns=frame.columns)


def _melt(wide: pd.DataFrame, name: str) -> pd.DataFrame:
    """Matriz larga de volta para formato longo."""
    long = wide.stack(future_stack=True).reset_index()
    long.columns = pd.Index(["trade_date", "ticker", name])
    return long


def compute_zscores(bars: pd.DataFrame, windows: Sequence[int]) -> pd.DataFrame:
    """Z-scores de volume por janela, com baseline deslocado.

    `bars` em formato longo, com ticker, trade_date e volume_financial.
    Devolve uma linha por (ticker, pregao, janela), sem as linhas em que o
    baseline nao existe.
    """
    if not windows:
        raise ValueError("informe ao menos uma janela")
    if any(w < 2 for w in windows):
        raise ValueError("janela minima e 2 pregoes")

    empty = pd.DataFrame({c: pd.Series(dtype="float64") for c in OUTPUT_COLUMNS})
    if bars.empty:
        return empty

    volume = to_wide(bars)
    # Volume zero ou negativo e ausencia de negocio, nao um valor.
    volume = volume.where(volume > 0)
    volume_log = pd.DataFrame(
        np.log(volume.to_numpy(dtype=float)), index=volume.index, columns=volume.columns
    )

    # O shift(1) e a regra: o dia avaliado nao entra no proprio baseline.
    prev_log = volume_log.shift(1)
    prev_raw = volume.shift(1)

    blocks: list[pd.DataFrame] = []
    for window in windows:
        roll_log = prev_log.rolling(window, min_periods=window)
        roll_raw = prev_raw.rolling(window, min_periods=window)

        z_log = (volume_log - roll_log.mean()) / roll_log.std()
        z_raw = (volume - roll_raw.mean()) / roll_raw.std()
        z_robust = (volume_log - roll_log.median()) / (MAD_SCALE * rolling_mad(prev_log, window))
        rvol = volume / roll_raw.median()

        block = _melt(z_log, "z_log")
        for frame, name in ((z_raw, "z_raw"), (z_robust, "z_robust"), (rvol, "rvol")):
            block[name] = _melt(frame, name)[name]
        block["window_size"] = window
        blocks.append(block)

    result = pd.concat(blocks, ignore_index=True)
    result = result.replace([np.inf, -np.inf], np.nan)
    result = result.dropna(subset=["z_log"])
    return result.loc[:, list(OUTPUT_COLUMNS)].reset_index(drop=True)


def max_reachable_z(window: int) -> float:
    """Maior z-score possivel quando o dia avaliado entra na propria janela.

    `(N-1)/sqrt(N)`. Existe para os testes provarem que o `shift(1)` esta la:
    passar deste teto so e possivel com baseline deslocado.
    """
    return (window - 1) / math.sqrt(window)


def market_volume(bars: pd.DataFrame) -> pd.Series:
    """Volume financeiro agregado do mercado, por pregao."""
    frame = bars.loc[:, ["trade_date", "volume_financial"]].copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame.groupby("trade_date")["volume_financial"].sum().sort_index()


def market_volume_z(bars: pd.DataFrame, window: int) -> pd.Series:
    """Z-score do volume agregado do mercado, com o mesmo baseline deslocado.

    E o `mkt_vol_z` da secao 3.2: responde se o mercado inteiro estava assim ou
    se foi so aquele papel.
    """
    total = market_volume(bars)
    total = total.where(total > 0)
    total_log = pd.Series(np.log(total.to_numpy(dtype=float)), index=total.index)
    prev = total_log.shift(1)
    roll = prev.rolling(window, min_periods=window)
    z = (total_log - roll.mean()) / roll.std()
    return pd.Series(z).replace([np.inf, -np.inf], np.nan)
