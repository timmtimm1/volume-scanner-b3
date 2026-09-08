"""Calendario B3.

As datas esperadas abaixo sao escritas a mao, nao geradas pelo modulo: um teste
que chama o proprio codigo para produzir o gabarito nao prova nada.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import Engine

from scanner.calendar import (
    UnsupportedYearError,
    ash_wednesday,
    carnival_monday,
    carnival_tuesday,
    corpus_christi,
    easter,
    good_friday,
    holidays,
    is_trading_day,
    next_trading_day,
    previous_trading_day,
    sessions_before,
    trading_days,
)

FERIADOS_2024 = {
    date(2024, 1, 1),  # Confraternizacao Universal
    date(2024, 2, 12),  # carnaval (segunda)
    date(2024, 2, 13),  # carnaval (terca)
    date(2024, 3, 29),  # Sexta-feira Santa
    date(2024, 4, 21),  # Tiradentes (domingo)
    date(2024, 5, 1),  # Dia do Trabalho
    date(2024, 5, 30),  # Corpus Christi
    date(2024, 9, 7),  # Independencia (sabado)
    date(2024, 10, 12),  # Aparecida (sabado)
    date(2024, 11, 2),  # Finados (sabado)
    date(2024, 11, 15),  # Proclamacao da Republica
    date(2024, 11, 20),  # Consciencia Negra (1o ano como feriado nacional)
    date(2024, 12, 24),  # B3 fechada
    date(2024, 12, 25),  # Natal
    date(2024, 12, 31),  # B3 fechada
}

FERIADOS_2025 = {
    date(2025, 1, 1),
    date(2025, 3, 3),  # carnaval (segunda)
    date(2025, 3, 4),  # carnaval (terca)
    date(2025, 4, 18),  # Sexta-feira Santa
    date(2025, 4, 21),  # Tiradentes
    date(2025, 5, 1),
    date(2025, 6, 19),  # Corpus Christi
    date(2025, 9, 7),  # domingo
    date(2025, 10, 12),  # domingo
    date(2025, 11, 2),  # domingo
    date(2025, 11, 15),  # sabado
    date(2025, 11, 20),
    date(2025, 12, 24),
    date(2025, 12, 25),
    date(2025, 12, 31),
}

FERIADOS_2026 = {
    date(2026, 1, 1),
    date(2026, 2, 16),  # carnaval (segunda)
    date(2026, 2, 17),  # carnaval (terca)
    date(2026, 4, 3),  # Sexta-feira Santa
    date(2026, 4, 21),  # Tiradentes
    date(2026, 5, 1),
    date(2026, 6, 4),  # Corpus Christi
    date(2026, 9, 7),
    date(2026, 10, 12),
    date(2026, 11, 2),
    date(2026, 11, 15),  # domingo
    date(2026, 11, 20),
    date(2026, 12, 24),
    date(2026, 12, 25),
    date(2026, 12, 31),
}


@pytest.mark.parametrize(
    ("year", "esperados"),
    [(2024, FERIADOS_2024), (2025, FERIADOS_2025), (2026, FERIADOS_2026)],
)
def test_feriados_do_ano_batem_exatamente(year: int, esperados: set[date]) -> None:
    assert holidays(year) == esperados


@pytest.mark.parametrize(
    ("year", "esperado"),
    [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5))],
)
def test_pascoa(year: int, esperado: date) -> None:
    assert easter(year) == esperado


def test_datas_moveis_de_2026_batem_com_o_comunicado_da_b3() -> None:
    # A B3 anunciou: carnaval em 16 e 17/02, Cinzas em 18/02 com abertura as 13h.
    assert carnival_monday(2026) == date(2026, 2, 16)
    assert carnival_tuesday(2026) == date(2026, 2, 17)
    assert ash_wednesday(2026) == date(2026, 2, 18)
    assert good_friday(2026) == date(2026, 4, 3)
    assert corpus_christi(2026) == date(2026, 6, 4)


@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_quarta_de_cinzas_e_pregao(year: int) -> None:
    # Horario reduzido nao suprime a barra diaria.
    assert is_trading_day(ash_wednesday(year))


@pytest.mark.parametrize(
    "dia",
    [
        date(2024, 1, 25),  # aniversario de Sao Paulo (quinta)
        date(2024, 7, 9),  # Revolucao Constitucionalista (terca)
        date(2025, 7, 9),  # (quarta)
        date(2026, 7, 9),  # (quinta)
    ],
)
def test_feriado_estadual_ou_municipal_de_sp_e_dia_de_pregao(dia: date) -> None:
    # Desde 2022 a B3 so para em feriado nacional.
    assert is_trading_day(dia)


def test_consciencia_negra_so_e_feriado_a_partir_de_2024() -> None:
    assert date(2023, 11, 20) not in holidays(2023)
    assert date(2024, 11, 20) in holidays(2024)
    assert is_trading_day(date(2023, 11, 20))
    assert not is_trading_day(date(2024, 11, 20))


def test_ano_anterior_a_politica_atual_falha_alto() -> None:
    # Ate 2021 a B3 parava em feriado municipal: devolver calendario errado
    # em silencio seria pior do que recusar.
    with pytest.raises(UnsupportedYearError):
        holidays(2021)
    with pytest.raises(UnsupportedYearError):
        is_trading_day(date(2021, 6, 10))


@pytest.mark.parametrize("dia", [date(2025, 6, 21), date(2025, 6, 22)])
def test_fim_de_semana_nunca_e_pregao(dia: date) -> None:
    assert not is_trading_day(dia)


def test_virada_de_ano_pula_24_25_31_e_1o() -> None:
    # 24, 25 e 31/12/2024 fechados; 01/01/2025 feriado. Sobram 30/12 e 02/01.
    assert previous_trading_day(date(2025, 1, 1)) == date(2024, 12, 30)
    assert next_trading_day(date(2024, 12, 31)) == date(2025, 1, 2)


def test_inclusive_respeita_se_o_dia_e_pregao() -> None:
    util = date(2025, 6, 18)
    assert previous_trading_day(util, inclusive=True) == util
    assert next_trading_day(util, inclusive=True) == util
    # 25/12/2025 e feriado: `inclusive` nao pode devolver um dia sem pregao.
    assert previous_trading_day(date(2025, 12, 25), inclusive=True) == date(2025, 12, 23)
    assert next_trading_day(date(2025, 12, 25), inclusive=True) == date(2025, 12, 26)


def test_sessions_before_olha_so_para_tras() -> None:
    dia = date(2025, 6, 18)
    janela = sessions_before(dia, 30)
    assert len(janela) == 30
    assert janela == sorted(janela)
    assert dia not in janela
    assert all(d < dia for d in janela)
    assert all(is_trading_day(d) for d in janela)


def test_sessions_before_inclusive_a_partir_de_feriado() -> None:
    # 25/12/2025 nao e pregao: a janela inclusiva comeca no pregao anterior.
    janela = sessions_before(date(2025, 12, 25), 3, inclusive=True)
    assert janela[-1] == date(2025, 12, 23)
    assert len(janela) == 3


def test_sessions_before_zero_e_lista_vazia() -> None:
    assert sessions_before(date(2025, 6, 18), 0) == []


def test_trading_days_intervalo_invertido_falha() -> None:
    with pytest.raises(ValueError, match="invertido"):
        trading_days(date(2025, 6, 18), date(2025, 6, 17))


@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_quantidade_de_pregoes_no_ano_e_plausivel(year: int) -> None:
    total = len(trading_days(date(year, 1, 1), date(year, 12, 31)))
    assert 240 <= total <= 252, total


def test_pregoes_do_ano_excluem_todos_os_feriados() -> None:
    sessoes = set(trading_days(date(2025, 1, 1), date(2025, 12, 31)))
    assert sessoes.isdisjoint(holidays(2025))


@pytest.mark.db
def test_calendario_bate_com_os_pregoes_reais_do_cotahist(working_engine: Engine) -> None:
    """O gabarito definitivo: os pregoes que a B3 de fato publicou.

    Pula se o banco nao tiver carga. Com os dados de 2024-2026 carregados, a
    checagem cobre mais de 600 pregoes reais.
    """
    from sqlalchemy import text as sql

    with working_engine.connect() as conn:
        reais = {
            row[0]
            for row in conn.execute(
                sql("SELECT DISTINCT trade_date FROM volume_scanner.daily_bars")
            )
        }
    if len(reais) < 200:
        pytest.skip("sem carga suficiente; rode scanner ingest backfill --start 2024-01-01")

    calculados = set(trading_days(min(reais), max(reais)))
    assert calculados - reais == set(), "calendario diz pregao mas a B3 nao publicou"
    assert reais - calculados == set(), "a B3 publicou pregao que o calendario chama de feriado"
