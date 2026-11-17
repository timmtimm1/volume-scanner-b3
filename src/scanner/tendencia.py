"""Tendencia de cada ativo pela inclinacao das medias moveis (pedido de 17/11/2026).

O usuario quer escolher, no scanner e na aba Cripto, os ativos em alta, baixa
ou lateral, e procurar o setup no grafico deles. Aqui so a parte mecanica: para
o ultimo pregao, se cada media esta subindo (+1), caindo (-1) ou sem historico
para a conta (0). Quais medias combinar e escolha do usuario, no site
(`web/src/lib/tendencia.ts`): alta = todas as escolhidas subindo, baixa = todas
caindo, lateral = discordam.

"Subindo" e a media de hoje acima da de k pregoes atras, com o k das convencoes
que o projeto ja usa: a MME 9 contra o pregao anterior (a virada do Larry
Williams), a 20 contra 5, a 50 contra 10, a 80 e a 200 contra 20. Os precos sao
os ajustados por desdobramento (`matrizes.montar`, o mesmo dos setups): sem o
ajuste, um desdobramento derrubaria a media de 200 por meses.

Entra so ativo que negociou no pregao. `liquido` e a regra de liquidez do
backtest aplicada a hoje: mediana do volume financeiro dos ultimos 60 pregoes,
com pelo menos 48 negociados, acima do piso do mercado (`mercado.piso_de_liquidez`).
E descricao, nao previsao: nao alimenta alerta, setup nem backtest.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import Engine

from scanner import mercado
from scanner.gatilhos.matrizes import montar
from scanner.gatilhos.medias import media_movel

PERIODOS = (9, 20, 50, 80, 200)
TIPOS = ("MME", "MMA")
# periodo da media -> com quantos pregoes atras comparar
INCLINACAO = {9: 1, 20: 5, 50: 10, 80: 20, 200: 20}
JANELA_LIQUIDEZ = 60
MINIMO_DE_PREGOES = 48

COLUNAS_DE_MEDIA = tuple(f"{t.lower()}{p}" for t in TIPOS for p in PERIODOS)
COLUNAS = (
    "ticker",
    "trade_date",
    "fechamento",
    "variacao",
    "volume_mediano",
    "liquido",
    *COLUNAS_DE_MEDIA,
)


def _vazio() -> pd.DataFrame:
    return pd.DataFrame(columns=list(COLUNAS))


def calcular(barras: pd.DataFrame, dia: date) -> pd.DataFrame:
    """Uma linha por ativo que negociou no ultimo pregao ate `dia`.

    `barras`: ticker, trade_date, open, high, low, close, volume_financial (o
    `contexto.bars` do `scanner daily`). O pregao avaliado e o ultimo com barra
    ate `dia` -- normalmente o proprio `dia`.
    """
    if barras.empty:
        return _vazio()
    datas_barras = pd.to_datetime(barras["trade_date"])
    barras = barras[datas_barras <= pd.Timestamp(dia)]
    if barras.empty:
        return _vazio()

    m = montar(barras)
    fech = m.fechamento
    ultimo = len(m.datas) - 1
    negociou = np.isfinite(fech[ultimo])
    if not negociou.any():
        return _vazio()

    dados: dict[str, object] = {}
    for tipo in TIPOS:
        for p in PERIODOS:
            mm = media_movel(fech, tipo, p)
            k = INCLINACAO[p]
            hoje = mm[ultimo]
            antes = mm[ultimo - k] if ultimo - k >= 0 else np.full_like(hoje, np.nan)
            with np.errstate(invalid="ignore"):
                s = np.where(hoje > antes, 1, np.where(hoje < antes, -1, 0))
            s[~(np.isfinite(hoje) & np.isfinite(antes))] = 0
            dados[f"{tipo.lower()}{p}"] = s.astype(np.int16)

    # Variacao do dia sobre o ultimo fechamento anterior (preco ajustado: um
    # desdobramento hoje nao vira queda de 50%).
    variacao = np.full(fech.shape[1], np.nan)
    if ultimo > 0:
        anterior = pd.DataFrame(fech[:ultimo]).ffill().to_numpy()[-1]
        with np.errstate(invalid="ignore", divide="ignore"):
            variacao = fech[ultimo] / anterior - 1

    janela = m.volume[max(0, ultimo - JANELA_LIQUIDEZ + 1) : ultimo + 1]
    negociados = np.isfinite(janela).sum(axis=0)
    # Ativo sem nenhum volume na janela da coluna toda NaN: a mediana e NaN e o
    # numpy avisa ("All-NaN slice"); o aviso nao diz nada que o NaN ja nao diga.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mediana = np.nanmedian(janela, axis=0)
    liquido = (negociados >= MINIMO_DE_PREGOES) & (mediana >= mercado.piso_de_liquidez())

    # O fechamento gravado e o do proprio dia, sem ajuste: e o preco que a tela mostra.
    # No ultimo pregao o ajuste acumulado e 1, entao o ajustado ja e o real.
    saida = pd.DataFrame(
        {
            "ticker": m.tickers.astype(str),
            "trade_date": m.datas[ultimo].date(),
            "fechamento": fech[ultimo],
            "variacao": variacao,
            "volume_mediano": mediana,
            "liquido": liquido,
            **dados,
        }
    )
    saida = saida[negociou].reset_index(drop=True)
    saida["variacao"] = saida["variacao"].where(np.isfinite(saida["variacao"]), np.nan)
    return pd.DataFrame(saida.loc[:, list(COLUNAS)])


@dataclass(frozen=True)
class RelatorioDeTendencias:
    """O que a etapa de tendencia do pregao fez."""

    dia: date
    ativos: int = 0
    liquidos: int = 0
    # pela combinacao padrao do site (MME 20 + MME 80), so para o log
    alta: int = 0
    baixa: int = 0
    dry_run: bool = False

    def summary(self) -> str:
        if self.ativos == 0:
            base = "tendencia: nenhum ativo negociado no pregao"
        else:
            verbo = "nao gravados" if self.dry_run else "gravados"
            lateral = self.liquidos - self.alta - self.baixa
            base = (
                f"tendencia: {self.ativos} ativos {verbo} ({self.liquidos} liquidos; pela "
                f"MME 20 + 80: {self.alta} em alta, {self.baixa} em baixa, {lateral} lateral "
                "ou sem historico)"
            )
        return f"[dry-run] {base}" if self.dry_run else base


def run_tendencias(
    engine: Engine, dia: date, *, bars: pd.DataFrame, dry_run: bool = False
) -> RelatorioDeTendencias:
    """Calcula a inclinacao das medias no pregao e troca a tabela `tendencias`."""
    from scanner.storage.repository import gravar_tendencias

    frame = calcular(bars, dia)
    if frame.empty:
        return RelatorioDeTendencias(dia=dia, dry_run=dry_run)
    liq = frame[frame["liquido"].astype(bool)]
    alta = int(((liq["mme20"] == 1) & (liq["mme80"] == 1)).sum())
    baixa = int(((liq["mme20"] == -1) & (liq["mme80"] == -1)).sum())
    if not dry_run:
        gravar_tendencias(engine, frame)
    return RelatorioDeTendencias(
        dia=dia,
        ativos=len(frame),
        liquidos=len(liq),
        alta=alta,
        baixa=baixa,
        dry_run=dry_run,
    )
