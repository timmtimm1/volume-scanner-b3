"""O trade da suite de backtest (scanner.backtest.simulador).

Cada teste monta um papel de poucos pregoes, a mao, e confere entrada, saida,
motivo e R. Precos redondos para a conta caber de cabeca.
"""

from __future__ import annotations

import numpy as np
import pytest

from scanner.backtest.simulador import (
    ABERTO,
    ALVO,
    MEDIA,
    MOVEL,
    PRAZO,
    STOP,
    TETO,
    Precos,
    Saida,
    entrar,
    simular,
)

ALVO2 = Saida("alvo2", alvo_r=2.0)
MINIMAS = Saida("minimas", movel="minimas")
MME9 = Saida("mme9", movel="mme9")


def _precos(barras: list[tuple[float, float, float, float]], tick: float = 0.0) -> Precos:
    """Um papel so: lista de (abertura, maxima, minima, fechamento) por pregao."""
    a = np.array(barras, dtype=np.float64)
    col = [a[:, i : i + 1].copy() for i in range(4)]
    return Precos.de(*col, tick=np.full_like(col[0], tick))


def _um(p: Precos, dia_entrada: int, entrada: float, stop: float, saida: Saida, **kw: object):
    return simular(
        p,
        np.array([dia_entrada]),
        np.array([0]),
        np.array([entrada]),
        np.array([stop]),
        saida,
        **kw,  # type: ignore[arg-type]
    )


PLANO = (10.0, 10.2, 9.8, 10.0)


def test_sem_passar_do_gatilho_nao_ha_trade() -> None:
    p = _precos([PLANO, (10.0, 10.4, 9.9, 10.3)])
    e = entrar(p, np.array([0]), np.array([0]), np.array([10.5]))
    assert not e.entrou[0]
    assert np.isnan(e.preco[0])


def test_entra_no_gatilho_ou_na_abertura_se_abriu_acima() -> None:
    p = _precos([PLANO, (10.1, 10.6, 10.0, 10.5), (10.8, 11.0, 10.7, 10.9)])
    no_gatilho = entrar(p, np.array([0]), np.array([0]), np.array([10.3]))
    assert no_gatilho.entrou[0] and no_gatilho.preco[0] == pytest.approx(10.3)
    assert no_gatilho.dia[0] == 1
    com_gap = entrar(p, np.array([1]), np.array([0]), np.array([10.61]))
    assert com_gap.preco[0] == pytest.approx(10.8)


def test_ultimo_dia_dos_dados_nao_entra() -> None:
    p = _precos([PLANO, PLANO])
    e = entrar(p, np.array([1]), np.array([0]), np.array([10.0]))
    assert not e.entrou[0]


def test_alvo_de_2r() -> None:
    # entrada 10, stop 9 (R = 1), alvo 12
    p = _precos(
        [PLANO, (10.0, 10.5, 9.5, 10.4), (10.4, 11.0, 10.2, 10.9), (11.0, 12.3, 10.9, 12.1)]
    )
    r = _um(p, 1, 10.0, 9.0, ALVO2)
    assert r.motivo[0] == ALVO
    assert r.dia_saida[0] == 3
    assert r.preco_saida[0] == pytest.approx(12.0)
    assert r.r[0] == pytest.approx(2.0)


def test_abertura_acima_do_alvo_sai_na_abertura() -> None:
    p = _precos([PLANO, (10.0, 10.5, 9.5, 10.4), (12.5, 12.8, 12.4, 12.6)])
    r = _um(p, 1, 10.0, 9.0, ALVO2)
    assert r.motivo[0] == ALVO
    assert r.r[0] == pytest.approx(2.5)


def test_stop_no_dia_da_entrada_conta_mesmo_sem_saber_a_ordem() -> None:
    # passou do gatilho e furou o stop no mesmo dia: conservador, e stop
    p = _precos([PLANO, (9.5, 10.3, 8.9, 10.2)])
    r = _um(p, 1, 10.0, 9.0, ALVO2)
    assert r.motivo[0] == STOP
    assert r.r[0] == pytest.approx(-1.0)


def test_stop_e_alvo_no_mesmo_dia_conta_o_stop() -> None:
    p = _precos([PLANO, (10.0, 10.5, 9.5, 10.4), (10.4, 12.5, 8.8, 11.0)])
    r = _um(p, 1, 10.0, 9.0, ALVO2)
    assert r.motivo[0] == STOP
    assert r.dia_saida[0] == 2


def test_gap_abaixo_do_stop_sai_na_abertura() -> None:
    p = _precos([PLANO, (10.0, 10.5, 9.5, 10.4), (8.5, 8.7, 8.2, 8.4)])
    r = _um(p, 1, 10.0, 9.0, ALVO2)
    assert r.motivo[0] == STOP
    assert r.preco_saida[0] == pytest.approx(8.5)
    assert r.r[0] == pytest.approx(-1.5)


def test_custo_e_cobrado_na_compra_e_na_venda() -> None:
    p = _precos([PLANO, (10.0, 10.5, 9.5, 10.4), (10.4, 12.3, 10.2, 12.1)])
    r = _um(p, 1, 10.0, 9.0, ALVO2, custo=0.001)
    assert r.r_bruto[0] == pytest.approx(2.0)
    assert r.r[0] == pytest.approx((12.0 * 0.999 - 10.0 * 1.001) / 1.0)


