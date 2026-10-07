"""Testes do script de analise `scripts/backtest_variacao.py`.

O coracao sao tres eventos montados de forma que cada numero possa ser
conferido a mao. As contas estao nos comentarios, ao lado do valor esperado.

Calendario: 101 pregoes (posicoes 0..100). DATA_CORTE na posicao 95.

- AAAA, evento em t=70. Antes: fecha 100 nas posicoes pares e 101 nas impares.
  Depois: close(70+k) = 100 + k, high = close + 1, low = close - 1.
- BBBB, evento em 75, 76 e 77 (um bloco so, conta em 75). Antes: 50 nas pares,
  51 nas impares. Depois: close(75+k) = 51 - k, high = close + 0.2, low = close - 0.3.
- CCCC, evento em t=80, dia em que o mercado inteiro negocia 20x o normal
  (mkt_vol_z alto). Antes: 20 nas pares, 20.4 nas impares. Depois: alterna
  21 (k impar) e 20 (k par), high = close + 0.5, low = close - 0.5.
- DDDD so fornece dias de controle.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest
from scripts.backtest_variacao import (
    Dados,
    Parametros,
    amostrar_controle,
    carregar,
    contagens,
    montar_matrizes,
    observar,
    resumir,
    selecionar_eventos,
    versoes,
)
from sqlalchemy import Engine, text

CALENDARIO = pd.bdate_range("2026-01-05", periods=101)
CORTE = CALENDARIO[95].date()

# Desvio amostral de 30 retornos `a` e 30 retornos `b`: media (a+b)/2, cada desvio
# vale +-(a-b)/2, soma dos quadrados 60*((a-b)/2)^2, dividida por 59.
SIGMA_A = (0.01 - (-1 / 101)) / 2 * math.sqrt(60 / 59)  # +1% e -1/101: 0.0100345
SIGMA_B = (0.02 - (-1 / 51)) / 2 * math.sqrt(60 / 59)  # +2% e -1/51: 0.0199710
SIGMA_C = (0.02 - (-0.4 / 20.4)) / 2 * math.sqrt(60 / 59)  # 20 -> 20.4 -> 20: = SIGMA_B


def _serie(
    t: int, antes: tuple[float, float], depois: list[float], folga: tuple[float, float]
) -> pd.DataFrame:
    """Barras de um papel: alterna `antes` ate t, segue `depois` a partir de t+1."""
    close = [antes[pos % 2] for pos in range(t + 1)] + depois
    close = close[: len(CALENDARIO)]
    pos = np.arange(len(close))
    alto = np.where(pos <= t, 0.5, folga[0])
    baixo = np.where(pos <= t, 0.5, folga[1])
    return pd.DataFrame(
        {
            "trade_date": CALENDARIO[: len(close)],
            "close": close,
            "high": np.array(close) + alto,
            "low": np.array(close) - baixo,
        }
    )


def _dados() -> Dados:
    a = _serie(70, (100.0, 101.0), [100.0 + k for k in range(1, 31)], (1.0, 1.0))
    b = _serie(75, (50.0, 51.0), [51.0 - k for k in range(1, 26)], (0.2, 0.3))
    c = _serie(80, (20.0, 20.4), [21.0 if k % 2 else 20.0 for k in range(1, 21)], (0.5, 0.5))
    d = _serie(100, (30.0, 30.3), [], (0.0, 0.0))
    partes = []
    for ticker, frame in (("AAAA", a), ("BBBB", b), ("CCCC", c), ("DDDD", d)):
        frame = frame.assign(ticker=ticker)
        pos = np.arange(len(frame))
        # Volume com variacao determinista (o mkt_vol_z precisa de desvio > 0).
        frame["volume_financial"] = 1e6 * (1 + 0.05 * ((pos * 7) % 5))
        partes.append(frame)
    bars = pd.concat(partes, ignore_index=True)
    bars.loc[bars["trade_date"] == CALENDARIO[80], "volume_financial"] *= 20

    z = bars.loc[:, ["ticker", "trade_date"]].assign(z_log=0.0)
    picos = {("AAAA", 70), ("BBBB", 75), ("BBBB", 76), ("BBBB", 77), ("CCCC", 80), ("AAAA", 30)}
    for ticker, posicao in picos:
        z.loc[(z["ticker"] == ticker) & (z["trade_date"] == CALENDARIO[posicao]), "z_log"] = 7.0
    eventos = pd.DataFrame({"ticker": ["AAAA"], "trade_date": [CALENDARIO[70]]})
    return Dados(bars=bars, z=z, eventos_tabela=eventos)


def _corta(dados: Dados, corte: date) -> Dados:
    limite = pd.Timestamp(corte)
    return Dados(
        bars=dados.bars[dados.bars["trade_date"] <= limite].reset_index(drop=True),
        z=dados.z[dados.z["trade_date"] <= limite].reset_index(drop=True),
        eventos_tabela=dados.eventos_tabela,
    )


PARAMS = Parametros(data_corte=CORTE, min_volume_brl=500_000.0)


def _evento(obs: pd.DataFrame, ticker: str, n: int) -> pd.Series:
    linha = obs[(obs["grupo"] == "evento") & (obs["ticker"] == ticker) & (obs["N"] == n)]
    assert len(linha) == 1, f"{ticker} N={n}: {len(linha)} linhas"
    return linha.iloc[0]


@pytest.fixture(scope="module")
def obs_corte() -> pd.DataFrame:
    return observar(_corta(_dados(), CORTE), PARAMS)


# ------------------------------------------------------------ os tres eventos, a mao


@pytest.mark.parametrize(
    ("n", "var_abs", "amplitude"),
    [
        (1, 0.01, 0.02),  # close 101; high(71)=102, low(71)=100 -> 2/100
        (5, 0.05, 0.06),  # close 105; max high 106 (t+5), min low 100 (t+1)
        (10, 0.10, 0.11),  # close 110; 111 - 100
        (20, 0.20, 0.21),  # close 120; 121 - 100
    ],
)
def test_evento_aaaa_conferido_a_mao(
    obs_corte: pd.DataFrame, n: int, var_abs: float, amplitude: float
) -> None:
    linha = _evento(obs_corte, "AAAA", n)
    assert linha["trade_date"] == CALENDARIO[70]
    assert linha["sigma60"] == pytest.approx(SIGMA_A)
    assert linha["var_abs"] == pytest.approx(var_abs)
    assert linha["amplitude"] == pytest.approx(amplitude)
    assert linha["var_abs_norm"] == pytest.approx(var_abs / SIGMA_A)
    assert linha["amplitude_norm"] == pytest.approx(amplitude / SIGMA_A)
    assert not linha["mkt_alto"]


@pytest.mark.parametrize(
    ("n", "var_abs", "amplitude"),
    [
        (1, 1 / 51, (50.2 - 49.7) / 51),  # close 50; high 50.2, low 49.7
        (5, 5 / 51, (50.2 - 45.7) / 51),  # close 46; max high em t+1, min low 46-0.3
        (20, 20 / 51, (50.2 - 30.7) / 51),  # close 31; min low 31-0.3
    ],
)
def test_evento_bbbb_bloco_conta_no_primeiro_dia(
    obs_corte: pd.DataFrame, n: int, var_abs: float, amplitude: float
) -> None:
    linha = _evento(obs_corte, "BBBB", n)
    assert linha["trade_date"] == CALENDARIO[75]
    assert linha["dias_no_bloco"] == 3
    assert linha["sigma60"] == pytest.approx(SIGMA_B)
    assert linha["var_abs"] == pytest.approx(var_abs)
    assert linha["amplitude"] == pytest.approx(amplitude)
    assert linha["amplitude_norm"] == pytest.approx(amplitude / SIGMA_B)


@pytest.mark.parametrize(
    ("n", "var_abs", "amplitude"),
    [
        (1, 0.05, (21.5 - 20.5) / 20),  # close 21; so o dia t+1
        (5, 0.05, (21.5 - 19.5) / 20),  # close 21 (k=5 impar); min low em k=2
        (10, 0.0, (21.5 - 19.5) / 20),  # close 20 (k=10 par)
    ],
)
def test_evento_cccc_com_mercado_alto(
    obs_corte: pd.DataFrame, n: int, var_abs: float, amplitude: float
) -> None:
    linha = _evento(obs_corte, "CCCC", n)
    assert linha["sigma60"] == pytest.approx(SIGMA_C)
    assert linha["var_abs"] == pytest.approx(var_abs, abs=1e-12)
    assert linha["amplitude"] == pytest.approx(amplitude)
    assert linha["mkt_vol_z"] > PARAMS.limiar_mkt_alto
    assert linha["mkt_alto"]


# ------------------------------------------------------------ regras


def test_horizonte_sem_pregoes_a_frente_ou_alem_do_corte_sai(obs_corte: pd.DataFrame) -> None:
    eventos = obs_corte[obs_corte["grupo"] == "evento"]
    # AAAA: t+30 e a posicao 100, depois do corte (95). CCCC: t+20 = 100, t+30 nem existe.
    assert set(eventos.loc[eventos["ticker"] == "AAAA", "N"]) == {1, 5, 10, 20}
    assert set(eventos.loc[eventos["ticker"] == "CCCC", "N"]) == {1, 5, 10}
    assert (eventos["data_fim"] <= pd.Timestamp(CORTE)).all()


def test_sem_corte_os_horizontes_voltam() -> None:
    obs = observar(_dados(), replace(PARAMS, data_corte=None))
    eventos = obs[obs["grupo"] == "evento"]
    assert set(eventos.loc[eventos["ticker"] == "AAAA", "N"]) == {1, 5, 10, 20, 30}
    # 100+30 = 130; high 131, low 100.
    assert _evento(obs, "AAAA", 30)["amplitude"] == pytest.approx(0.31)
    assert set(eventos.loc[eventos["ticker"] == "CCCC", "N"]) == {1, 5, 10, 20}


def test_evento_sem_60_pregoes_de_historia_sai() -> None:
    # AAAA tem z=7 tambem na posicao 30: so 29 retornos antes, menos que os 50 exigidos.
    obs = observar(_dados(), replace(PARAMS, data_corte=None))
    assert CALENDARIO[30] not in set(obs.loc[obs["grupo"] == "evento", "trade_date"])
    m = montar_matrizes(_dados().bars, PARAMS)
    assert len(selecionar_eventos(_dados(), m, PARAMS)) == 4  # AAAA x2, BBBB, CCCC


def test_preco_posterior_ao_corte_nao_muda_nada() -> None:
    dados = _dados()
    mexido = dados.bars.copy()
    depois = mexido["trade_date"] > pd.Timestamp(CORTE)
    mexido.loc[depois, ["close", "high", "low"]] *= 7.0
    original = observar(dados, PARAMS)
    alterado = observar(Dados(mexido, dados.z, dados.eventos_tabela), PARAMS)
    pd.testing.assert_frame_equal(original, alterado)
    # E ler so ate o corte da o mesmo que ler tudo e respeitar t+N <= corte.
    pd.testing.assert_frame_equal(observar(_corta(dados, CORTE), PARAMS), original)


def test_desvio_usa_so_pregoes_anteriores_a_t() -> None:
    dados = _dados()
    antes = montar_matrizes(dados.bars, PARAMS)
    mexido = dados.bars.copy()
    no_dia = (mexido["ticker"] == "DDDD") & (mexido["trade_date"] == CALENDARIO[70])
    mexido.loc[no_dia, "close"] *= 3.0
    depois = montar_matrizes(mexido, PARAMS)
    j = list(antes.tickers).index("DDDD")
    assert depois.sigma[70, j] == antes.sigma[70, j]
    assert depois.sigma[71, j] != antes.sigma[71, j]


def test_controle_tem_z_baixo_e_sorteio_reproduzivel() -> None:
    dados = _dados()
    p = replace(PARAMS, n_controle=25)
    um, dois = amostrar_controle(dados, p), amostrar_controle(dados, p)
    pd.testing.assert_frame_equal(um, dois)
    assert len(um) == 25
    assert (um["z_log"] < p.limiar_controle).all()
    outro = amostrar_controle(dados, replace(p, semente=p.semente + 1))
    assert not um.equals(outro)


def test_versoes_contagens_e_resumo() -> None:
    dados = _dados()
    por_versao = versoes(_corta(dados, CORTE), dados, PARAMS)
    cont = contagens(por_versao, PARAMS.horizontes)
    eventos = cont[cont["grupo"] == "evento"].set_index("versao").drop(columns="grupo")
    por_versao_n = {v: [int(x) for x in linha] for v, linha in eventos.iterrows()}
    assert por_versao_n == {
        "a_corte": [3, 3, 3, 2, 0],  # AAAA t+30 e CCCC t+20 passam do corte
        "b_sem_corte": [3, 3, 3, 3, 1],  # so AAAA tem 30 pregoes a frente
        "c_corte_sem_mkt_alto": [2, 2, 2, 2, 0],  # sai CCCC
        "d_corte_so_mkt_alto": [1, 1, 1, 0, 0],  # so CCCC
    }

    resumo = resumir(por_versao["a_corte"], PARAMS.horizontes)
    linha = resumo[(resumo["N"] == 1) & (resumo["metrica"] == "var_abs")].iloc[0]
    # Tres eventos em N=1: 0.01, 1/51 e 0.05 -> mediana 1/51.
    assert linha["mediana_evento"] == pytest.approx(1 / 51)
    assert linha["razao_mediana"] == pytest.approx(1 / 51 / linha["mediana_controle"])


# ------------------------------------------------------------ banco


@pytest.mark.db
def test_carregar_nao_le_nada_depois_do_corte(engine: Engine) -> None:
    tickers = ("ZZBT3", "ZZBT4")
    dias = pd.bdate_range("2026-09-28", periods=6)  # 28/09 a 05/10
    corte = date(2026, 10, 2)
    with engine.begin() as conn:
        for ticker in tickers:
            for dia in dias:
                conn.execute(
                    text(
                        "INSERT INTO volume_scanner.daily_bars "
                        "(ticker, trade_date, close, high, low, volume_financial) "
                        "VALUES (:t, :d, 10, 11, 9, 1000000)"
                    ),
                    {"t": ticker, "d": dia.date()},
                )
                conn.execute(
                    text(
                        "INSERT INTO volume_scanner.volume_metrics "
                        "(ticker, trade_date, window_size, z_log) VALUES (:t, :d, 30, 1.0)"
                    ),
                    {"t": ticker, "d": dia.date()},
                )
    try:
        dados = carregar(engine, 30, corte)
        nossos = dados.bars[dados.bars["ticker"].isin(tickers)]
        assert nossos["trade_date"].max() == pd.Timestamp(corte)
        assert len(nossos) == 2 * 5
        assert dados.z["trade_date"].max() <= pd.Timestamp(corte)
        tudo = carregar(engine, 30, None)
        assert len(tudo.bars[tudo.bars["ticker"].isin(tickers)]) == 2 * 6
    finally:
        with engine.begin() as conn:
            for tabela in ("daily_bars", "volume_metrics"):
                conn.execute(
                    text(f"DELETE FROM volume_scanner.{tabela} WHERE ticker = ANY(:t)"),
                    {"t": list(tickers)},
                )
