"""Contexto do evento (secao 3.2 do plano).

Estas features nao filtram nada e nao decidem nada. Sao os numeros que vao no
alerta e na tela para o usuario julgar o evento em segundos, no olho.

Como em `metrics.py`, tudo e calculado sobre matrizes largas (pregao x ticker),
sem loop por ticker. As janelas que servem de baseline usam `shift(1)`, pela
mesma razao da secao 1: o dia avaliado nao entra na propria referencia.
"""

from __future__ import annotations

import pandas as pd

from scanner.metrics import market_volume_z, to_wide

# Janela de 252 pregoes ~ um ano de bolsa.
YEAR_SESSIONS = 252
# "Os 20 pregoes anteriores" da secao 3.2.
PRIOR_SESSIONS = 20

FEATURE_COLUMNS = (
    "ret_day",
    "clv",
    "gap",
    "range_norm",
    "pos252",
    "ret_prior_20",
    "avg_ticket",
    "ticket_z",
    "mkt_vol_z",
    "z_excess",
)


def _long(wide: pd.DataFrame, name: str) -> pd.DataFrame:
    long = wide.stack(future_stack=True).reset_index()
    long.columns = pd.Index(["trade_date", "ticker", name])
    return long


def compute_features(
    bars: pd.DataFrame,
    window: int,
    metrics: pd.DataFrame | None = None,
    *,
    year_sessions: int = YEAR_SESSIONS,
    prior_sessions: int = PRIOR_SESSIONS,
) -> pd.DataFrame:
    """Uma linha por (ticker, pregao) com todo o contexto da secao 3.2.

    `window` e a janela usada como baseline de `ticket_z` e `mkt_vol_z`; na
    pratica, a maior das janelas configuradas para o alerta.

    `metrics` e a saida de `compute_zscores`; com ela, `z_excess` e preenchido.
    Sem ela, `z_excess` fica NaN.
    """
    if bars.empty:
        return pd.DataFrame(
            {c: pd.Series(dtype="float64") for c in ("ticker", "trade_date", *FEATURE_COLUMNS)}
        )

    close = to_wide(bars, "close")
    high = to_wide(bars, "high")
    low = to_wide(bars, "low")
    opening = to_wide(bars, "open")
    avg_price = to_wide(bars, "avg_price")
    volume = to_wide(bars, "volume_financial")
    trades = to_wide(bars, "trades_count")
    prepared = bars.assign(trades_censored=bars["trades_censored"].astype(float))
    censored = to_wide(prepared, "trades_censored") > 0

    prev_close = close.shift(1)

    ret_day = close / prev_close - 1.0
    gap = opening / prev_close - 1.0

    # Onde fechou dentro do range do dia: 0 no fundo, 1 no topo.
    span = high - low
    clv = (close - low) / span.where(span > 0)

    range_norm = span / avg_price.where(avg_price > 0)

    # Faixa dos ultimos 252 pregoes, incluindo o dia: 0 = minima, 1 = maxima.
    year_low = close.rolling(year_sessions, min_periods=year_sessions).min()
    year_high = close.rolling(year_sessions, min_periods=year_sessions).max()
    year_span = year_high - year_low
    pos252 = (close - year_low) / year_span.where(year_span > 0)

    # Retorno ATE a vespera: diz de onde o papel veio, sem contar o dia do evento.
    ret_prior = prev_close / close.shift(prior_sessions + 1) - 1.0

    # Ticket medio. TOTNEG censurado (saturado em 99999) nao produz ticket: o
    # denominador seria um teto de campo, nao a contagem real de negocios.
    usable_trades = trades.where((trades > 0) & ~censored)
    avg_ticket = volume / usable_trades

    prev_ticket = avg_ticket.shift(1)
    roll_ticket = prev_ticket.rolling(window, min_periods=window)
    ticket_z = (avg_ticket - roll_ticket.mean()) / roll_ticket.std()

    result = _long(ret_day, "ret_day")
    for frame, name in (
        (clv, "clv"),
        (gap, "gap"),
        (range_norm, "range_norm"),
        (pos252, "pos252"),
        (ret_prior, "ret_prior_20"),
        (avg_ticket, "avg_ticket"),
        (ticket_z, "ticket_z"),
    ):
        result[name] = _long(frame, name)[name]

    # Volume agregado do mercado: o mesmo numero para todos os tickers do dia.
    market = market_volume_z(bars, window).rename("mkt_vol_z")
    result = result.merge(
        market.reset_index().rename(columns={"index": "trade_date"}),
        on="trade_date",
        how="left",
    )

    # Anomalia liquida: separa evento do papel de dia de vencimento ou de
    # rebalanceamento, quando o mercado inteiro negocia mais.
    if metrics is None or metrics.empty:
        result["z_excess"] = float("nan")
    else:
        janela = metrics.loc[metrics["window_size"] == window, ["ticker", "trade_date", "z_log"]]
        result = result.merge(janela, on=["ticker", "trade_date"], how="left")
        result["z_excess"] = result["z_log"] - result["mkt_vol_z"]
        result = result.drop(columns=["z_log"])

    return result.loc[:, ["ticker", "trade_date", *FEATURE_COLUMNS]]