def test_stop_movel_sobe_com_as_minimas_e_nunca_desce() -> None:
    p = _precos(
        [
            (10.0, 10.2, 9.6, 10.0),  # sinal (minima 9,6)
            (10.0, 10.6, 9.9, 10.5),  # entrada a 10
            (10.5, 11.0, 10.4, 10.9),  # stop vira min(9,6; 9,9) = 9,6 -> fica 9,6
            (10.9, 11.4, 10.8, 11.3),  # stop vira min(9,9; 10,4) = 9,9
            (11.3, 11.5, 10.6, 10.7),  # stop vira min(10,4; 10,8) = 10,4: minima 10,6 nao toca
            (10.7, 10.8, 10.3, 10.4),  # stop vira min(10,8; 10,6) = 10,6: minima 10,3 toca
        ]
    )
    r = _um(p, 1, 10.0, 9.5, MINIMAS, dia_anterior_minima=np.array([9.6]))
    assert r.motivo[0] == MOVEL
    assert r.dia_saida[0] == 5
    assert r.preco_saida[0] == pytest.approx(10.6)
    assert r.r[0] == pytest.approx(0.6 / 0.5)


def test_stop_movel_que_nao_subiu_e_stop_inicial() -> None:
    p = _precos([(10.0, 10.2, 9.0, 10.0), (10.0, 10.6, 9.4, 10.5), (10.5, 10.6, 8.5, 8.7)])
    r = _um(p, 1, 10.0, 9.2, MINIMAS, dia_anterior_minima=np.array([9.0]))
    assert r.motivo[0] == STOP


def _mme_vira(n_sobe: int) -> list[tuple[float, float, float, float]]:
    """Alta de n_sobe pregoes e depois um fechamento bem mais baixo (vira a MME 9)."""
    barras = [(10 + 0.1 * i, 10.2 + 0.1 * i, 9.9 + 0.1 * i, 10.1 + 0.1 * i) for i in range(n_sobe)]
    ult = barras[-1][3]
    barras.append((ult, ult + 0.05, ult - 1.0, ult - 0.95))  # fecha 0,95 abaixo: a MME vira
    barras.append((ult - 0.9, ult - 0.8, ult - 1.1, ult - 1.0))
    return barras


def test_saida_pela_mme9_na_abertura_seguinte() -> None:
    barras = _mme_vira(30)
    p = _precos(barras)
    entrada_dia = 20
    entrada = barras[entrada_dia][0]
    r = _um(p, entrada_dia, entrada, entrada - 2.0, MME9)
    assert r.motivo[0] == MEDIA
    assert r.dia_saida[0] == 31  # o fechamento do dia 30 virou a media
    assert r.preco_saida[0] == pytest.approx(barras[31][0])


def test_alvo_nao_vale_na_saida_pela_mme9() -> None:
    p = _precos(
        [PLANO, (10.0, 10.5, 9.5, 10.4)]
        + [(11.0 + i, 20.0 + i, 10.9 + i, 19.0 + i) for i in range(5)]
    )
    r = _um(p, 1, 10.0, 9.0, MME9)
    assert r.motivo[0] == ABERTO  # sem alvo: subiu sem a media virar ate o fim dos dados


def test_teto_sai_no_fechamento() -> None:
    barras = [PLANO] + [(10.0, 10.1, 9.95, 10.0)] * (TETO + 5)
    p = _precos(barras)
    r = _um(p, 1, 10.0, 9.0, ALVO2)
    assert r.motivo[0] == PRAZO
    assert r.dia_saida[0] == 1 + TETO
    assert r.r[0] == pytest.approx(0.0)


def test_dia_sem_negocio_nao_mexe_no_trade() -> None:
    sem = (np.nan, np.nan, np.nan, np.nan)
    p = _precos([PLANO, (10.0, 10.5, 9.5, 10.4), sem, (10.4, 12.3, 10.2, 12.1)])
    r = _um(p, 1, 10.0, 9.0, ALVO2)
    assert r.motivo[0] == ALVO
    assert r.dia_saida[0] == 3


def test_fim_dos_dados_fica_aberto() -> None:
    p = _precos([PLANO, (10.0, 10.5, 9.5, 10.4), (10.4, 10.9, 10.2, 10.8)])
    r = _um(p, 1, 10.0, 9.0, ALVO2)
    assert r.motivo[0] == ABERTO
    assert r.dia_saida[0] == -1
    assert np.isnan(r.r[0])


def test_varios_trades_juntos_sao_independentes() -> None:
    a = np.array([[10.0, 20.0], [10.0, 20.0], [12.5, 17.0]])
    h = np.array([[10.2, 20.2], [10.5, 20.5], [12.8, 17.2]])
    low = np.array([[9.8, 19.8], [9.5, 19.5], [12.4, 16.5]])
    c = np.array([[10.0, 20.0], [10.4, 20.4], [12.6, 16.8]])
    p = Precos.de(a, h, low, c, tick=np.zeros_like(a))
    r = simular(
        p, np.array([1, 1]), np.array([0, 1]), np.array([10.0, 20.0]), np.array([9.0, 19.0]), ALVO2
    )
    assert list(r.motivo) == [ALVO, STOP]


def test_nada_olha_o_futuro() -> None:
    # mudar o que vem depois da saida nao muda o trade
    base = [PLANO, (10.0, 10.5, 9.5, 10.4), (10.4, 12.3, 10.2, 12.1)]
    r1 = _um(_precos(base + [(12.0, 12.1, 11.9, 12.0)] * 3), 1, 10.0, 9.0, ALVO2)
    r2 = _um(_precos(base + [(5.0, 30.0, 1.0, 2.0)] * 3), 1, 10.0, 9.0, ALVO2)
    assert r1.dia_saida[0] == r2.dia_saida[0] == 2
    assert r1.r[0] == r2.r[0]
