"""Barras longas -> matrizes pregao x papel, com desdobramento ajustado.

O COTAHIST traz o preco como foi negociado. Num desdobramento de 1 para 2 o
preco cai pela metade de um dia para o outro, e o detector de suporte leria isso
como um rompimento. Aqui o salto e reconhecido pela abertura (abertura do dia
sobre o fechamento anterior) e os precos ANTERIORES sao divididos pelo fator,
como fazem as plataformas de grafico.

So entra salto que bate com uma fracao de desdobramento ou grupamento (1/2, 1/3,
10, ...) ou que e grande demais para ser mercado (abertura mais de 3x acima ou
abaixo). Uma queda de 45% sem fracao reconhecivel e queda de verdade e fica.
Bonificacao pequena (10%, 20%) nao e detectada: o salto se confunde com gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt
import pandas as pd

F64 = npt.NDArray[np.float64]

FRACOES = np.array(
    [
        1 / 1000,
        1 / 100,
        1 / 50,
        1 / 25,
        1 / 20,
        1 / 10,
        1 / 8,
        1 / 5,
        1 / 4,
        1 / 3,
        1 / 2,
        2,
        3,
        4,
        5,
        8,
        10,
        20,
        25,
        50,
        100,
        1000,
    ],
    dtype=np.float64,
)
# Fora desta faixa o salto de abertura e candidato a desdobramento.
SALTO_MIN = 0.62
SALTO_MAX = 1.6
# Dentro de 8% de uma fracao conhecida, vale a fracao exata.
FOLGA_FRACAO = 0.08
# Sem fracao reconhecivel, so ajusta salto maior que 3x para cima ou para baixo.
SALTO_SEM_FRACAO = 3.0


@dataclass(frozen=True)
class Matrizes:
    """Precos e volume em matrizes (pregao x papel). Dia sem negocio e NaN."""

    datas: pd.DatetimeIndex
    tickers: pd.Index
    abertura: F64
    maxima: F64
    minima: F64
    fechamento: F64
    volume: F64
    # Fator aplicado aos precos de cada dia (1 = sem ajuste).
    fator: F64

    @property
    def forma(self) -> tuple[int, int]:
        d, t = self.fechamento.shape
        return d, t


def fatores_de_desdobramento(abertura: F64, fechamento: F64) -> F64:
    """Fator de cada salto (no dia do salto); 1 nos outros dias.

    O fator e o que multiplica os precos anteriores para ficarem na escala nova.
    """
    anterior = _ultimo_valido(fechamento)
    with np.errstate(divide="ignore", invalid="ignore"):
        salto = abertura / anterior
    candidato = np.isfinite(salto) & ((salto < SALTO_MIN) | (salto > SALTO_MAX))
    fator = np.ones_like(abertura)
    if not candidato.any():
        return fator
    s = salto[candidato]
    perto = FRACOES[np.argmin(np.abs(np.log(s[:, None] / FRACOES[None, :])), axis=1)]
    bate = np.abs(perto / s - 1) < FOLGA_FRACAO
    enorme = (s > SALTO_SEM_FRACAO) | (s < 1 / SALTO_SEM_FRACAO)
    valor = np.where(bate, perto, np.where(enorme, s, 1.0))
    fator[candidato] = valor
    return fator


def _ultimo_valido(m: F64) -> F64:
    """Valor do ultimo dia negociado ANTES de cada dia (NaN se nao houve)."""
    return pd.DataFrame(m).ffill().shift(1).to_numpy(dtype=np.float64)


def ajuste_acumulado(fator: F64) -> F64:
    """Multiplicador de cada dia: produto dos fatores dos dias SEGUINTES."""
    reverso = np.cumprod(fator[::-1], axis=0)[::-1]
    depois = np.ones_like(fator)
    depois[:-1] = reverso[1:]
    return depois


def montar(
    barras: pd.DataFrame,
    tickers: list[str] | None = None,
    datas: pd.DatetimeIndex | None = None,
) -> Matrizes:
    """Matrizes ajustadas a partir das barras longas do COTAHIST.

    `barras` precisa de ticker, trade_date, open, high, low, close e
    volume_financial. `tickers` limita (e ordena) as colunas; `datas` fixa as
    linhas (o calendario de pregoes), para lotes diferentes ficarem alinhados.
    """
    frame = barras
    if tickers is not None:
        frame = frame[frame["ticker"].isin(tickers)]
    frame = frame.assign(trade_date=pd.to_datetime(frame["trade_date"]))
    largo = frame.pivot_table(
        index="trade_date",
        columns="ticker",
        values=["open", "high", "low", "close", "volume_financial"],
        aggfunc="last",
        observed=True,
    ).sort_index()
    if datas is not None:
        largo = largo.reindex(datas)
    colunas = pd.Index(tickers) if tickers is not None else largo["close"].columns

    def pega(campo: str) -> F64:
        return (
            cast(pd.DataFrame, largo[campo])
            .reindex(columns=colunas)
            .to_numpy(dtype=np.float64, copy=True)
        )

    abertura, maxima, minima, fechamento = pega("open"), pega("high"), pega("low"), pega("close")
    volume = pega("volume_financial")
    volume[volume <= 0] = np.nan

    fator = fatores_de_desdobramento(abertura, fechamento)
    ajuste = ajuste_acumulado(fator)
    return Matrizes(
        datas=pd.DatetimeIndex(largo.index),
        tickers=colunas,
        abertura=abertura * ajuste,
        maxima=maxima * ajuste,
        minima=minima * ajuste,
        fechamento=fechamento * ajuste,
        volume=volume,
        fator=fator,
    )
