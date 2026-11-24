"""O que fica de fora das contas de cripto (backtest e analise contra o Bitcoin)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scanner.cripto.filtros import e_estavel, motivo_de_fora


def _serie(inicio: str, dias: int = 120, *, estavel: bool = False) -> pd.Series:
    rng = np.random.default_rng(3)
    passos = rng.normal(0, 0.001 if estavel else 0.04, dias)
    return pd.Series(np.cumprod(1 + passos), index=pd.date_range(inicio, periods=dias, freq="D"))


@pytest.mark.parametrize(
    ("moeda", "inicio", "motivo"),
    [
        ("WBTC", "2020-01-01", "embrulhado"),
        ("PAXG", "2020-01-01", "embrulhado"),
        ("BULL", "2020-01-17", "alavancado"),
        ("BEAR", "2020-01-17", "alavancado"),
        ("NVDAB", "2026-06-11", "acao tokenizada"),
        ("SQQQB", "2026-09-02", "acao tokenizada"),
        # Cripto que termina em B, estreada antes das acoes da Binance: entra.
        ("SHIB", "2021-05-10", None),
        ("ARB", "2023-03-23", None),
        ("YB", "2025-10-15", None),
        ("ETH", "2017-08-17", None),
    ],
)
def test_motivo_de_fora(moeda: str, inicio: str, motivo: str | None) -> None:
    assert motivo_de_fora(moeda, _serie(inicio)) == motivo


def test_stablecoin_sai_pelo_preco_e_nao_pelo_nome() -> None:
    assert motivo_de_fora("QUALQUER", _serie("2022-01-01", estavel=True)) == "estavel"
    assert e_estavel(_serie("2022-01-01", estavel=True))
    assert not e_estavel(_serie("2022-01-01"))


def test_poucos_dias_nao_bastam_para_chamar_de_stablecoin() -> None:
    assert not e_estavel(_serie("2022-01-01", 20, estavel=True))


def test_dias_vazios_nao_contam_como_preco() -> None:
    serie = _serie("2022-01-01", estavel=True)
    serie.iloc[::2] = np.nan
    assert e_estavel(serie)
