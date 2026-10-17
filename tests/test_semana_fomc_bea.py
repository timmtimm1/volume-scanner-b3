"""FOMC e BEA: paginas reais recortadas (leitura de 17/10/2026)."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from scanner.semana.fontes import FonteIndisponivelError
from scanner.semana.fontes.bea import ler_agenda
from scanner.semana.fontes.fomc import ler_eventos, reunioes

FIXTURES = Path(__file__).parent / "fixtures" / "semana"
FOMC = (FIXTURES / "fed_fomc_calendario.htm").read_text()
BEA = (FIXTURES / "bea_agenda.htm").read_text()


def test_fomc_2026_e_2027_batem_com_a_pagina() -> None:
    todas = dict(reunioes(FOMC))

    ultimos_2026 = [(d.month, d.day, p) for d, p in todas.items() if d.year == 2026]
    ultimos_2027 = [(d.month, d.day, p) for d, p in todas.items() if d.year == 2027]
    assert ultimos_2026 == [
        (1, 28, False),
        (3, 18, True),
        (4, 29, False),
        (6, 17, True),
        (7, 29, False),
        (9, 16, True),
        (10, 28, False),
        (12, 9, True),
    ]
    assert ultimos_2027 == [
        (1, 27, False),
        (3, 17, True),
        (4, 28, False),
        (6, 9, True),
        (7, 28, False),
        (9, 15, True),
        (10, 27, False),
        (12, 8, True),
    ]


def test_cada_ano_fica_no_seu_painel() -> None:
    anos = [d.year for d, _ in reunioes(FOMC)]

    # 8 em 2027, 8 em 2026, 8 em 2025 (a votacao "22 (notation vote)" nao conta) e 8 em 2024.
    assert [anos.count(a) for a in (2027, 2026, 2025, 2024)] == [8, 8, 8, 8]


def test_reuniao_que_atravessa_o_mes_usa_o_mes_final() -> None:
    # "Apr/May" com "30-1" em 2024: a decisao e em 1o de maio.
    assert (date(2024, 5, 1), True) in reunioes(FOMC) or (date(2024, 5, 1), False) in reunioes(FOMC)


def test_decisao_do_fomc_as_14h_de_nova_york() -> None:
    eventos, avisos = ler_eventos(FOMC, date(2026, 10, 26), date(2026, 10, 30))

    assert avisos == []
    assert len(eventos) == 1
    e = eventos[0]
    # 14:00 em Nova York (UTC-4 em 28/10, ainda no horario de verao) -> 15:00 em Brasilia.
    assert (e.data, e.hora, e.evento, e.detalhe, e.pais, e.fonte) == (
        date(2026, 10, 28),
        time(15, 0),
        "FOMC: decisão",
        None,
        "EUA",
        "Fed",
    )


def test_reuniao_com_projecoes_e_horario_depois_do_fim_do_verao() -> None:
    eventos, _ = ler_eventos(FOMC, date(2026, 12, 7), date(2026, 12, 11))

    assert [(e.data, e.hora, e.detalhe) for e in eventos] == [
        (date(2026, 12, 9), time(16, 0), "com projeções")
    ]


def test_semana_sem_fomc() -> None:
    assert ler_eventos(FOMC, date(2026, 10, 19), date(2026, 10, 23)) == ([], [])


def test_ano_ausente_da_pagina_gera_aviso() -> None:
    eventos, avisos = ler_eventos(FOMC, date(2028, 1, 3), date(2028, 1, 7))

    assert eventos == []
    assert avisos == ["calendário do FOMC sem 2028"]


def test_pagina_sem_paineis_levanta() -> None:
    with pytest.raises(FonteIndisponivelError):
        reunioes("<html></html>")


def test_bea_pib_e_pce_da_ultima_semana_de_outubro() -> None:
    eventos, avisos = ler_agenda(BEA, date(2026, 10, 26), date(2026, 10, 30))

    assert avisos == []
    assert [(e.data, e.hora, e.evento, e.detalhe) for e in eventos] == [
        (
            date(2026, 10, 29),
            time(9, 30),
            "PIB dos EUA",
            "GDP (Advance Estimate), 3rd Quarter 2026",
        ),
        (
            date(2026, 10, 29),
            time(9, 30),
            "PCE (renda e gastos pessoais)",
            "Personal Income and Outlays, September 2026",
        ),
    ]
    assert {e.pais for e in eventos} == {"EUA"} and {e.fonte for e in eventos} == {"BEA"}


def test_bea_so_entram_os_releases_nacionais() -> None:
    eventos, _ = ler_agenda(BEA, date(2026, 1, 1), date(2026, 12, 31))

    detalhes = [e.detalhe or "" for e in eventos]
    assert any(d.startswith("Gross Domestic Product, 3rd Quarter 2025") for d in detalhes)
    # "by State" (23/01) e "by County" (05/02) estao na fixture e nao entram.
    assert not any(" by State" in d.split(",")[0] or "by County" in d for d in detalhes)
    assert len(eventos) == 6  # 22/01 PIB e PCE, 29/10 PIB e PCE, 25/11 PIB e PCE


def test_bea_hora_de_novembro_depois_do_fim_do_verao() -> None:
    eventos, _ = ler_agenda(BEA, date(2026, 11, 23), date(2026, 11, 27))

    assert {(e.data, e.hora) for e in eventos} == {(date(2026, 11, 25), time(10, 30))}


def test_bea_ano_fora_da_pagina_avisa() -> None:
    eventos, avisos = ler_agenda(BEA, date(2027, 1, 4), date(2027, 1, 8))

    assert eventos == []
    assert avisos == ["agenda do BEA sem 2027"]


def test_bea_sem_cabecalho_de_ano_levanta() -> None:
    with pytest.raises(FonteIndisponivelError):
        ler_agenda("<html></html>", date(2026, 10, 19), date(2026, 10, 23))
