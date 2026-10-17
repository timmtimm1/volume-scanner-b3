"""A semana de pregao: sexta nominal, base no pregao anterior, feriados."""

from __future__ import annotations

from datetime import date

import pytest

from scanner.semana import periodo
from scanner.semana.periodo import (
    SemanaSemPregaoError,
    semana_da_data,
    semana_encerrada,
)


@pytest.mark.parametrize("dia", [date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 14)])
def test_semana_do_feriado_de_12_de_outubro(dia: date) -> None:
    semana = semana_da_data(dia)

    assert semana.sexta == date(2026, 10, 16)
    # 12/10 e feriado: a semana tem 4 pregoes e a base e a sexta anterior.
    assert semana.inicio == date(2026, 10, 9)
    assert semana.fim == date(2026, 10, 16)
    assert semana.pregoes == (
        date(2026, 10, 13),
        date(2026, 10, 14),
        date(2026, 10, 15),
        date(2026, 10, 16),
    )


def test_domingo_pertence_a_semana_que_acabou() -> None:
    assert semana_da_data(date(2026, 10, 18)).sexta == date(2026, 10, 16)


def test_sexta_feira_santa_o_ultimo_pregao_e_a_quinta() -> None:
    semana = semana_da_data(date(2026, 4, 3))

    assert semana.sexta == date(2026, 4, 3)  # a sexta nominal segue sendo o nome
    assert semana.fim == date(2026, 4, 2)
    assert semana.inicio == date(2026, 3, 27)
    assert date(2026, 4, 3) not in semana.pregoes


def test_semana_encerrada_no_meio_da_semana_e_a_anterior() -> None:
    semana = semana_encerrada(date(2026, 10, 14))  # quarta

    assert semana.sexta == date(2026, 10, 9)
    assert semana.fim == date(2026, 10, 9)
    assert semana.inicio == date(2026, 10, 2)


@pytest.mark.parametrize("hoje", [date(2026, 10, 17), date(2026, 10, 18)])
def test_semana_encerrada_no_fim_de_semana_e_a_que_terminou(hoje: date) -> None:
    assert semana_encerrada(hoje).sexta == date(2026, 10, 16)


def test_semana_encerrada_na_segunda_e_na_sexta_olha_para_tras() -> None:
    assert semana_encerrada(date(2026, 10, 19)).sexta == date(2026, 10, 16)
    assert semana_encerrada(date(2026, 10, 16)).sexta == date(2026, 10, 9)


def test_semana_sem_nenhum_pregao(monkeypatch: pytest.MonkeyPatch) -> None:
    # Nao existe semana real assim no calendario de hoje: simula uma.
    monkeypatch.setattr(periodo, "trading_days", lambda *_a: [])

    with pytest.raises(SemanaSemPregaoError):
        semana_da_data(date(2026, 10, 16))


def test_proxima_semana_a_partir_de_16_de_outubro() -> None:
    from scanner.semana.periodo import proxima_semana

    assert proxima_semana(semana_da_data(date(2026, 10, 16))) == (
        date(2026, 10, 19),
        date(2026, 10, 23),
    )


def test_proxima_semana_depois_da_sexta_feira_santa_comeca_na_segunda() -> None:
    from scanner.semana.periodo import proxima_semana

    # A sexta nominal e 03/04 (feriado, fim = quinta 02/04): a seguinte e 06/04 a 10/04.
    assert proxima_semana(semana_da_data(date(2026, 4, 3))) == (
        date(2026, 4, 6),
        date(2026, 4, 10),
    )
