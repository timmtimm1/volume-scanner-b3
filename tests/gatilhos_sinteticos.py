"""Barras sinteticas para os testes dos Setups.

Um papel em serra entre um fundo e um topo, periodo de 10 pregoes: o fundo vira
suporte de muitos toques e o topo, resistencia. O ultimo pregao pode ser trocado
por um martelo no suporte, com o volume que o teste quiser.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DIAS = 260
VOLUME = 1_000_000.0


def serra(fundo: float, topo: float, dias: int = DIAS, meia: int = 5) -> list[float]:
    caminho = [topo]
    while len(caminho) < dias:
        caminho += list(np.linspace(topo, fundo, meia + 1)[1:])
        caminho += list(np.linspace(fundo, topo, meia + 1)[1:])
    return caminho[:dias]


def barras(
    ticker: str = "AAAA3",
    *,
    fundo: float = 10.0,
    topo: float = 12.0,
    dias: int = DIAS,
    martelo: bool = True,
    volume_martelo: float = 2.0,
    extra: list[tuple[float, float, float, float]] | None = None,
) -> pd.DataFrame:
    """Barras longas de um papel. O ultimo dia da serra cai num fundo.

    `martelo`: troca o candle desse fundo por um martelo encostado no suporte.
    `extra`: pregoes (abertura, maxima, minima, fechamento) depois do martelo.
    """
    # termina num fundo: a serra de periodo 10 comeca no topo, fundo a cada 10
    n = dias - (dias - 6) % 10
    c = np.array(serra(fundo, topo, n))
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.fmax(o, c) + 0.05
    low = np.fmin(o, c) - 0.05
    vol = np.full(n, VOLUME)
    if martelo:
        passo = (topo - fundo) / 5
        abertura = fundo + passo - 0.08
        o[-1], c[-1] = abertura, abertura + 0.13
        h[-1], low[-1] = c[-1] + 0.03, fundo - 0.03
        vol[-1] = VOLUME * volume_martelo
    linhas = [list(x) for x in zip(o, h, low, c, vol, strict=True)]
    for a, mx, mn, f in extra or []:
        linhas.append([a, mx, mn, f, VOLUME])
    datas = pd.bdate_range("2025-01-02", periods=len(linhas))
    frame = pd.DataFrame(linhas, columns=["open", "high", "low", "close", "volume_financial"])
    frame.insert(0, "trade_date", datas.date)
    frame.insert(0, "ticker", ticker)
    return frame


def dia_do_martelo(frame: pd.DataFrame, extra: int = 0) -> object:
    return frame["trade_date"].iloc[-1 - extra]


def alta_com_martelo_na_media(
    ticker: str = "BBBB3", dias: int = 120, volume_martelo: float = 2.0
) -> pd.DataFrame:
    """Alta firme (+0,4% ao dia) e, no ultimo dia, um martelo que encosta na MMA 20.

    Sem fundos nem topos (a serie so sobe), nao ha suporte horizontal: o que
    segura o martelo e a media.
    """
    c = 10 * 1.004 ** np.arange(dias - 1)
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.fmax(o, c) + 0.05
    low = np.fmin(o, c) - 0.05
    fecha = c[-1] * 1.002
    mm20 = (c[-19:].sum() + fecha) / 20
    o = np.append(o, fecha - 0.08)  # corpo de 8 centavos: martelo, nao libelula
    h = np.append(h, fecha + 0.01)
    low = np.append(low, mm20 + 0.01)
    c = np.append(c, fecha)
    vol = np.full(dias, VOLUME)
    vol[-1] = VOLUME * volume_martelo
    frame = pd.DataFrame({"open": o, "high": h, "low": low, "close": c, "volume_financial": vol})
    frame.insert(0, "trade_date", pd.bdate_range("2025-01-02", periods=dias).date)
    frame.insert(0, "ticker", ticker)
    return frame
