"""Candles, contexto e matrizes ajustadas (scanner.gatilhos)."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd
import pytest

from scanner.gatilhos.candles import padroes
from scanner.gatilhos.contexto import RegrasDeContexto, atr_wilder, calcular
from scanner.gatilhos.matrizes import ajuste_acumulado, fatores_de_desdobramento, montar

F64 = npt.NDArray[np.float64]


def _col(*v: float) -> F64:
    return np.array(v, dtype=np.float64)[:, None]


def _padrao(barras: list[tuple[float, float, float, float]], atr: float = 1.0) -> dict[str, bool]:
    o, h, low, c = (_col(*x) for x in zip(*barras, strict=True))
    res = padroes(o, h, low, c, np.full_like(c, atr))
    return {k: bool(v[-1, 0]) for k, v in res.items()}


def test_martelo_e_quase_martelo() -> None:
    # abre 10, minima 8, fecha 10,3, maxima 10,35: sombra de baixo 2,0, corpo 0,3
    assert _padrao([(10, 10.35, 8, 10.3)])["martelo"]
    # sombra de cima grande demais: nao e martelo
    assert not _padrao([(10, 11, 8, 10.3)])["martelo"]
    # candle minusculo (range 0,3 < meio ATR): ruido, nao martelo
    assert not _padrao([(10, 10.06, 9.76, 10.05)])["martelo"]


def test_doji_libelula() -> None:
    r = _padrao([(10, 10.05, 8.5, 10.02)])
    assert r["libelula"]
    assert not r["martelo"]


def test_engolfo_e_piercing() -> None:
    assert _padrao([(11, 11.1, 9.9, 10), (9.9, 11.2, 9.8, 11.1)])["engolfo"]
    # verde que fecha acima da metade do vermelho, sem engolir: piercing
    r = _padrao([(11, 11.1, 9.9, 10), (9.8, 10.7, 9.7, 10.6)])
    assert r["piercing"]
    assert not r["engolfo"]
    # o "vermelho" anterior e quase um doji (corpo 0,04): engolir isso nao e engolfo
    assert not _padrao([(10.30, 10.4, 10.2, 10.26), (10.25, 10.6, 10.2, 10.5)])["engolfo"]
    # fecha abaixo da metade: nenhum dos dois
    r = _padrao([(11, 11.1, 9.9, 10), (9.8, 10.4, 9.7, 10.3)])
    assert not r["piercing"] and not r["engolfo"]


def test_estrela_da_manha() -> None:
    barras = [(12, 12.1, 10.9, 11), (10.9, 11.0, 10.6, 10.8), (10.9, 11.8, 10.85, 11.7)]
    assert _padrao(barras)["estrela"]
    barras[2] = (10.9, 11.4, 10.85, 11.3)  # nao passa da metade do primeiro (11,5)
    assert not _padrao(barras)["estrela"]


def test_candle_de_forca() -> None:
    assert _padrao([(10, 11.55, 9.95, 11.5)])["forca"]
    assert not _padrao([(10, 12.5, 9.95, 11.5)])["forca"]  # fechou longe da maxima


def test_rvol_usa_so_os_dias_anteriores() -> None:
    vol = np.full((40, 1), 100.0)
    vol[30, 0] = 500.0
    ctx = calcular(np.full((40, 1), 11.0), np.full((40, 1), 10.0), vol, RegrasDeContexto())
    rvol = ctx["rvol"]
    assert rvol[30, 0] == pytest.approx(5.0)
    assert rvol[31, 0] == pytest.approx(1.0)  # mediana resiste ao pico do dia 30


def test_queda_recente_e_tendencia_de_baixa() -> None:
    c = np.concatenate([np.linspace(30, 20, 230), [19, 18, 17]])[:, None]
    ctx = calcular(c * 1.01, c, np.full_like(c, 1e6), RegrasDeContexto())
    assert bool(ctx["baixa"][-1, 0])
    assert bool(ctx["queda"][-1, 0])  # de ~21 para 18 em 20 pregoes = -14%
    assert not bool(ctx["correcao"][-1, 0])


def test_atr_ignora_dia_sem_negocio() -> None:
    h = np.full((30, 1), 11.0)
    low = np.full((30, 1), 9.0)
    c = np.full((30, 1), 10.0)
    c[20, 0] = np.nan
    atr = atr_wilder(h, low, c)
    assert np.isnan(atr[20, 0])
    assert atr[25, 0] == pytest.approx(2.0)


def test_desdobramento_ajusta_o_passado_e_queda_nao() -> None:
    fech = _col(40, 41, 20.4, 20.6, 11, 11.2)
    abre = _col(40, 40.5, 20.5, 20.4, 11.5, 11.1)
    fator = fatores_de_desdobramento(abre, fech)
    # 1 para 2 no dia 2; a queda de 47% no dia 4 nao bate fracao: fica
    assert fator[:, 0].tolist() == [1, 1, 0.5, 1, 1, 1]
    ajuste = ajuste_acumulado(fator)
    assert (fech * ajuste)[:, 0].tolist() == pytest.approx([20, 20.5, 20.4, 20.6, 11, 11.2])


def test_montar_matrizes_com_buraco() -> None:
    barras = pd.DataFrame(
        {
            "ticker": ["AAAA3", "AAAA3", "BBBB4"],
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-03"]),
            "open": [10.0, 10.5, 5.0],
            "high": [11.0, 11.0, 5.5],
            "low": [9.5, 10.0, 4.8],
            "close": [10.5, 10.8, 5.2],
            "volume_financial": [1e6, 2e6, 0.0],
        }
    )
    m = montar(barras)
    assert m.forma == (2, 2)
    assert np.isnan(m.fechamento[0, 1])
    assert np.isnan(m.volume[1, 1])  # volume zero vira buraco, nunca zero
