"""Yahoo: parse da serie e variacoes, contra respostas reais de 17/10/2026."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from scanner.semana.fontes import FonteIndisponivelError
from scanner.semana.fontes.yahoo import ler_serie, variacoes_da_serie
from scanner.semana.periodo import semana_da_data

FIXTURES = Path(__file__).parent / "fixtures" / "semana"
SEMANA = semana_da_data(date(2026, 10, 16))


def _json(nome: str) -> Any:
    return json.loads((FIXTURES / nome).read_text())


def test_ler_serie_converte_carimbo_em_data_local() -> None:
    serie = ler_serie(_json("yahoo_bvsp.json"))

    assert serie.index[-1].date() == date(2026, 10, 16)
    assert serie.iloc[-1] == 205430.0
    # 12/10 e feriado na B3: nao ha ponto do Ibovespa.
    assert pd.Timestamp("2026-10-12") not in serie.index


def test_ler_serie_descarta_fechamento_nulo() -> None:
    dados = _json("yahoo_bvsp.json")
    dados["chart"]["result"][0]["indicators"]["quote"][0]["close"][-1] = None

    serie = ler_serie(dados)

    assert serie.index[-1].date() == date(2026, 10, 15)


def test_ibovespa_da_semana_do_feriado() -> None:
    r = variacoes_da_serie(ler_serie(_json("yahoo_bvsp.json")), SEMANA)

    assert r["valor"] == 205430.0
    assert r["data"] == "2026-10-16"
    assert r["semana"] == pytest.approx(205430.0 / 209067.0 - 1)  # base: sexta 09/10
    assert r["mes"] == pytest.approx(205430.0 / 186340.0 - 1)  # base: 30/09
    assert r["ano"] == pytest.approx(205430.0 / 161125.0 - 1)  # base: 30/12/2025


def test_brent_negociado_na_segunda_feriada_nao_vira_base() -> None:
    # O Brent negocia em 12/10, que ja e da semana: a base segue sendo o ultimo
    # ponto ANTES da segunda (sexta 09/10), e nao o de 12/10.
    r = variacoes_da_serie(ler_serie(_json("yahoo_brent.json")), SEMANA)

    assert r["valor"] == pytest.approx(109.86000061035156)
    assert r["semana"] == pytest.approx(109.86000061035156 / 104.72000122070312 - 1)


def test_sem_base_devolve_none() -> None:
    serie = ler_serie(_json("yahoo_bvsp.json"))
    curta = serie.loc["2026-10-05":]

    r = variacoes_da_serie(curta, SEMANA)

    assert r["semana"] is not None
    assert r["mes"] is None
    assert r["ano"] is None


def test_serie_parada_levanta() -> None:
    serie = ler_serie(_json("yahoo_bvsp.json")).loc[:"2026-10-06"]

    with pytest.raises(FonteIndisponivelError, match="velho demais"):
        variacoes_da_serie(serie, SEMANA)


def test_serie_sem_ponto_ate_a_sexta_levanta() -> None:
    serie = ler_serie(_json("yahoo_bvsp.json")).loc["2026-10-19":]

    with pytest.raises(FonteIndisponivelError):
        variacoes_da_serie(serie, SEMANA)


@pytest.mark.parametrize("dados", [{}, {"chart": {"result": None}}, {"chart": {"result": []}}])
def test_formato_inesperado(dados: Any) -> None:
    with pytest.raises(FonteIndisponivelError):
        ler_serie(dados)
