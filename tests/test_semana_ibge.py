"""IBGE: calendario real recortado (consulta de 17/10/2026 para 19/10 a 31/12)."""

from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

import pytest

from scanner.semana.fontes import FonteIndisponivelError
from scanner.semana.fontes.ibge import ler_calendario

DADOS = json.loads(
    (Path(__file__).parent / "fixtures" / "semana" / "ibge_calendario.json").read_text()
)


def _por_data(inicio: date, fim: date) -> dict[tuple[date, str], tuple[time | None, str | None]]:
    return {(e.data, e.evento): (e.hora, e.detalhe) for e in ler_calendario(DADOS, inicio, fim)}


def test_ipca_15_sai_as_nove_de_brasilia_embora_a_api_diga_doze() -> None:
    achados = ler_calendario(DADOS, date(2026, 10, 19), date(2026, 10, 23))

    assert len(achados) == 1
    e = achados[0]
    assert (e.data, e.hora, e.pais, e.evento, e.detalhe, e.fonte) == (
        date(2026, 10, 23),
        time(9, 0),
        "BR",
        "IPCA-15",
        "outubro",
        "IBGE",
    )
    assert e.focus is None  # o Focus nao tem consenso para o IPCA-15


def test_semana_de_2_a_6_de_novembro_tem_so_a_pim_pf() -> None:
    achados = _por_data(date(2026, 11, 2), date(2026, 11, 6))

    assert achados == {
        (date(2026, 11, 5), "Produção industrial (PIM-PF)"): (time(9, 0), "setembro")
    }


def test_referencias_de_cada_produto_vem_dos_campos_da_api() -> None:
    achados = _por_data(date(2026, 10, 26), date(2026, 12, 31))

    assert (
        achados[(date(2026, 10, 30), "Desemprego (PNAD Contínua)")][1] == "trimestre até setembro"
    )
    assert achados[(date(2026, 11, 12), "IPCA")][1] == "outubro"
    assert achados[(date(2026, 11, 13), "Varejo (PMC)")][1] == "setembro"
    assert achados[(date(2026, 11, 26), "IPCA-15")][1] == "novembro"
    assert achados[(date(2026, 12, 2), "PIB (trimestral)")][1] == "3º trimestre"


def test_ipca_pede_o_consenso_do_mes_de_referencia() -> None:
    ipca = next(
        e
        for e in ler_calendario(DADOS, date(2026, 11, 9), date(2026, 11, 13))
        if e.evento == "IPCA"
    )

    assert ipca.focus is not None
    assert (ipca.focus.indicador, ipca.focus.chave) == ("ipca", "10/2026")


def test_produto_fora_da_lista_nao_entra() -> None:
    # A fixture traz o IPCA Especial (9262) e a safra (9201): nao sao da lista.
    todos = ler_calendario(DADOS, date(2026, 10, 19), date(2026, 12, 31))

    assert len(todos) == 13
    assert {e.evento for e in todos} == {
        "IPCA",
        "IPCA-15",
        "PIB (trimestral)",
        "Desemprego (PNAD Contínua)",
        "Varejo (PMC)",
        "Produção industrial (PIM-PF)",
    }


def test_referencia_zerada_deixa_o_detalhe_nulo() -> None:
    item = dict(DADOS["items"][0], mes_referencia_inicio=0, ano_referencia_inicio=0)

    achados = ler_calendario({"items": [item]}, date(2026, 12, 29), date(2026, 12, 29))

    assert achados[0].detalhe is None


def test_formato_inesperado_levanta() -> None:
    with pytest.raises(FonteIndisponivelError):
        ler_calendario({"erro": "x"}, date(2026, 10, 19), date(2026, 10, 23))
    with pytest.raises(FonteIndisponivelError):
        ler_calendario({"items": [{"produto_id": 9260}]}, date(2026, 10, 19), date(2026, 10, 23))
