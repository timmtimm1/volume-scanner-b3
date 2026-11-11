"""Numeros da suite de backtest (scanner.backtest.metricas)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scanner.backtest.metricas import (
    FALHOU,
    FIRME,
    FRACO,
    bootstrap,
    curva,
    escolher,
    nivel_da_conferencia,
    pior_fase,
    resumo,
)
from scanner.backtest.simulador import ALVO, STOP


def _trades(
    rs: list[float], controle: list[float] | None = None, inicio: str = "2020-01-01"
) -> pd.DataFrame:
    n = len(rs)
    entrada = pd.date_range(inicio, periods=n, freq="7D")
    return pd.DataFrame(
        {
            "setup": "9.1",
            "saida": "alvo2",
            "data_entrada": entrada,
            "data_saida": entrada + pd.Timedelta(days=5),
            "motivo": [ALVO if r > 0 else STOP for r in rs],
            "dias": 4,
            "r": rs,
            "r_controle": controle if controle is not None else [0.0] * n,
            "alta": True,
        }
    )


def test_resumo_conta_de_cabeca() -> None:
    s = resumo(_trades([2.0, -1.0, -1.0, 2.0]))
    assert s["n"] == 4
    assert s["acerto"] == pytest.approx(0.5)
    assert s["expectativa"] == pytest.approx(0.5)
    assert s["payoff"] == pytest.approx(2.0)
    assert s["fator_lucro"] == pytest.approx(2.0)
    assert s["pct_alvo"] == pytest.approx(0.5)
    assert s["diferenca"] == pytest.approx(0.5)


def test_diferenca_contra_o_controle() -> None:
    s = resumo(_trades([1.0, 1.0], controle=[0.4, 0.6]))
    assert s["diferenca"] == pytest.approx(0.5)


def test_bootstrap_de_valor_constante_e_o_proprio_valor() -> None:
    lo, hi = bootstrap(np.full(50, 0.3), np.arange(50) // 5)
    assert lo == pytest.approx(0.3) and hi == pytest.approx(0.3)


def test_bootstrap_contem_a_media_e_alarga_com_blocos() -> None:
    rng = np.random.default_rng(0)
    v = rng.normal(0.1, 1.0, 2000)
    lo, hi = bootstrap(v, np.arange(2000))
    assert lo < v.mean() < hi
    # o mesmo valor repetido dentro do bloco: o intervalo por bloco fica mais largo
    blocos = np.arange(2000) // 50
    v_bloco = np.repeat(rng.normal(0.1, 1.0, 40), 50)
    lo_b, hi_b = bootstrap(v_bloco, blocos)
    lo_t, hi_t = bootstrap(v_bloco, np.arange(2000))
    assert (hi_b - lo_b) > 3 * (hi_t - lo_t)


def _linha(
    setup: str, saida: str, periodo: str, exp: float, n: int = 500, dif: float = 0.1
) -> dict[str, object]:
    return {
        "setup": setup,
        "saida": saida,
        "grupo": "todos",
        "periodo": periodo,
        "n": n,
        "expectativa": exp,
        "diferenca": dif,
        "ic_baixo": exp - 0.1,
        "ic_alto": exp + 0.1,
    }


def test_escolha_so_olha_1995_2015() -> None:
    g = pd.DataFrame(
        [
            _linha("9.1", "alvo2", "1995-2015", 0.30),
            _linha("9.1", "mme9", "1995-2015", 0.10),
            _linha(
                "9.1", "alvo3", "1995-2015", 0.90, n=50
            ),  # poucos trades: nao pode ser escolhida
            _linha("9.1", "alvo2", "2016-2026", 0.05, dif=0.02),
            _linha("9.1", "mme9", "2016-2026", 0.80),  # melhor depois, mas a escolha ja foi feita
            _linha("9.1", "alvo3", "2016-2026", 0.80),
        ]
    )
    e = escolher(g).iloc[0]
    assert e["saida"] == "alvo2"
    assert e["exp_conferencia"] == pytest.approx(0.05)
    assert e["passou"]


def test_positivo_mas_abaixo_do_controle_nao_passa() -> None:
    g = pd.DataFrame(
        [
            _linha("123", "alvo1", "1995-2015", 0.2),
            _linha("123", "alvo1", "2016-2026", 0.1, dif=-0.05),
        ]
    )
    assert not escolher(g).iloc[0]["passou"]


def test_curva_acumula_e_recua() -> None:
    t = _trades([2.0, -1.0, -1.0, -1.0, 2.0])
    t["data_saida"] = pd.to_datetime(
        ["2020-01-10", "2020-02-10", "2020-03-10", "2020-04-10", "2020-05-10"]
    )
    c = curva(t)
    c = c[c["grupo"] == "todos"]
    assert list(c["acumulado"]) == [2.0, 1.0, 0.0, -1.0, 1.0]
    assert list(c["recuo"]) == [0.0, -1.0, -2.0, -3.0, -1.0]


def test_tres_niveis() -> None:
    assert nivel_da_conferencia(0.3, 0.1, 0.2) == FIRME
    assert nivel_da_conferencia(0.3, -0.1, 0.2) == FRACO
    assert nivel_da_conferencia(0.3, 0.1, -0.01) == FALHOU  # positivo, mas o controle ganhou
    assert nivel_da_conferencia(-0.1, -0.3, 0.2) == FALHOU
    assert nivel_da_conferencia(float("nan"), float("nan"), float("nan")) == FALHOU


def test_escolha_leva_o_nivel() -> None:
    g = pd.DataFrame(
        [_linha("forca", "mme9", "1995-2015", 0.2), _linha("forca", "mme9", "2016-2026", 0.3)]
    )
    e = escolher(g).iloc[0]
    assert e["nivel"] == FIRME  # ic_baixo 0,2 > 0 e diferenca 0,1 > 0


def _dias(textos: list[str]) -> np.ndarray:
    return np.array(textos, dtype="datetime64[D]")


def test_pior_fase_de_um_caminho_so() -> None:
    # um sinal por dia de entrada, sem sobreposicao: so existe um caminho
    ent = _dias(["2020-01-01", "2020-01-10", "2020-01-20", "2020-02-01", "2020-02-10"])
    sai = ent + np.timedelta64(3, "D")
    r = np.array([2.0, -1.0, -1.0, -1.0, 2.0])
    assert pior_fase(ent, sai, r) == (3.0, -3.0)


def test_pior_fase_pula_o_sinal_que_cai_dentro_do_trade_aberto() -> None:
    # o 2o sinal entra enquanto o 1o ainda esta aberto: quem opera um por vez
    # nao pega; sem ele, sao duas perdas seguidas, nao tres
    ent = _dias(["2020-01-01", "2020-01-03", "2020-01-10", "2020-01-20"])
    sai = _dias(["2020-01-08", "2020-01-05", "2020-01-12", "2020-01-22"])
    r = np.array([-1.0, -1.0, -1.0, 1.0])
    assert pior_fase(ent, sai, r) == (2.0, -2.0)


def test_pior_fase_sem_perda_e_sem_trade() -> None:
    ent = _dias(["2020-01-01", "2020-01-10"])
    assert pior_fase(ent, ent, np.array([1.0, 2.0])) == (0.0, 0.0)
    vazio = _dias([])
    assert all(np.isnan(pior_fase(vazio, vazio, np.array([]))))


def test_pior_fase_entra_no_resumo() -> None:
    m = resumo(_trades([1.0, -1.0, -1.0, 2.0]))
    assert m["pior_sequencia"] == 2.0
    assert m["pior_recuo"] == -2.0
