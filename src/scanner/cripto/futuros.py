"""Candles diarios dos contratos perpetuos da Binance, pelo arquivo publico.

A API de futuros (`fapi.binance.com`) recusa os Estados Unidos, como o
`api.binance.com`, e nao tem espelho como o `data-api.binance.vision`. O que
chega de qualquer lugar e o arquivo publico da Binance (`data.binance.vision`):
um zip por mes (`monthly`) e um por dia (`daily`) de cada contrato, com o mesmo
candle da API e o volume em dolar (`quote_volume`).

O zip do dia sai na manha seguinte, em UTC (o de 23/11/2026 saiu as 11h03 de
24/11). Quando a rodada da noite roda, o de ontem ainda nao existe, e o contrato
fica um dia atras do BTC. A analise compara sempre nas mesmas datas, entao isso
so atrasa o ultimo dia; na noite seguinte ele entra.

Pedidos: um zip por mes ja fechado; no mes corrente -- e no anterior, enquanto o
zip dele nao sai --, um por dia, ate o primeiro que ainda nao existe (404). Nada
de buraco no meio: o que vem depois de um dia que falta fica para a outra noite.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, date, datetime, timedelta

import httpx
import pandas as pd

from scanner.cripto.binance import candles_para_barras
from scanner.ingest.cotahist import BAR_COLUMNS
from scanner.semana.fontes import FonteIndisponivelError, baixar

FONTE = "binance-futuros"
ARQUIVO = "https://data.binance.vision/data/futures/um"
# Acima disto o horario do candle esta em microssegundos (o arquivo a vista da
# Binance trocou de milissegundo para microssegundo em 2025).
MICROSSEGUNDOS = 10**14


def url_do_mes(par: str, mes: date) -> str:
    return f"{ARQUIVO}/monthly/klines/{par}/1d/{par}-1d-{mes:%Y-%m}.zip"


def url_do_dia(par: str, dia: date) -> str:
    return f"{ARQUIVO}/daily/klines/{par}/1d/{par}-1d-{dia:%Y-%m-%d}.zip"


def zip_para_candles(conteudo: bytes) -> list[list[object]]:
    """Um zip do arquivo -> candles no formato da API (`klines`).

    O CSV tem cabecalho nos arquivos novos e nao tem nos antigos: fica so a
    linha que comeca com numero.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            nomes = [n for n in pacote.namelist() if n.endswith(".csv")]
            if len(nomes) != 1:
                raise FonteIndisponivelError(FONTE, f"zip com {len(nomes)} csv")
            texto = pacote.read(nomes[0]).decode()
    except zipfile.BadZipFile as exc:
        raise FonteIndisponivelError(FONTE, "arquivo nao e zip") from exc
    candles: list[list[object]] = []
    for linha in csv.reader(io.StringIO(texto)):
        if len(linha) < 9 or not linha[0].strip().isdigit():
            continue
        abre, fecha = int(linha[0]), int(linha[6])
        if abre > MICROSSEGUNDOS:
            abre, fecha = abre // 1000, fecha // 1000
        candles.append([abre, *linha[1:6], fecha, linha[7], int(linha[8])])
    return candles


def _zip(url: str, cliente: httpx.Client | None) -> bytes | None:
    """O conteudo do zip, ou None se ele ainda nao existe (404)."""
    try:
        return baixar(FONTE, url, cliente=cliente).content
    except FonteIndisponivelError as exc:
        if exc.status == 404:
            return None
        raise


def _proximo_mes(mes: date) -> date:
    return (mes.replace(day=28) + timedelta(days=4)).replace(day=1)


def buscar_barras(
    moeda: str,
    par: str,
    desde: date,
    *,
    agora: datetime | None = None,
    cliente: httpx.Client | None = None,
) -> pd.DataFrame:
    """Barras diarias fechadas de `par`, de `desde` ate o ultimo dia ja publicado."""
    momento = agora if agora is not None else datetime.now(UTC)
    ontem = momento.astimezone(UTC).date() - timedelta(days=1)
    candles: list[list[object]] = []
    mes = desde.replace(day=1)
    acabou = False
    while mes <= ontem and not acabou:
        fim_do_mes = _proximo_mes(mes) - timedelta(days=1)
        conteudo = _zip(url_do_mes(par, mes), cliente) if fim_do_mes <= ontem else None
        if conteudo is not None:
            candles += zip_para_candles(conteudo)
        else:
            dia = max(desde, mes)
            while dia <= min(fim_do_mes, ontem):
                diario = _zip(url_do_dia(par, dia), cliente)
                if diario is None:
                    acabou = True
                    break
                candles += zip_para_candles(diario)
                dia += timedelta(days=1)
        mes = _proximo_mes(mes)
    barras = candles_para_barras(moeda, candles, momento)
    if barras.empty:
        return pd.DataFrame(columns=list(BAR_COLUMNS))
    return barras[barras["trade_date"] >= pd.Timestamp(desde)].reset_index(drop=True)
