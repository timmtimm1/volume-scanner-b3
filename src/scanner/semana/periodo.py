"""A semana de pregao: de segunda a sexta, com a base no pregao anterior.

A semana e identificada pela SEXTA-FEIRA nominal, mesmo quando ela e feriado:
e o nome que o usuario reconhece ("semana de 16/10") e nao muda quando o ultimo
pregao muda. Na Sexta-feira Santa de 2026 (03/04) a semana e a de 03/04, mas o
ultimo pregao e quinta, 02/04.

A variacao da semana compara o ultimo pregao dela com o ultimo pregao ANTES da
segunda-feira (`inicio`): numa semana com segunda feriado (12/10/2026) a base e
sexta, 09/10, e nao o primeiro pregao da semana.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from scanner.calendar import previous_trading_day, trading_days


@dataclass(frozen=True)
class Semana:
    """Uma semana de pregao ja definida pelo calendario da B3."""

    sexta: date  # identificador: sexta nominal (mesmo se feriado)
    inicio: date  # base: ultimo pregao ANTES da segunda-feira da semana
    fim: date  # ultimo pregao entre segunda e sexta
    pregoes: tuple[date, ...]  # pregoes de segunda a sexta

    @property
    def segunda(self) -> date:
        """Segunda-feira da semana, pregao ou nao."""
        return self.sexta - timedelta(days=4)


class SemanaSemPregaoError(ValueError):
    """A semana nao teve nenhum pregao (nao existe hoje, mas o calendario permite)."""


def semana_da_data(dia: date) -> Semana:
    """A semana de `dia`. Segunda a sexta: a propria; sabado e domingo: a que acabou."""
    # weekday(): segunda=0 ... sexta=4, sabado=5, domingo=6. A diferenca para a
    # sexta e positiva na semana e negativa no fim de semana, e o mesmo
    # calculo serve aos dois casos.
    sexta = dia + timedelta(days=4 - dia.weekday())
    segunda = sexta - timedelta(days=4)

    pregoes = trading_days(segunda, sexta)
    if not pregoes:
        raise SemanaSemPregaoError(f"a semana de {sexta.isoformat()} nao teve pregao")
    return Semana(
        sexta=sexta,
        inicio=previous_trading_day(segunda),
        fim=pregoes[-1],
        pregoes=tuple(pregoes),
    )


def semana_encerrada(hoje: date) -> Semana:
    """A ultima semana que ja acabou.

    Sabado e domingo: a semana que terminou ontem. Segunda a sexta: a ANTERIOR,
    porque a atual ainda nao acabou (mesmo na sexta, depois do fechamento: o
    resumo sai com a semana fechada, sem depender do arquivo do dia).
    """
    if hoje.weekday() >= 5:
        return semana_da_data(hoje)
    domingo_anterior = hoje - timedelta(days=hoje.weekday() + 1)
    return semana_da_data(domingo_anterior)


def proxima_semana(semana: Semana) -> tuple[date, date]:
    """Segunda e sexta da semana SEGUINTE, contadas a partir da sexta nominal.

    Pela sexta nominal e nao por `fim`: na Sexta-feira Santa o `fim` e a quinta,
    e a semana seguinte continua comecando na segunda depois da sexta.
    """
    segunda = semana.sexta + timedelta(days=3)
    return segunda, segunda + timedelta(days=4)


def sextas(desde: date, ate: date) -> list[date]:
    """As sextas-feiras nominais de `desde` (a primeira que nao seja anterior) ate `ate`."""
    primeira = desde + timedelta(days=(4 - desde.weekday()) % 7)
    return [primeira + timedelta(days=7 * i) for i in range(((ate - primeira).days // 7) + 1)]
