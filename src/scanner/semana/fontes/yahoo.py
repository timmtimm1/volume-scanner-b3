"""Ibovespa, dolar, Brent e ouro pelo Yahoo Finance.

Calendario de dias corridos, nao o da B3: o Brent e o ouro negociam em dias que
a B3 fecha (segunda 12/10/2026 tem Brent a US$ 106,65 e nenhum Ibovespa), e a
base da variacao da semana e "o ultimo ponto antes da segunda", seja qual for o
dia em que ele cai.
"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx
import pandas as pd

from scanner.semana.fontes import FonteIndisponivelError, baixar
from scanner.semana.periodo import Semana

FONTE = "yahoo"
BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
SIMBOLOS = {"ibovespa": "^BVSP", "dolar": "BRL=X", "brent": "BZ=F", "ouro": "GC=F"}

# Medido em 17/10/2026: com o User-Agent de navegador do resto do pacote
# (Chrome/130) o Yahoo responde 429 em toda requisicao; com este, o mesmo que o
# modulo de cotacoes ja usa, responde 200. Nao e um favor: e o que funciona.
USER_AGENT = "Mozilla/5.0 (compatible; volume-scanner-b3)"

# Ponto final mais velho que isto em relacao a sexta = serie parada (ativo
# deslistado, simbolo errado), e nao um fim de semana comprido.
DEFASAGEM_MAXIMA_DIAS = 7


def ler_serie(dados: Any) -> pd.Series:
    """Serie de fechamentos (indice = data local do ativo) do JSON do Yahoo.

    A data e o carimbo mais o `gmtoffset` do ativo, convertido para dia: o
    carimbo do Ibovespa e 13:00 UTC, o do Brent e meia-noite local. Ponto sem
    fechamento (`None`) e descartado, nao vira zero.
    """
    try:
        resultado = dados["chart"]["result"][0]
        deslocamento = int(resultado["meta"]["gmtoffset"])
        carimbos = resultado["timestamp"]
        fechamentos = resultado["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise FonteIndisponivelError(FONTE, f"formato inesperado ({exc!r})") from exc
    if not isinstance(carimbos, list) or not isinstance(fechamentos, list):
        raise FonteIndisponivelError(FONTE, "formato inesperado (series nao sao listas)")
    if len(carimbos) != len(fechamentos):
        raise FonteIndisponivelError(FONTE, "timestamp e close com tamanhos diferentes")

    pontos = {
        datetime.fromtimestamp(int(t) + deslocamento, UTC).date(): float(c)
        for t, c in zip(carimbos, fechamentos, strict=True)
        if c is not None
    }
    serie = pd.Series(pontos, dtype="float64").sort_index()
    serie.index = pd.to_datetime(serie.index)
    return serie


def _ultimo_ate(serie: pd.Series, limite: date) -> tuple[date, float] | None:
    """Ultimo ponto com data <= `limite`, ou None."""
    ate = serie.loc[: pd.Timestamp(limite)]
    if ate.empty:
        return None
    return ate.index[-1].date(), float(ate.iloc[-1])


def variacoes_da_serie(serie: pd.Series, semana: Semana) -> dict[str, Any]:
    """Valor na sexta e variacao na semana, no mes e no ano (fracoes; None sem base).

    valor/data = ultimo ponto <= sexta. Semana = contra o ultimo ponto antes da
    segunda. Mes e ano = contra o ultimo ponto do mes e do ano ANTERIORES ao da
    data do valor.
    """
    final = _ultimo_ate(serie, semana.sexta)
    if final is None:
        raise FonteIndisponivelError(FONTE, "serie sem ponto ate a sexta da semana")
    data, valor = final
    if (semana.sexta - data).days > DEFASAGEM_MAXIMA_DIAS:
        raise FonteIndisponivelError(
            FONTE, f"ultimo ponto e de {data.isoformat()}, velho demais para a semana"
        )

    ultimo_dia_mes_anterior = date(data.year, data.month, 1) - timedelta(days=1)
    bases = {
        "semana": semana.segunda - timedelta(days=1),
        "mes": ultimo_dia_mes_anterior,
        "ano": date(data.year - 1, 12, 31),
    }
    resultado: dict[str, Any] = {"valor": valor, "data": data.isoformat()}
    for nome, limite in bases.items():
        base = _ultimo_ate(serie, limite)
        resultado[nome] = None if base is None else valor / base[1] - 1
    return resultado


def buscar_serie(simbolo: str, semana: Semana, *, cliente: httpx.Client | None = None) -> pd.Series:
    """Baixa os fechamentos diarios desde o fim do ano anterior (com folga de 10 dias)."""
    inicio = date(semana.fim.year - 1, 12, 31) - timedelta(days=10)
    fim = semana.sexta + timedelta(days=1)
    p1 = calendar.timegm(inicio.timetuple())
    p2 = calendar.timegm(fim.timetuple())
    url = f"{BASE_URL}/{quote(simbolo, safe='=')}?period1={p1}&period2={p2}&interval=1d"
    resposta = baixar(FONTE, url, cliente=cliente, headers={"User-Agent": USER_AGENT})
    try:
        dados = resposta.json()
    except ValueError as exc:
        raise FonteIndisponivelError(FONTE, "resposta nao e JSON") from exc
    return ler_serie(dados)


def abertura(semana: Semana, *, cliente: httpx.Client | None = None) -> dict[str, Any]:
    """Ibovespa, dolar, Brent e ouro. Um que falha vira `{"erro": ...}` sozinho."""
    saida: dict[str, Any] = {}
    for nome, simbolo in SIMBOLOS.items():
        try:
            saida[nome] = variacoes_da_serie(buscar_serie(simbolo, semana, cliente=cliente), semana)
        except FonteIndisponivelError as exc:
            saida[nome] = {"erro": exc.motivo}
    return saida
