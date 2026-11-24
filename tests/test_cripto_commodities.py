"""As commodities da analise: o grupo de cada moeda e a lista igual a do site."""

from __future__ import annotations

import re
from pathlib import Path

from scanner.cripto import filtros
from scanner.cripto.commodities import (
    A_VISTA,
    CONTRATOS,
    GRUPO_COMMODITY,
    GRUPO_CRIPTO,
    grupo,
)


def test_ouro_tokenizado_e_contratos_sao_commodity_o_resto_e_cripto() -> None:
    assert grupo("PAXG") == grupo("XAUT") == grupo("XAU") == grupo("NATGAS") == GRUPO_COMMODITY
    assert grupo("BTC") == grupo("WBTC") == grupo("USDC") == GRUPO_CRIPTO


def test_os_contratos_sao_perpetuos_contra_usdt_com_o_ticker_no_nome() -> None:
    for ticker, contrato in CONTRATOS.items():
        assert contrato.par == f"{ticker}USDT"
    assert not A_VISTA & set(CONTRATOS)


def test_o_backtest_continua_sem_o_ouro_tokenizado() -> None:
    # A analise poe o ouro num grupo a parte; o backtest de cripto nao o opera.
    assert A_VISTA <= filtros.EMBRULHADOS


def test_a_lista_do_site_e_a_mesma_do_pipeline() -> None:
    texto = (Path(__file__).parents[1] / "web/src/lib/commodities.ts").read_text(encoding="utf-8")
    no_site = dict(re.findall(r'ticker: "(\w+)",\s*nome: "[^"]+",\s*tipo: "(\w+)"', texto))
    assert no_site == {
        **dict.fromkeys(A_VISTA, "token"),
        **dict.fromkeys(CONTRATOS, "contrato"),
    }
    pares = dict(re.findall(r'ticker: "(\w+)",[^}]*?par: "(\w+)"', texto, flags=re.S))
    assert {t: pares[t] for t in CONTRATOS} == {t: c.par for t, c in CONTRATOS.items()}
