"""Candles diarios da Binance (API publica de dados de mercado, sem chave).

Endereco: `data-api.binance.vision`, o espelho so de leitura que a Binance
mantem para dado de mercado. O `api.binance.com` recusa requisicoes vindas dos
Estados Unidos (HTTP 451), e e la que rodam os runners do GitHub Actions.

Cada candle e um dia UTC: abre a meia-noite UTC (21h de Brasilia da vespera) e
fecha 24 horas depois. `trade_date` e a data UTC da abertura, a mesma que
qualquer plataforma de grafico mostra no diario. O candle do dia em andamento
nunca e gravado: ele muda a cada negocio, e a regra dos setups le fechamento.

Par sempre contra USDT (dolar): o ticker gravado e a moeda (`BTC`), e o par
consultado e `BTCUSDT`. `volume_financial` e o volume em dolares do dia
(`quoteAssetVolume`), o equivalente do VOLTOT do COTAHIST.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pandas as pd

from scanner.ingest.cotahist import BAR_COLUMNS
from scanner.semana.fontes import FonteIndisponivelError, baixar

FONTE = "binance"
BASE_PADRAO = "https://data-api.binance.vision/api/v3"
# Para a carga historica do backtest, rodada na maquina do usuario: do Brasil o
# `api.binance.com` responde 25 vezes mais rapido que o espelho (1,4 s contra
# 36 s por mil candles, medido em 16/11/2026). No Actions vale o padrao.
VARIAVEL_BASE = "SCANNER_BINANCE_URL"
COTACAO = "USDT"
# Teto da API por chamada.
LIMITE = 1000
# 6.000 de peso por minuto por IP; uma chamada de candles pesa 2. A pausa so
# existe para a carga historica de centenas de pares nao encostar no teto.
PAUSA = 0.05
MS_POR_DIA = 86_400_000

# Sufixos de token alavancado da propria Binance (BTCUP, ETHDOWN, ...): nao sao
# moeda, sao derivativo empacotado, e ja foram todos deslistados.
ALAVANCADOS = ("UP", "DOWN", "BULL", "BEAR")


def _base() -> str:
    return os.environ.get(VARIAVEL_BASE, "").strip().rstrip("/") or BASE_PADRAO


def _json(caminho: str, cliente: httpx.Client | None) -> Any:
    try:
        return baixar(FONTE, f"{_base()}{caminho}", cliente=cliente).json()
    except ValueError as exc:
        raise FonteIndisponivelError(FONTE, "resposta nao e JSON") from exc


def pares_em_dolar(info: Any, *, so_negociando: bool = True) -> dict[str, str]:
    """`moeda -> par` dos pares a vista contra USDT de uma resposta de `exchangeInfo`.

    `so_negociando=False` inclui os pares parados ou deslistados (status
    diferente de TRADING) -- o backtest quer tambem quem morreu.
    """
    if not isinstance(info, dict) or not isinstance(info.get("symbols"), list):
        raise FonteIndisponivelError(FONTE, "formato inesperado (exchangeInfo sem symbols)")
    pares: dict[str, str] = {}
    for item in info["symbols"]:
        if item.get("quoteAsset") != COTACAO:
            continue
        if so_negociando and item.get("status") != "TRADING":
            continue
        moeda = str(item["baseAsset"])
        if moeda.endswith(ALAVANCADOS) and len(moeda) > 4:
            continue
        pares[moeda] = str(item["symbol"])
    return pares


def buscar_pares(
    *, so_negociando: bool = True, cliente: httpx.Client | None = None
) -> dict[str, str]:
    # A lista completa passa de 3 mil pares e alguns MB; pedindo so os que estao
    # negociando a resposta cai para um quinto (medido em 16/11/2026).
    filtro = "?permissions=SPOT&symbolStatus=TRADING" if so_negociando else "?permissions=SPOT"
    return pares_em_dolar(_json(f"/exchangeInfo{filtro}", cliente), so_negociando=so_negociando)


def candles_para_barras(moeda: str, candles: Any, agora: datetime) -> pd.DataFrame:
    """Resposta de `klines` -> barras no formato do banco, so com dia ja fechado.

    Cada candle: [abertura_ms, open, high, low, close, volume, fechamento_ms,
    volume_em_dolar, negocios, ...]. Dia sem negocio (volume zero, par
    suspenso) nao vira linha: buraco, nunca zero -- a regra do COTAHIST.
    """
    vazio = pd.DataFrame(columns=list(BAR_COLUMNS))
    if not isinstance(candles, list):
        raise FonteIndisponivelError(FONTE, f"{moeda}: formato inesperado (klines nao e lista)")
    if not candles:
        return vazio
    agora_ms = int(agora.astimezone(UTC).timestamp() * 1000)
    try:
        bruto = pd.DataFrame(
            [c[:9] for c in candles],
            columns=["abre", "open", "high", "low", "close", "volume", "fecha", "dolar", "n"],
        )
        for coluna in ("open", "high", "low", "close", "volume", "dolar"):
            bruto[coluna] = bruto[coluna].astype(float)
        bruto[["abre", "fecha", "n"]] = bruto[["abre", "fecha", "n"]].astype("int64")
    except (ValueError, TypeError, IndexError) as exc:
        raise FonteIndisponivelError(FONTE, f"{moeda}: candle fora do formato ({exc})") from exc
    bruto = bruto[(bruto["fecha"] < agora_ms) & (bruto["dolar"] > 0) & (bruto["volume"] > 0)]
    if bruto.empty:
        return vazio
    return pd.DataFrame(
        {
            "ticker": moeda,
            "trade_date": pd.to_datetime(bruto["abre"], unit="ms").dt.normalize(),
            "open": bruto["open"],
            "high": bruto["high"],
            "low": bruto["low"],
            "close": bruto["close"],
            "avg_price": bruto["dolar"] / bruto["volume"],
            # Quantidade de moedas, arredondada: a coluna e inteira (acoes).
            # Nada no pipeline le este campo; o volume que vale e o financeiro.
            "volume_shares": bruto["volume"].round().astype("int64"),
            "volume_financial": bruto["dolar"].round(2),
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
    dormir: Callable[[float], None] = time.sleep,
) -> pd.DataFrame:
    """Barras diarias fechadas de `par`, de `desde` ate ontem (UTC), paginando."""
    momento = agora if agora is not None else datetime.now(UTC)
    inicio = int(datetime(desde.year, desde.month, desde.day, tzinfo=UTC).timestamp() * 1000)
    partes: list[pd.DataFrame] = []
    while True:
        candles = _json(
            f"/klines?symbol={par}&interval=1d&limit={LIMITE}&startTime={inicio}", cliente
        )
        partes.append(candles_para_barras(moeda, candles, momento))
        if not isinstance(candles, list) or len(candles) < LIMITE:
            break
        inicio = int(candles[-1][0]) + MS_POR_DIA
        dormir(PAUSA)
    cheias = [p for p in partes if not p.empty]
    if not cheias:
        return pd.DataFrame(columns=list(BAR_COLUMNS))
    return pd.concat(cheias, ignore_index=True)


def ultimo_dia_fechado(agora: datetime | None = None) -> date:
    """A data do candle diario mais recente que ja fechou (ontem, em UTC)."""
    momento = agora if agora is not None else datetime.now(UTC)
    return momento.astimezone(UTC).date() - timedelta(days=1)
