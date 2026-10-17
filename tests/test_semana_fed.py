"""Fed: edicao valida e medianas do dot plot, contra a tabela real de 16/09/2026."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scanner.semana.fontes import FonteIndisponivelError
from scanner.semana.fontes.fed import edicao_valida, ler_projecao

FIXTURES = Path(__file__).parent / "fixtures" / "semana"
CALENDARIO = (FIXTURES / "fed_calendario.htm").read_text()
PROJECAO = (FIXTURES / "fed_projecoes_2026-09-16.htm").read_text()


def test_edicao_valida_e_a_maior_data_ate_a_sexta() -> None:
    assert edicao_valida(CALENDARIO, date(2026, 10, 16)) == date(2026, 9, 16)


def test_edicao_do_proprio_dia_vale() -> None:
    assert edicao_valida(CALENDARIO, date(2026, 9, 16)) == date(2026, 9, 16)


def test_semana_antiga_nao_usa_projecao_futura() -> None:
    assert edicao_valida(CALENDARIO, date(2026, 9, 15)) == date(2026, 6, 17)
    assert edicao_valida(CALENDARIO, date(2025, 12, 12)) == date(2025, 12, 10)


def test_sem_edicao_anterior_levanta() -> None:
    with pytest.raises(FonteIndisponivelError):
        edicao_valida(CALENDARIO, date(2025, 3, 1))


def test_medianas_da_taxa_em_16_de_setembro_de_2026() -> None:
    r = ler_projecao(PROJECAO, date(2026, 9, 16))

    assert r["data_projecao"] == "2026-09-16"
    assert r["medianas"] == [
        {"periodo": "2026", "taxa": 4.1},
        {"periodo": "2027", "taxa": 4.1},
        {"periodo": "2028", "taxa": 3.9},
        {"periodo": "2029", "taxa": 3.6},
        {"periodo": "longo prazo", "taxa": 3.2},
    ]


def test_ignora_a_linha_de_junho_com_celula_vazia() -> None:
    # A linha "June projection" logo abaixo tem 2029 em branco: nao pode contaminar.
    r = ler_projecao(PROJECAO, date(2026, 9, 16))

    assert [m["taxa"] for m in r["medianas"]] != [3.8, 3.6, 3.4, 3.1]


@pytest.mark.parametrize("html", ["", "<html></html>", "<table><tr><th>x</th></tr></table>"])
def test_tabela_inesperada_levanta(html: str) -> None:
    with pytest.raises(FonteIndisponivelError):
        ler_projecao(html, date(2026, 9, 16))


def test_sem_a_linha_dos_juros_levanta() -> None:
    sem_juros = PROJECAO.replace("Federal funds rate", "Outra coisa")

    with pytest.raises(FonteIndisponivelError, match="Federal funds rate"):
        ler_projecao(sem_juros, date(2026, 9, 16))
