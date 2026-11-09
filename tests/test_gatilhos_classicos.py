"""Setups classicos de compra (scanner.gatilhos.classicos).

Cada teste monta uma serie de um papel com o padrao no ultimo pregao e confere
que o setup arma ali (e nao na vespera), com gatilho na maxima + 1 centavo e o
stop do padrao.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

from scanner.gatilhos.classicos import (
    CENTAVO,
    RegrasClassicas,
    Sinal,
    classicos,
    tendencia_de_alta,
    topos_e_fundos_ascendentes,
)
from scanner.gatilhos.contexto import atr_wilder, calcular
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


def _sinais(
    barras: list[Barra],
    volume: list[float] | None = None,
    regras: RegrasClassicas | None = None,
) -> dict[str, Sinal]:
    """Os classicos de um papel. Volume constante, salvo o pedido."""
    a = np.array(barras, dtype=np.float64)
    o, h, low, c = (a[:, i : i + 1].copy() for i in range(4))
    v = np.array(volume if volume is not None else [1e6] * len(barras), dtype=np.float64)[:, None]
    tick = np.full_like(c, CENTAVO)
    atr = atr_wilder(h, low, c)
    retrato, eventos = detectar(h, low, c, atr, Regras(toques_min=2))
    rvol = np.asarray(calcular(h, c, v)["rvol"], dtype=np.float64)
    return classicos(o, h, low, c, tick, retrato, eventos, rvol, atr, regras)


def _so_no_ultimo(s: Sinal, nome: str) -> None:
    assert s.armado[-1, 0], f"{nome} deveria armar no ultimo pregao"
    assert not s.armado[-2, 0], f"{nome} nao deveria armar na vespera"


def _serra_subindo(ciclos: int = 18, inicio: float = 10.0) -> list[float]:
    """Alta em serra: 6 pregoes subindo 0,30, 4 caindo 0,25. Topos e fundos
    ascendentes e a media de 80 subindo -- o ambiente em que os 9.x valem
    (06/11/2026). Termina num recuo de 4 pregoes."""
    f = [inicio]
    for _ in range(ciclos):
        f += [f[-1] + 0.30 * (i + 1) for i in range(6)]
        f += [f[-1] - 0.25 * (i + 1) for i in range(4)]
    return f


def _alta_terminando_em_alta() -> list[float]:
    """A mesma serra, terminando numa perna de alta (MME 9 subindo)."""
    base = _serra_subindo()
    return base + [base[-1] + 0.3 * (i + 1) for i in range(6)]


def _91_no_suporte(alta: float = 1.2) -> list[Barra]:
    """Serra entre 10 e 12 (suporte de muitos toques em ~10) terminando no fundo,
    e um candle que sai do suporte e vira a MME 9 para cima."""
    fech = serra(10.0, 12.0, 256)
    fundo = max(k for k, x in enumerate(fech) if abs(x - 10.0) < 1e-9)
    barras = _barras_de(fech[: fundo + 1])
    f = fech[fundo]
    barras.append((f, f + alta + 0.05, f - 0.03, f + alta))
    return barras


def test_91_no_suporte_com_volume() -> None:
    """Pedido de 06/11/2026: o 9.1 so vale com a minima num suporte de 3+ toques
    e volume de 1,5x a mediana ou mais."""
    barras = _91_no_suporte()
    volume = [1e6] * (len(barras) - 1) + [2e6]
    s = _sinais(barras, volume)["9.1"]
    _so_no_ultimo(s, "9.1")
    assert s.gatilho[-1, 0] == pytest.approx(barras[-1][1] + 0.01)
    assert s.stop[-1, 0] == pytest.approx(barras[-1][2] - 0.01)


def test_91_no_suporte_sem_volume_nao_arma() -> None:
    assert not _sinais(_91_no_suporte())["9.1"].armado[-1, 0]


def test_91_em_alta_fora_do_suporte_nao_arma() -> None:
    fech = _serra_subindo()
    fech.append(fech[-1] + 1.0)  # a MME 9 vira, mas longe de suporte
    barras = _barras_de(fech)
    volume = [1e6] * (len(barras) - 1) + [3e6]
    assert not _sinais(barras, volume)["9.1"].armado[-1, 0]


def test_91_nao_arma_com_a_media_ja_subindo() -> None:
    fech = list(np.linspace(10, 15, 40))
    s = _sinais(_barras_de(fech))["9.1"]
    assert not s.armado[20:, 0].any()


def _com_a_minima_na_media(fech: list[float]) -> list[Barra]:
    """As barras de `fech`, com a sombra do ultimo candle descendo ate a MME 9."""
    barras = _barras_de(fech)
    mme = float(media_movel(np.array(fech)[:, None], "MME", 9)[-1, 0])
    o, h, low, c = barras[-1]
    barras[-1] = (o, h, min(low, mme), c)
    return barras


def _recuo_do_92() -> list[float]:
    fech = _alta_terminando_em_alta()
    return [*fech, fech[-1] - 0.5]  # abaixo da minima anterior, a MME 9 ainda sobe


def _recuo_do_93() -> list[float]:
    fech = _alta_terminando_em_alta()
    ref = fech[-1]
    return [*fech, ref - 0.1, ref - 0.05]  # os dois abaixo da referencia


def test_92_fecha_abaixo_da_minima_anterior_com_a_media_subindo() -> None:
    fech = _recuo_do_92()
    s = _sinais(_com_a_minima_na_media(fech))
    _so_no_ultimo(s["9.2"], "9.2")
    mme = media_movel(np.array(fech)[:, None], "MME", 9)[:, 0]
    assert mme[-1] > mme[-2]


def test_93_dois_fechamentos_abaixo_da_referencia() -> None:
    s = _sinais(_com_a_minima_na_media(_recuo_do_93()))["9.3"]
    _so_no_ultimo(s, "9.3")


@pytest.mark.parametrize(("nome", "recuo"), [("9.2", _recuo_do_92), ("9.3", _recuo_do_93)])
def test_9x_longe_da_media_nao_arma(nome: str, recuo: Callable[[], list[float]]) -> None:
    """Pedido de 09/11/2026: 9.2 a 9.4 acompanham a MME 9. Com a minima do candle
    do sinal a mais de 0,3 ATR acima da media, nao e o setup -- era o erro mais
    comum da lista (o usuario recusou 21 de 22 casos assim na conferencia)."""
    barras = _barras_de(recuo())
    a = np.array(barras, dtype=np.float64)
    mme = media_movel(a[:, 3:4].copy(), "MME", 9)[-1, 0]
    atr = atr_wilder(a[:, 1:2].copy(), a[:, 2:3].copy(), a[:, 3:4].copy())[-1, 0]
    assert barras[-1][2] > mme + 0.3 * atr  # o candle esta mesmo longe
    assert not _sinais(barras)[nome].armado[-1, 0]
    # sem a regra, o mesmo candle armava
    assert _sinais(barras, regras=RegrasClassicas(perto_9x=None))[nome].armado[-1, 0]


def test_9x_perto_da_media_vale_ate_o_limite() -> None:
    """A minima a 0,2 ATR da MME 9 vale; a 0,4 ATR, nao."""
    fech = _recuo_do_92()
    for folga, esperado in ((0.2, True), (0.4, False)):
        barras = _barras_de(fech)
        a = np.array(barras, dtype=np.float64)
        mme = float(media_movel(a[:, 3:4].copy(), "MME", 9)[-1, 0])
        atr = 0.4  # ordem de grandeza do ATR desta serie; conferido abaixo
        o, h, _, c = barras[-1]
        barras[-1] = (o, h, mme + folga * atr, c)
        b = np.array(barras, dtype=np.float64)
        real = float(atr_wilder(b[:, 1:2].copy(), b[:, 2:3].copy(), b[:, 3:4].copy())[-1, 0])
        distancia = (barras[-1][2] - mme) / real
        assert (distancia <= 0.3) is esperado
        assert bool(_sinais(barras)["9.2"].armado[-1, 0]) is esperado


def test_94_venda_desfeita_sem_perder_a_minima() -> None:
    fech = _alta_terminando_em_alta()
    topo = fech[-1]
    fech.append(topo - 1.2)  # vira a MME para baixo (9.1 de venda)
    barras = _barras_de(fech)
    # volta forte, sem perder a minima do candle de baixa
    o = fech[-1]
    c = topo + 0.6
    barras.append((o, c + 0.05, barras[-1][2] + 0.02, c))
    s = _sinais(barras)["9.4"]
    _so_no_ultimo(s, "9.4")
    assert s.stop[-1, 0] == pytest.approx(barras[-2][2] - 0.01)


def test_9x_em_queda_nao_arma() -> None:
    """Pedido de 06/11/2026: 9.2 a 9.4 so em tendencia (MME 80 subindo, topos e
    fundos ascendentes); 9.1 so em suporte com volume. No fim de uma serra de
    queda, sem suporte nem volume, nenhum vale."""
    queda = list(reversed(_serra_subindo()))
    fech = [*queda, queda[-1] + 1.0]
    s = _sinais(_barras_de(fech))
    assert not any(s[n].armado[-30:, 0].any() for n in ("9.1", "9.2", "9.3", "9.4"))
    # e sem os filtros, o mesmo candle armaria o 9.1
    a = np.array(_barras_de(fech), dtype=np.float64)
    o, h, low, c = (a[:, i : i + 1].copy() for i in range(4))
    atr = atr_wilder(h, low, c)
    ret, ev = detectar(h, low, c, atr, Regras(toques_min=2))
    sem = classicos(
        o,
        h,
        low,
        c,
        np.full_like(c, CENTAVO),
        ret,
        ev,
        np.ones_like(c),
        atr,
        RegrasClassicas(tendencia_9x=None, pivo_9x=None, regra_91="nenhum"),
    )
    assert sem["9.1"].armado[-1, 0]


def test_topos_e_fundos_ascendentes() -> None:
    sobe = _barras_de(_serra_subindo())
    desce = _barras_de(list(reversed(_serra_subindo())))
    for barras, esperado in ((sobe, True), (desce, False)):
        a = np.array(barras, dtype=np.float64)
        asc = topos_e_fundos_ascendentes(a[:, 1:2], a[:, 2:3], 3)
        assert bool(asc[-1, 0]) is esperado
    # no comeco nao ha dois fundos e dois topos conhecidos: nao vale
    a = np.array(sobe, dtype=np.float64)
    assert not topos_e_fundos_ascendentes(a[:, 1:2], a[:, 2:3], 3)[:10, 0].any()


def test_pivo_so_vale_depois_de_k_pregoes() -> None:
    """O fundo de um dia so e conhecido k pregoes depois: cortar a serie logo
    depois de um fundo novo mais alto nao pode mudar o que o dia sabia antes."""
    a = np.array(_barras_de(_serra_subindo()), dtype=np.float64)
    cheio = topos_e_fundos_ascendentes(a[:, 1:2], a[:, 2:3], 3)
    for corte in (120, 137, 150):
        parte = topos_e_fundos_ascendentes(a[:corte, 1:2], a[:corte, 2:3], 3)
        assert (parte[:, 0] == cheio[:corte, 0]).all()


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
    rvol = np.asarray(calcular(m.maxima, m.fechamento, m.volume)["rvol"], dtype=np.float64)
    juntos = classicos(
        m.abertura,
        m.maxima,
        m.minima,
        m.fechamento,
        np.full_like(m.fechamento, CENTAVO),
        ret,
        ev,
        rvol,
        atr,
    )
    sozinho = _sinais(_barras_de(fechs[1]))
    for nome in juntos:
        assert (juntos[nome].armado[:, 1] == sozinho[nome].armado[:, 0]).all(), nome
