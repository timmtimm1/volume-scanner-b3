"""A regra dos Setups (scanner.gatilhos.regra), sobre barras sinteticas."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scanner.config import SetupsConfig, UniverseConfig
from scanner.gatilhos.regra import analisar, niveis, setups
from tests.gatilhos_sinteticos import barras, dia_do_martelo

CFG = SetupsConfig()
UNIVERSO = UniverseConfig()


def _setups(frame: pd.DataFrame) -> pd.DataFrame:
    return setups(analisar(frame, CFG, UNIVERSO), CFG)


def _no_dia(frame: pd.DataFrame) -> pd.DataFrame:
    s = _setups(frame)
    return s[s["trade_date"] == dia_do_martelo(frame)]


def test_martelo_no_suporte_com_volume_vira_setup() -> None:
    frame = barras(volume_martelo=2.0)
    s = _no_dia(frame)
    assert len(s) == 1
    linha = s.iloc[0]
    assert linha["categoria"] == "reversao"
    assert linha["padroes"] == ["martelo"]
    assert linha["toques"] >= 3
    assert linha["rvol"] == pytest.approx(2.0)
    assert not linha["destaque"]
    assert linha["minima"] == pytest.approx(9.97)  # o stop e a minima do martelo
    assert linha["maxima"] == pytest.approx(10.48)  # a confirmacao e acima da maxima
    assert linha["suporte"] == pytest.approx(9.95, abs=0.01)
    assert linha["resistencia"] == pytest.approx(12.05, abs=0.01)
    assert linha["espaco_r"] == pytest.approx((12.05 - 10.45) / (10.45 - 9.97), abs=0.05)


def test_volume_de_destaque() -> None:
    s = _no_dia(barras(volume_martelo=3.0))
    assert bool(s.iloc[0]["destaque"])


def test_volume_baixo_nao_entra() -> None:
    assert _no_dia(barras(volume_martelo=1.2)).empty


def test_sem_martelo_nao_ha_setup() -> None:
    assert _no_dia(barras(martelo=False, volume_martelo=2.0)).empty


def test_resistencia_perto_demais_nao_entra() -> None:
    # topo em 10,9: a resistencia fica a ~1R do fechamento, e a regra pede 2R
    assert _no_dia(barras(topo=10.9, volume_martelo=2.0)).empty


def test_tendencia_de_baixa_nao_entra() -> None:
    # 200 pregoes descendo de 16 para 12,2, depois a mesma serra curta com o
    # martelo: o papel fica abaixo de uma MM200 que cai
    def antes_da_serra(de: float, ate: float) -> pd.DataFrame:
        serra_curta = barras(dias=66, volume_martelo=2.0)
        serra_curta["trade_date"] = pd.bdate_range("2024-12-02", periods=len(serra_curta)).date
        passos = np.linspace(de, ate, 200)
        abre = np.concatenate([[passos[0]], passos[:-1]])
        prefixo = pd.DataFrame(
            {
                "ticker": "AAAA3",
                "trade_date": pd.bdate_range("2024-03-01", periods=200).date,
                "open": abre,
                "high": np.fmax(abre, passos) + 0.05,
                "low": np.fmin(abre, passos) - 0.05,
                "close": passos,
                "volume_financial": 1_000_000.0,
            }
        )
        return pd.concat([prefixo, serra_curta], ignore_index=True)

    # descendo de 16 para 12,2: abaixo de uma MM200 que cai -> fora
    assert _no_dia(antes_da_serra(16.0, 12.2)).empty
    # o mesmo martelo depois de um patamar plano no meio da serra -> entra
    assert not _no_dia(antes_da_serra(11.0, 11.0)).empty


def test_precos_saem_na_escala_do_proprio_dia() -> None:
    # desdobramento de 1 para 2 depois do martelo: o setup continua com os
    # precos que o COTAHIST publicou naquele dia
    frame = barras(volume_martelo=2.0, extra=[(5.25, 5.4, 5.2, 5.35), (5.35, 5.5, 5.3, 5.45)])
    s = _setups(frame)
    linha = s[s["trade_date"] == dia_do_martelo(frame, extra=2)].iloc[0]
    assert linha["maxima"] == pytest.approx(10.48)
    assert linha["minima"] == pytest.approx(9.97)


def test_niveis_para_a_ficha() -> None:
    nv = niveis(analisar(barras(), CFG, UNIVERSO), CFG)
    sup = nv[(nv["lado"] == "suporte") & nv["ativo"]]
    assert len(sup) == 1
    linha = sup.iloc[0]
    assert linha["preco"] == pytest.approx(9.95, abs=0.01)
    assert linha["vale_desde"] is not None and linha["vale_desde"] > linha["de"]
    assert len(linha["toques"]) >= 3
    assert all(isinstance(t[0], str) and isinstance(t[1], bool) for t in linha["toques"])
