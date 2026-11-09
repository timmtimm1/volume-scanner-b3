"""A suite de backtest num lote de papeis (scanner.backtest.suite)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scanner.backtest.suite import liquidez_historica, rodar_lote, sem_sobreposicao, sortear
from scanner.config import SetupsConfig


def test_um_trade_por_vez_por_papel() -> None:
    col = np.array([0, 0, 0, 1, 0])
    entrada = np.array([1, 3, 6, 3, 20])
    saida = np.array([5, 8, 9, 4, -1])
    fica = sem_sobreposicao(col, entrada, saida)
    # o de entrada 3 entra com o primeiro aberto (ate 5); o de 6 entra depois dele
    assert list(fica) == [True, False, True, True, True]


def test_trade_aberto_bloqueia_os_seguintes() -> None:
    fica = sem_sobreposicao(np.array([0, 0]), np.array([1, 30]), np.array([-1, 40]))
    assert list(fica) == [True, False]


def test_controle_nunca_sorteia_o_proprio_papel() -> None:
    rng = np.random.default_rng(0)
    ok = np.ones((5, 4), dtype=bool)
    dias = np.zeros(2000, dtype=np.int64)
    fora = np.full(2000, 2, dtype=np.int64)
    escolha = sortear(ok, dias, fora, rng)
    assert (escolha != 2).all()
    assert set(escolha.tolist()) == {0, 1, 3}


def test_controle_sem_outro_papel_liquido_fica_vazio() -> None:
    ok = np.zeros((3, 3), dtype=bool)
    ok[1, 0] = True
    escolha = sortear(ok, np.array([1, 1]), np.array([0, 1]), np.random.default_rng(1))
    assert list(escolha) == [-1, 0]


def _barras(
    n: int = 420, semente: int = 4, volumes: dict[str, float] | None = None
) -> pd.DataFrame:
    rng = np.random.default_rng(semente)
    datas = pd.bdate_range("2019-01-02", periods=n)
    linhas = []
    for t, vol in (volumes or {"AAAA3": 5e6, "BBBB3": 5e6, "CCCC3": 5e6}).items():
        c = 20 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, n)))
        o = np.concatenate([[c[0]], c[:-1]]) * (1 + rng.normal(0, 0.003, n))
        h = np.fmax(o, c) * (1 + np.abs(rng.normal(0, 0.008, n)))
        low = np.fmin(o, c) * (1 - np.abs(rng.normal(0, 0.008, n)))
        for d, *v in zip(datas, o, h, low, c, strict=True):
            linhas.append(
                {
                    "ticker": t,
                    "trade_date": d.date(),
                    "open": v[0],
                    "high": v[1],
                    "low": v[2],
                    "close": v[3],
                    "volume_financial": vol,
                }
            )
    return pd.DataFrame(linhas)


def test_liquidez_usa_so_o_passado() -> None:
    b = _barras(200, volumes={"AAAA3": 5e6, "BBBB3": 1e4})
    sessoes = pd.DatetimeIndex(sorted(pd.to_datetime(b["trade_date"].unique())))
    liq = liquidez_historica(b, sessoes)
    assert not liq["AAAA3"].iloc[:48].any()  # sem 48 pregoes de historia ainda nao da para saber
    assert liq["AAAA3"].iloc[70:].all()
    assert not liq["BBBB3"].any()
    # volume enorme no futuro nao muda o passado
    b2 = b.copy()
    b2.loc[
        (b2["ticker"] == "BBBB3") & (pd.to_datetime(b2["trade_date"]) >= sessoes[150]),
        "volume_financial",
    ] = 1e9
    liq2 = liquidez_historica(b2, sessoes)
    assert (liq2["AAAA3"].iloc[:150] == liq["AAAA3"].iloc[:150]).all()
    assert not liq2["BBBB3"].iloc[:151].any()


def test_rodar_lote_devolve_trades_de_toda_saida() -> None:
    b = _barras()
    sessoes = pd.DatetimeIndex(sorted(pd.to_datetime(b["trade_date"].unique())))
    tickers = ["AAAA3", "BBBB3", "CCCC3"]
    liq = pd.DataFrame(True, index=sessoes, columns=tickers)
    t = rodar_lote(b, tickers, sessoes, liq, SetupsConfig(), semente=1)
    assert set(t["saida"].unique()) == {"alvo1", "alvo2", "alvo3", "minimas", "mme9"}
    # (o 9.1 pede volume de 1,5x desde 06/11/2026; aqui o volume e constante)
    assert {"123", "pfr"} <= set(t["setup"].unique())
    fechado = t[t["motivo"] != 0]
    assert np.isfinite(fechado["r"]).all()
    assert (fechado["r"] >= -20).all()
    assert (t["data_entrada"] > t["data_sinal"]).all()
    assert (fechado["data_saida"] >= fechado["data_entrada"]).all()
    assert (t["stop"] < t["entrada"]).all()
    assert np.isfinite(t["r_controle"]).mean() > 0.9


def test_papel_fora_do_universo_nao_opera() -> None:
    b = _barras()
    sessoes = pd.DatetimeIndex(sorted(pd.to_datetime(b["trade_date"].unique())))
    tickers = ["AAAA3", "BBBB3", "CCCC3"]
    liq = pd.DataFrame(True, index=sessoes, columns=tickers)
    liq["BBBB3"] = False
    t = rodar_lote(b, tickers, sessoes, liq, SetupsConfig(), semente=1)
    assert "BBBB3" not in set(t["ticker"].astype(str))
