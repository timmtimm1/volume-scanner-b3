"""Ciclo de vida dos Setups (scanner.setups): armado, confirmado, stop, prazo."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import Engine, delete, func, select

from scanner.config import ScannerConfig, SetupsConfig, UniverseConfig
from scanner.gatilhos.regra import Analise, analisar, setups
from scanner.setups import avancar, resultados, run_setups
from tests.gatilhos_sinteticos import barras, dia_do_martelo

CFG = SetupsConfig()
UNIVERSO = UniverseConfig()
# pregao seguinte ao martelo (maxima 10,48, minima 9,97, fechamento 10,45)
CONFIRMA = (10.50, 10.70, 10.40, 10.60)
NAO_CONFIRMA = (10.40, 10.45, 10.20, 10.30)
ACIMA = (10.60, 10.75, 10.55, 10.70)


def _armado(frame: pd.DataFrame, extra: int) -> tuple[pd.DataFrame, Analise]:
    a = analisar(frame, CFG, UNIVERSO)
    s = setups(a, CFG)
    linha = s[s["trade_date"] == dia_do_martelo(frame, extra=extra)].copy()
    assert len(linha) == 1
    linha["id"] = 1
    linha["estado"] = "armado"
    linha["confirmado_em"] = None
    linha["entrada"] = None
    return linha, a


def _dias(frame: pd.DataFrame, extra: int) -> list[date]:
    return list(frame["trade_date"].iloc[-1 - extra :])


def test_confirma_quando_o_dia_seguinte_passa_da_maxima() -> None:
    frame = barras(extra=[CONFIRMA])
    linha, a = _armado(frame, 1)
    mud = avancar(linha, a, prazo=20)
    assert mud["estado"].tolist() == ["confirmado"]
    assert mud["confirmado_em"].iloc[0] == _dias(frame, 1)[1]
    assert mud["entrada"].iloc[0] == pytest.approx(10.50)  # abriu acima da maxima (10,48)


def test_entrada_na_maxima_quando_abre_abaixo_e_passa() -> None:
    frame = barras(extra=[(10.40, 10.60, 10.35, 10.55)])
    linha, a = _armado(frame, 1)
    assert avancar(linha, a, prazo=20)["entrada"].iloc[0] == pytest.approx(10.48)


def test_nao_confirma_quando_o_dia_seguinte_fica_abaixo() -> None:
    frame = barras(extra=[NAO_CONFIRMA])
    linha, a = _armado(frame, 1)
    mud = avancar(linha, a, prazo=20)
    assert mud["estado"].tolist() == ["nao_confirmou"]
    assert mud["encerrado_em"].iloc[0] == _dias(frame, 1)[1]
    assert mud["confirmado_em"].iloc[0] is None


def test_sem_pregao_seguinte_continua_armado() -> None:
    frame = barras()
    linha, a = _armado(frame, 0)
    assert avancar(linha, a, prazo=20).empty


def test_stop_no_primeiro_fechamento_abaixo_da_minima() -> None:
    caiu = (10.0, 10.05, 9.85, 9.90)  # fecha 9,90, abaixo da minima do padrao (9,97)
    frame = barras(extra=[CONFIRMA, ACIMA, caiu, ACIMA])
    linha, a = _armado(frame, 4)
    mud = avancar(linha, a, prazo=20)
    assert mud["estado"].tolist() == ["stop"]
    assert mud["encerrado_em"].iloc[0] == _dias(frame, 4)[3]
    assert mud["saida"].iloc[0] == pytest.approx(9.90)


def test_prazo_depois_de_n_pregoes_confirmado() -> None:
    frame = barras(extra=[CONFIRMA] + [ACIMA] * 5)
    linha, a = _armado(frame, 6)
    assert avancar(linha, a, prazo=5)["estado"].tolist() == ["prazo"]
    assert avancar(linha, a, prazo=6)["estado"].tolist() == ["confirmado"]


def test_confirmado_continua_ate_o_prazo() -> None:
    frame = barras(extra=[CONFIRMA, ACIMA])
    linha, a = _armado(frame, 2)
    mud = avancar(linha, a, prazo=20)
    linha.loc[:, ["estado", "confirmado_em", "entrada"]] = mud[
        ["estado", "confirmado_em", "entrada"]
    ].to_numpy()
    assert avancar(linha, a, prazo=20).empty  # nada mudou: segue em andamento


def test_desdobramento_depois_do_martelo() -> None:
    # 1 para 2 no pregao seguinte: abre 5,25, maxima 5,40. Em escala nova a
    # maxima do martelo e 5,24 -- confirmou, e a entrada sai na escala do dia
    frame = barras(extra=[(5.25, 5.40, 5.20, 5.35)])
    linha, a = _armado(frame, 1)
    mud = avancar(linha, a, prazo=20)
    assert mud["estado"].tolist() == ["confirmado"]
    assert mud["entrada"].iloc[0] == pytest.approx(5.25)


def test_resultados_contra_o_mercado() -> None:
    frame = barras(extra=[CONFIRMA, ACIMA, ACIMA, ACIMA, ACIMA, ACIMA, ACIMA])
    linha, a = _armado(frame, 7)
    mud = avancar(linha, a, prazo=20)
    linha.loc[:, ["estado", "confirmado_em", "entrada"]] = mud[
        ["estado", "confirmado_em", "entrada"]
    ].to_numpy()
    res = resultados(linha, a).iloc[0]
    assert res["r5"] == pytest.approx(10.70 / 10.45 - 1)
    assert res["m5"] == pytest.approx(res["r5"])  # o universo e este papel so
    assert res["rc5"] == pytest.approx(10.70 / 10.50 - 1)
    assert pd.isna(res["r10"])


@pytest.mark.db
def test_noite_a_noite_contra_o_banco(engine: Engine) -> None:
    from scanner.storage.models import Nivel, Setup

    with engine.begin() as conn:
        conn.execute(delete(Setup))
        conn.execute(delete(Nivel))
    config = ScannerConfig()

    noite1 = barras()
    dia1 = dia_do_martelo(noite1)
    assert isinstance(dia1, date)
    rel = run_setups(engine, config, dia1, bars=noite1)
    assert rel.estreia
    assert rel.armados == [("AAAA3", False)]
    with engine.connect() as conn:
        linha = conn.execute(select(Setup)).one()._mapping
        n_niveis = conn.execute(select(func.count()).select_from(Nivel)).scalar_one()
    assert linha["ao_vivo"] and linha["estado"] == "armado"
    assert float(linha["maxima"]) == pytest.approx(10.48)
    assert n_niveis > 0

    # rodar de novo a mesma noite nao duplica nada
    rel = run_setups(engine, config, dia1, bars=noite1)
    assert not rel.estreia and rel.gravados == 0
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(Setup)).scalar_one() == 1
        assert conn.execute(select(func.count()).select_from(Nivel)).scalar_one() == n_niveis

    # a noite seguinte confirma
    noite2 = barras(extra=[CONFIRMA])
    dia2 = noite2["trade_date"].iloc[-1]
    rel = run_setups(engine, config, dia2, bars=noite2)
    assert rel.confirmados == ["AAAA3"]
    with engine.connect() as conn:
        linha = conn.execute(select(Setup)).one()._mapping
    assert linha["estado"] == "confirmado"
    assert linha["confirmado_em"] == dia2
    assert float(linha["entrada"]) == pytest.approx(10.50)
    assert linha["r5"] is None
