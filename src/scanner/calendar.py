"""Calendario de pregoes da B3.

As datas moveis (carnaval, Sexta-feira Santa, Corpus Christi) sao derivadas da
Pascoa por algoritmo, nunca tabeladas: tabela de data movel envelhece em silencio.
As fixas e a politica de quais feriados a B3 observa vem das regras abaixo.

Politica vigente (verificada contra os comunicados da B3):

- Feriados nacionais fixos: 01/01, 21/04, 01/05, 07/09, 12/10, 02/11, 15/11, 25/12.
- 20/11 (Consciencia Negra) e feriado nacional a partir de 2024 (Lei 14.759/2023).
- 24/12 e 31/12: a B3 nao negocia, por conta do expediente interno dos bancos.
- Feriados estaduais e municipais de Sao Paulo (25/01 e 09/07) SAO dias de pregao:
  desde 2022 a B3 so para em feriado nacional.
- Quarta-feira de Cinzas E dia de pregao (abertura as 13h). Horario reduzido nao
  muda a existencia da barra diaria, que e o que este projeto consome.

A politica so vale de 2022 em diante. Antes disso a B3 parava em feriado municipal,
e devolver um calendario errado em silencio seria pior do que falhar.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

# Antes de 2022 a B3 ainda observava feriados municipais de Sao Paulo.
FIRST_SUPPORTED_YEAR = 2022

# 20/11 virou feriado nacional pela Lei 14.759/2023, valendo a partir de 2024.
BLACK_AWARENESS_FIRST_YEAR = 2024

FIXED_NATIONAL_HOLIDAYS: tuple[tuple[int, int], ...] = (
    (1, 1),  # Confraternizacao Universal
    (4, 21),  # Tiradentes
    (5, 1),  # Dia do Trabalho
    (9, 7),  # Independencia
    (10, 12),  # Nossa Senhora Aparecida
    (11, 2),  # Finados
    (11, 15),  # Proclamacao da Republica
    (12, 25),  # Natal
)

# Nao sao feriado legal, mas a B3 nao negocia (expediente interno dos bancos).
EXCHANGE_CLOSURES: tuple[tuple[int, int], ...] = (
    (12, 24),
    (12, 31),
)


class UnsupportedYearError(ValueError):
    """Ano fora da faixa em que a politica de feriados foi verificada."""


def _check_year(year: int) -> None:
    if year < FIRST_SUPPORTED_YEAR:
        raise UnsupportedYearError(
            f"calendario nao cobre {year}: a politica atual da B3 vale de "
            f"{FIRST_SUPPORTED_YEAR} em diante (antes disso havia feriado municipal)"
        )


def easter(year: int) -> date:
    """Domingo de Pascoa pelo algoritmo gregoriano anonimo (Meeus/Jones/Butler)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def carnival_monday(year: int) -> date:
    """Segunda-feira de carnaval: 48 dias antes da Pascoa."""
    return easter(year) - timedelta(days=48)


def carnival_tuesday(year: int) -> date:
    """Terca-feira de carnaval: 47 dias antes da Pascoa."""
    return easter(year) - timedelta(days=47)


def ash_wednesday(year: int) -> date:
    """Quarta-feira de Cinzas. E pregao, com abertura as 13h."""
    return easter(year) - timedelta(days=46)


def good_friday(year: int) -> date:
    """Sexta-feira Santa: 2 dias antes da Pascoa."""
    return easter(year) - timedelta(days=2)


def corpus_christi(year: int) -> date:
    """Corpus Christi: 60 dias depois da Pascoa."""
    return easter(year) + timedelta(days=60)


@lru_cache(maxsize=64)
def holidays(year: int) -> frozenset[date]:
    """Dias do ano em que a B3 nao negocia, excluindo fins de semana."""
    _check_year(year)

    days = {date(year, month, day) for month, day in FIXED_NATIONAL_HOLIDAYS}
    days |= {date(year, month, day) for month, day in EXCHANGE_CLOSURES}
    days |= {
        carnival_monday(year),
        carnival_tuesday(year),
        good_friday(year),
        corpus_christi(year),
    }
    if year >= BLACK_AWARENESS_FIRST_YEAR:
        days.add(date(year, 11, 20))
    return frozenset(days)


def is_holiday(day: date) -> bool:
    """True se a data e feriado de bolsa (independente de cair em fim de semana)."""
    return day in holidays(day.year)


def is_trading_day(day: date) -> bool:
    """True se houve pregao: dia util que nao e feriado de bolsa."""
    _check_year(day.year)
    return day.weekday() < 5 and day not in holidays(day.year)


def trading_days(start: date, end: date) -> list[date]:
    """Pregoes no intervalo fechado [start, end], em ordem crescente."""
    if end < start:
        raise ValueError(f"intervalo invertido: {start} > {end}")
    _check_year(start.year)
    _check_year(end.year)

    span = (end - start).days
    candidates = (start + timedelta(days=offset) for offset in range(span + 1))
    return [day for day in candidates if is_trading_day(day)]


def previous_trading_day(day: date, *, inclusive: bool = False) -> date:
    """Pregao imediatamente anterior a `day` (ou o proprio, se `inclusive`)."""
    current = day if inclusive else day - timedelta(days=1)
    # No maximo ~10 dias corridos separam dois pregoes (feriado emendado + fim de ano).
    for _ in range(15):
        if is_trading_day(current):
            return current
        current -= timedelta(days=1)
    raise UnsupportedYearError(f"nenhum pregao encontrado nos 15 dias anteriores a {day}")


def next_trading_day(day: date, *, inclusive: bool = False) -> date:
    """Proximo pregao a partir de `day` (ou o proprio, se `inclusive`)."""
    current = day if inclusive else day + timedelta(days=1)
    for _ in range(15):
        if is_trading_day(current):
            return current
        current += timedelta(days=1)
    raise UnsupportedYearError(f"nenhum pregao encontrado nos 15 dias seguintes a {day}")


def sessions_before(day: date, count: int, *, inclusive: bool = False) -> list[date]:
    """Os `count` pregoes anteriores a `day`, em ordem crescente.

    E o que a janela deslocada da secao 1 do plano precisa: o baseline olha para
    tras, e o dia avaliado nao entra, salvo pedido explicito.
    """
    if count < 0:
        raise ValueError("count nao pode ser negativo")

    result: list[date] = []
    # `inclusive` inclui o proprio dia so se ele for pregao; senao recua.
    current = previous_trading_day(day, inclusive=inclusive)
    while len(result) < count:
        result.append(current)
        current = previous_trading_day(current)
    result.reverse()
    return result
