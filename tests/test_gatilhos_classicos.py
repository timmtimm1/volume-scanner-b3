"""Setups classicos de compra (scanner.gatilhos.classicos).

Cada teste monta uma serie de um papel com o padrao no ultimo pregao e confere
que o setup arma ali (e nao na vespera), com gatilho na maxima + 1 centavo e o
stop do padrao.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scanner.gatilhos.classicos import CENTAVO, Sinal, classicos, tendencia_de_alta
from scanner.gatilhos.contexto import atr_wilder
from scanner.gatilhos.matrizes import montar
from scanner.gatilhos.medias import media_movel
from scanner.gatilhos.niveis import Regras, detectar
from tests.gatilhos_sinteticos import serra

Barra = tuple[float, float, float, float]


def _barras_de(fech: list[float], folga: float = 0.05) -> list[Barra]:
    """Abertura no fechamento anterior, sombras de `folga` alem do corpo."""
    out: list[Barra] = []
    for i, c in enumerate(fech):
        o = fech[i - 1] if i else c
        out.append((o, max(o, c) + folga, min(o, c) - folga, c))
    return out


def _sinais(barras: list[Barra]) -> dict[str, Sinal]:
    a = np.array(barras, dtype=np.float64)
    o, h, low, c = (a[:, i : i + 1].copy() for i in range(4))
    tick = np.full_like(c, CENTAVO)
    atr = atr_wilder(h, low, c)
    retrato, eventos = detectar(h, low, c, atr, Regras(toques_min=2))
    return classicos(o, h, low, c, tick, retrato, eventos)


def _so_no_ultimo(s: Sinal, nome: str) -> None:
    assert s.armado[-1, 0], f"{nome} deveria armar no ultimo pregao"
    assert not s.armado[-2, 0], f"{nome} nao deveria armar na vespera"


def test_91_mme_vira_para_cima() -> None:
    fech = list(np.linspace(20, 15, 40))
    fech.append(fech[-1] + 0.8)  # fecha bem acima: a MME 9 vira
    barras = _barras_de(fech)
    s = _sinais(barras)["9.1"]
    _so_no_ultimo(s, "9.1")
    assert s.gatilho[-1, 0] == pytest.approx(barras[-1][1] + 0.01)
    assert s.stop[-1, 0] == pytest.approx(barras[-1][2] - 0.01)


def test_91_nao_arma_com_a_media_ja_subindo() -> None:
    fech = list(np.linspace(10, 15, 40))
    s = _sinais(_barras_de(fech))["9.1"]
    assert not s.armado[20:, 0].any()


def test_92_fecha_abaixo_da_minima_anterior_com_a_media_subindo() -> None:
    fech = list(10 + 0.5 * np.arange(40))
    fech.append(fech[-1] - 0.7)  # abaixo da minima anterior (abertura dela - 0,05), acima da MME
    s = _sinais(_barras_de(fech))
    _so_no_ultimo(s["9.2"], "9.2")
    mme = media_movel(np.array(fech)[:, None], "MME", 9)[:, 0]
    assert mme[-1] > mme[-2]


def test_93_dois_fechamentos_abaixo_da_referencia() -> None:
    fech = list(10 + 0.5 * np.arange(40))
    ref = fech[-1]
    fech += [ref - 0.1, ref - 0.05]  # os dois abaixo da referencia, a MME ainda sobe
    s = _sinais(_barras_de(fech))["9.3"]
    _so_no_ultimo(s, "9.3")


def test_94_venda_desfeita_sem_perder_a_minima() -> None:
    fech = list(10 + 0.2 * np.arange(40))
    topo = fech[-1]
    fech.append(topo - 1.4)  # vira a MME para baixo (9.1 de venda)
    barras = _barras_de(fech)
    # volta forte, sem perder a minima do candle de baixa
    o = fech[-1]
    c = topo + 0.6
    barras.append((o, c + 0.05, barras[-1][2] + 0.02, c))
    s = _sinais(barras)["9.4"]
    _so_no_ultimo(s, "9.4")
    assert s.stop[-1, 0] == pytest.approx(barras[-2][2] - 0.01)


def test_123_minima_do_meio_e_a_menor() -> None:
    barras = _barras_de(list(np.full(30, 10.0)))
    barras += [(10.0, 10.2, 9.7, 9.9), (9.9, 10.0, 9.5, 9.8), (9.8, 10.3, 9.6, 10.2)]
    s = _sinais(barras)["123"]
    _so_no_ultimo(s, "123")
    assert s.stop[-1, 0] == pytest.approx(9.5 - 0.01)
    assert s.gatilho[-1, 0] == pytest.approx(10.3 + 0.01)


def test_123_empate_na_minima_nao_vale() -> None:
    barras = _barras_de(list(np.full(30, 10.0)))
    barras += [(10.0, 10.2, 9.5, 9.9), (9.9, 10.0, 9.5, 9.8), (9.8, 10.3, 9.6, 10.2)]
    assert not _sinais(barras)["123"].armado[-1, 0]


def test_pfr_nova_minima_e_fecha_acima_do_anterior() -> None:
    barras = _barras_de(list(np.full(30, 10.0)))
    barras += [(10.0, 10.1, 9.8, 9.9), (9.9, 10.0, 9.7, 9.8), (9.8, 10.1, 9.5, 9.95)]
    s = _sinais(barras)["pfr"]
    _so_no_ultimo(s, "pfr")
    assert s.stop[-1, 0] == pytest.approx(9.5 - 0.01)


def test_pfr_fechando_abaixo_do_anterior_nao_vale() -> None:
    barras = _barras_de(list(np.full(30, 10.0)))
    barras += [(10.0, 10.1, 9.8, 9.9), (9.9, 10.0, 9.7, 9.8), (9.8, 10.1, 9.5, 9.75)]
    assert not _sinais(barras)["pfr"].armado[-1, 0]


def _alta_longa(dias: int = 260) -> list[float]:
    return list(10 * 1.003 ** np.arange(dias))


def test_mma20_toque_simples_em_alta() -> None:
    fech = _alta_longa()
    barras = _barras_de(fech, folga=0.01)
    mm20 = (sum(fech[-19:]) + fech[-1]) / 20
    c = fech[-1]
    barras.append((c, c + 0.05, mm20 * 1.005, c))  # pavio ate 0,5% da MMA 20
    s = _sinais(barras)["mma20"]
    _so_no_ultimo(s, "mma20")


def test_mma20_longe_da_media_nao_vale() -> None:
    fech = _alta_longa()
    barras = _barras_de(fech, folga=0.01)
    mm20 = (sum(fech[-19:]) + fech[-1]) / 20
    c = fech[-1]
    barras.append((c, c + 0.05, mm20 * 1.02, c))
    assert not _sinais(barras)["mma20"].armado[-1, 0]


def test_mma20_abaixo_da_mma200_nao_vale() -> None:
    # caiu muito e voltou a subir: MMA 20 subindo, mas abaixo da MMA 200
    fech = list(np.linspace(30, 10, 230)) + list(10 * 1.004 ** np.arange(1, 31))
    barras = _barras_de(fech, folga=0.01)
    mm20 = (sum(fech[-19:]) + fech[-1]) / 20
    c = fech[-1]
    barras.append((c, c + 0.05, mm20 * 1.005, c))
    assert not _sinais(barras)["mma20"].armado[-1, 0]


def _rompimento_e_volta(volta_minima: float, volta_fech: float, espera: int) -> list[Barra]:
    """Serra entre 10 e 12 (resistencia em ~12,05), rompe para 13,4 e volta ao nivel."""
    barras = _barras_de(serra(10.0, 12.0, 200))
    # rompe: fechamentos bem acima da resistencia
    for c in (12.6, 12.9, 13.2, 13.4):
        o = barras[-1][3]
        barras.append((o, max(o, c) + 0.05, min(o, c) - 0.05, c))
    for _ in range(espera):
        barras.append((13.3, 13.5, 13.1, 13.3))
    barras.append((13.3, 13.35, 12.7, 12.8))
    barras.append((12.8, 12.9, volta_minima, volta_fech))
    return barras


def test_pullback_volta_ao_nivel_rompido() -> None:
    s = _sinais(_rompimento_e_volta(12.1, 12.4, espera=3))["pullback"]
    _so_no_ultimo(s, "pullback")


def test_pullback_tarde_demais_nao_vale() -> None:
    s = _sinais(_rompimento_e_volta(12.1, 12.4, espera=25))["pullback"]
    assert not s.armado[-1, 0]


def test_pullback_fechando_abaixo_do_nivel_nao_vale() -> None:
    s = _sinais(_rompimento_e_volta(11.4, 11.5, espera=3))["pullback"]
    assert not s.armado[-1, 0]


def test_tendencia_de_alta() -> None:
    sobe = np.array(_alta_longa())[:, None]
    desce = sobe[::-1].copy()
    assert tendencia_de_alta(sobe)[-1, 0]
    assert not tendencia_de_alta(desce)[-1, 0]
    assert not tendencia_de_alta(sobe)[150, 0]  # antes de ter 200 pregoes nao ha MMA 200


def test_stop_sempre_abaixo_da_minima() -> None:
    rng = np.random.default_rng(3)
    fech = list(20 * np.exp(np.cumsum(rng.normal(0, 0.02, 400))))
    for nome, s in _sinais(_barras_de(fech)).items():
        a = np.array(_barras_de(fech))
        dd = np.nonzero(s.armado[:, 0])[0]
        assert (s.stop[dd, 0] < a[dd, 2]).all(), nome
        assert (s.gatilho[dd, 0] > a[dd, 1]).all(), nome


def test_nada_olha_o_futuro() -> None:
    rng = np.random.default_rng(11)
    fech = list(20 * np.exp(np.cumsum(rng.normal(0, 0.02, 400))))
    cheio = _sinais(_barras_de(fech))
    cortado = _sinais(_barras_de(fech[:300]))
    for nome in cheio:
        assert (cheio[nome].armado[:300] == cortado[nome].armado).all(), nome


def test_papeis_independentes() -> None:
    rng = np.random.default_rng(2)
    fechs = [list(20 * np.exp(np.cumsum(rng.normal(0, 0.02, 300)))) for _ in range(2)]
    linhas = []
    for t, f in zip(("AAAA3", "BBBB3"), fechs, strict=True):
        for d, (o, h, low, c) in zip(
            pd.bdate_range("2020-01-01", periods=300), _barras_de(f), strict=True
        ):
            linhas.append(
                {
                    "ticker": t,
                    "trade_date": d,
                    "open": o,
                    "high": h,
                    "low": low,
                    "close": c,
                    "volume_financial": 1e6,
                }
            )
    m = montar(pd.DataFrame(linhas))
    atr = atr_wilder(m.maxima, m.minima, m.fechamento)
    ret, ev = detectar(m.maxima, m.minima, m.fechamento, atr, Regras(toques_min=2))
    juntos = classicos(
        m.abertura, m.maxima, m.minima, m.fechamento, np.full_like(m.fechamento, CENTAVO), ret, ev
    )
    sozinho = _sinais(_barras_de(fechs[1]))
    for nome in juntos:
        assert (juntos[nome].armado[:, 1] == sozinho[nome].armado[:, 0]).all(), nome
