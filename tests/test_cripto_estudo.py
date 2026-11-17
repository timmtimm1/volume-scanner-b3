"""Os dois setups do estudo de cripto: as regras e o trade de cada sinal."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scanner.cripto import estudo
from scanner.cripto.estudo import SETUPS, acompanhar, sinal_compressao_venda, sinal_rsi_reversao

RSI = SETUPS["rsi_reversao"]
VENDA = SETUPS["compressao_venda"]


def candles(linhas: list[tuple[float, float, float, float]], fechado: bool = True) -> pd.DataFrame:
    idx = pd.date_range("2026-11-01", periods=len(linhas), freq="D", tz="UTC")
    df = pd.DataFrame(linhas, columns=["Open", "High", "Low", "Close"], index=idx)
    df["fechado"] = fechado
    return df


# --- O trade ----------------------------------------------------------------
# Sinal de compra: fechou em 100, stop em 90 (risco 10), alvo 3R = 130.


def test_compra_que_bate_o_alvo() -> None:
    t = acompanhar(RSI, 100, 90, candles([(100, 105, 98, 104), (104, 131, 103, 128)]))
    assert t.estado == "alvo"
    assert t.entrada == pytest.approx(100 * 1.0005)
    assert t.saida == 130  # o alvo, sem derrapagem
    # entrada 100,05 (derrapagem), risco 10,05; menos a taxa dos dois lados
    assert t.resultado_r == pytest.approx((130 - 100.05) / 10.05 - 0.001 * 230.05 / 10.05)


def test_compra_que_bate_o_stop_com_derrapagem() -> None:
    t = acompanhar(RSI, 100, 90, candles([(100, 102, 89, 91)]))
    assert t.estado == "stop"
    assert t.saida == pytest.approx(90 * 0.9995)
    assert t.resultado_r == pytest.approx(-1.04, abs=0.02)


def test_stop_e_alvo_no_mesmo_candle_conta_o_stop() -> None:
    assert acompanhar(RSI, 100, 90, candles([(100, 140, 85, 120)])).estado == "stop"


def test_gap_abaixo_do_stop_sai_na_abertura() -> None:
    t = acompanhar(RSI, 100, 90, candles([(100, 101, 99, 100), (80, 85, 78, 82)]))
    assert t.estado == "stop"
    assert t.saida == pytest.approx(80 * 0.9995)
    assert t.resultado_r < -1.9


def test_prazo_sai_na_abertura_depois_do_ultimo_candle() -> None:
    lento = [
        (100 + i * 0.1, 101 + i * 0.1, 99 + i * 0.1, 100 + i * 0.1) for i in range(RSI.prazo + 2)
    ]
    t = acompanhar(RSI, 100, 90, candles(lento))
    assert t.estado == "prazo"
    assert t.saida_em == candles(lento).index[RSI.prazo + 1]
    assert t.saida == pytest.approx(lento[RSI.prazo + 1][0] * 0.9995)


def test_aberto_marca_o_resultado_no_ultimo_preco() -> None:
    dados = candles([(100, 103, 99, 102)])
    dados.loc[dados.index[-1], "fechado"] = False  # o candle de hoje, em andamento
    t = acompanhar(RSI, 100, 90, dados)
    assert t.estado == "aberto"
    assert t.saida is None
    assert t.resultado_r == pytest.approx((102 - 100.05) / 10.05 - 0.001 * 202.05 / 10.05)


def test_sem_candle_depois_do_sinal_esta_aguardando() -> None:
    assert acompanhar(RSI, 100, 90, candles([])[:0]).estado == "aguardando"


# Venda: fechou em 100, stop em 110 (risco 10), alvo 3R = 70.


def test_venda_espelhada_alvo_e_stop() -> None:
    alvo = acompanhar(VENDA, 100, 110, candles([(100, 101, 69, 72)]))
    assert alvo.estado == "alvo"
    assert alvo.entrada == pytest.approx(100 * 0.9995)  # vende na abertura, derrapagem contra
    assert alvo.saida == 70
    assert alvo.resultado_r == pytest.approx((99.95 - 70) / 10.05 - 0.001 * 169.95 / 10.05)
    stop = acompanhar(VENDA, 100, 110, candles([(100, 111, 99, 108)]))
    assert stop.estado == "stop"
    assert stop.saida == pytest.approx(110 * 1.0005)
    assert stop.resultado_r == pytest.approx(-1.04, abs=0.02)


# --- As regras --------------------------------------------------------------


def _serie(fech: np.ndarray, vol: float = 5e6) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(fech), freq="D")
    return pd.DataFrame(
        {"Open": fech, "High": fech * 1.01, "Low": fech * 0.99, "Close": fech, "VolUSD": vol},
        index=idx,
    )


def test_rsi_dispara_na_volta_depois_de_esticar_para_baixo() -> None:
    fech = np.concatenate([np.full(60, 100.0), 100 * 0.95 ** np.arange(1, 9), [70, 74, 78]])
    s = sinal_rsi_reversao(_serie(fech))
    assert s.notna().sum() >= 1
    primeiro = s.first_valid_index()
    assert primeiro is not None
    i = list(s.index).index(primeiro)
    assert fech[i] > fech[i - 1]  # o candle do sinal fechou em alta
    assert s[primeiro] == pytest.approx(_serie(fech)["Low"].iloc[i - 5 : i + 1].min())


def test_rsi_nao_dispara_sem_liquidez() -> None:
    fech = np.concatenate([np.full(60, 100.0), 100 * 0.95 ** np.arange(1, 9), [70, 74, 78]])
    assert sinal_rsi_reversao(_serie(fech, vol=1e5)).notna().sum() == 0


def test_compressao_dispara_na_venda_depois_de_bandas_apertadas() -> None:
    rng = np.random.default_rng(3)
    largo = 100 + rng.normal(0, 3, 200)  # bandas largas
    apertado = 100 + rng.normal(0, 0.05, 30)  # comprime
    queda = [97.0]  # fecha abaixo da banda de baixo
    fech = np.concatenate([largo, apertado, queda])
    df = _serie(fech, vol=5e6 / 6)
    df.index = pd.date_range("2025-01-01", periods=len(fech), freq="4h")
    s = sinal_compressao_venda(df)
    assert pd.notna(s.iloc[-1])
    assert s.iloc[-1] > fech[-1]  # o stop (a media) fica acima do preco
    # a mesma serie sem a queda nao dispara no ultimo candle
    sem_queda = df.iloc[:-1].copy()
    assert pd.isna(sinal_compressao_venda(sem_queda).iloc[-1])


def test_rank_na_janela_igual_ao_rank_do_pandas() -> None:
    x = np.random.default_rng(1).normal(size=300)
    x[50] = np.nan
    esperado = pd.Series(x).rolling(120, min_periods=60).rank(pct=True).to_numpy()
    obtido = estudo._rank_na_janela(x, 120, 60)
    assert np.allclose(obtido, esperado, equal_nan=True)
