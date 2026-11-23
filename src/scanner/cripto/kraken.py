"""Candles diarios da Kraken, para as moedas que a Binance nao negocia.

A XMR esta suspensa na Binance desde 2024. Na Kraken o candle diario tambem vai
de meia-noite a meia-noite UTC, entao entra no mesmo pipeline sem ajuste. O par
e contra o dolar (XMRUSD), e o volume e so o da Kraken: ele serve para comparar
a moeda com o proprio historico, nao com o volume das moedas da Binance.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx
import pandas as pd

from scanner.ingest.cotahist import BAR_COLUMNS
from scanner.semana.fontes import FonteIndisponivelError, baixar

FONTE = "kraken"
BASE = "https://api.kraken.com/0/public"
INTERVALO_DIARIO = 1440
SEGUNDOS_POR_DIA = 86_400


def resultado_do_par(dados: Any) -> Any:
    """O conteudo do unico par pedido, na resposta `{error, result}` da Kraken."""
    if not isinstance(dados, dict):
        raise FonteIndisponivelError(FONTE, "formato inesperado (resposta nao e objeto)")
    if dados.get("error"):
        raise FonteIndisponivelError(FONTE, f"recusado: {dados['error']}")
    resultado = dados.get("result")
    if not isinstance(resultado, dict):
        raise FonteIndisponivelError(FONTE, "formato inesperado (sem result)")
    chaves = [k for k in resultado if k != "last"]
    if len(chaves) != 1:
        raise FonteIndisponivelError(FONTE, f"esperava um par, vieram {len(chaves)}")
    return resultado[chaves[0]]


def candles_para_barras(moeda: str, candles: Any, agora: datetime) -> pd.DataFrame:
    """Resposta de `OHLC` -> barras no formato do banco, so com dia ja fechado.

    Cada candle: [abertura_s, open, high, low, close, vwap, volume, negocios].
    Dia sem negocio nao vira linha: buraco, nunca zero.
    """
    vazio = pd.DataFrame(columns=list(BAR_COLUMNS))
    if not isinstance(candles, list):
        raise FonteIndisponivelError(FONTE, f"{moeda}: formato inesperado (OHLC nao e lista)")
    if not candles:
        return vazio
    try:
        bruto = pd.DataFrame(
            [c[:8] for c in candles],
            columns=["abre", "open", "high", "low", "close", "vwap", "volume", "n"],
        )
        for coluna in ("open", "high", "low", "close", "vwap", "volume"):
            bruto[coluna] = bruto[coluna].astype(float)
        bruto[["abre", "n"]] = bruto[["abre", "n"]].astype("int64")
    except (ValueError, TypeError, IndexError) as exc:
        raise FonteIndisponivelError(FONTE, f"{moeda}: candle fora do formato ({exc})") from exc
    agora_s = int(agora.astimezone(UTC).timestamp())
    fechado = bruto["abre"] + SEGUNDOS_POR_DIA <= agora_s
    bruto = bruto[fechado & (bruto["vwap"] > 0) & (bruto["volume"] > 0)]
    if bruto.empty:
        return vazio
    return pd.DataFrame(
        {
            "ticker": moeda,
            "trade_date": pd.to_datetime(bruto["abre"], unit="s").dt.normalize(),
            "open": bruto["open"],
            "high": bruto["high"],
            "low": bruto["low"],
            "close": bruto["close"],
            "avg_price": bruto["vwap"],
            # Quantidade de moedas, arredondada: a coluna e inteira (acoes).
            "volume_shares": bruto["volume"].round().astype("int64"),
            "volume_financial": (bruto["vwap"] * bruto["volume"]).round(2),
            "trades_count": bruto["n"].clip(upper=2_147_483_647),
            "trades_censored": False,
        }
    ).reset_index(drop=True)


def buscar_barras(
    moeda: str,
    par: str,
    desde: date,
    *,
    agora: datetime | None = None,
    cliente: httpx.Client | None = None,
) -> pd.DataFrame:
    """Barras diarias fechadas de `par`, de `desde` ate ontem (UTC).

    A Kraken devolve ate 720 candles numa chamada, mais do que os 400 dias que o
    banco guarda: nao precisa paginar.
    """
    momento = agora if agora is not None else datetime.now(UTC)
    inicio = int(datetime(desde.year, desde.month, desde.day, tzinfo=UTC).timestamp())
    url = f"{BASE}/OHLC?pair={par}&interval={INTERVALO_DIARIO}&since={inicio - 1}"
    try:
        dados = baixar(FONTE, url, cliente=cliente).json()
    except ValueError as exc:
        raise FonteIndisponivelError(FONTE, "resposta nao e JSON") from exc
    barras = candles_para_barras(moeda, resultado_do_par(dados), momento)
    if barras.empty:
        return barras
    return barras[barras["trade_date"] >= pd.Timestamp(desde)].reset_index(drop=True)
