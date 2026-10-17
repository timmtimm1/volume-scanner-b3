"""O evento da agenda macro, comum a todas as fontes, e as contas de data e hora.

`hora` sai sempre em horario de Brasilia (America/Sao_Paulo). As fontes dos EUA
publicam em Nova York, e o horario de verao dos EUA e o do Brasil nao mudam no
mesmo dia (o Brasil nao tem mais horario de verao desde 2019): a conversao tem
que passar pelo fuso, nunca por uma diferenca fixa de horas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")
FUSO_NOVA_YORK = ZoneInfo("America/New_York")
FUSO_UTC = ZoneInfo("UTC")

MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


@dataclass(frozen=True)
class PedidoFocus:
    """O consenso que o Focus pode dar a um evento."""

    indicador: str  # "selic" (reuniao do Copom) ou "ipca" (mes de referencia)
    chave: str  # "R7/2026" ou "10/2026"


@dataclass(frozen=True)
class Evento:
    data: date
    hora: time | None
    pais: str
    evento: str
    detalhe: str | None
    fonte: str
    focus: PedidoFocus | None = None

    def chave_de_ordem(self) -> tuple[date, bool, time, str, str]:
        """Data, hora (sem hora por ultimo no dia), pais, nome."""
        return (self.data, self.hora is None, self.hora or time(0), self.pais, self.evento)

    def como_dict(self, consenso: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "data": self.data.isoformat(),
            "hora": None if self.hora is None else self.hora.strftime("%H:%M"),
            "pais": self.pais,
            "evento": self.evento,
            "detalhe": self.detalhe,
            "consenso": consenso,
            "fonte": self.fonte,
        }


def em_brasilia(dia: date, hora: time, fuso: ZoneInfo) -> tuple[date, time]:
    """Data e hora de parede em `fuso` -> data e hora de Brasilia."""
    local = datetime.combine(dia, hora, tzinfo=fuso).astimezone(FUSO_BRASILIA)
    return local.date(), local.time().replace(second=0, microsecond=0)


def mes_por_extenso(ano: int, mes: int, ano_do_evento: int) -> str:
    """'outubro'; com o ano ('dezembro de 2025') quando nao e o do evento."""
    nome = MESES[mes - 1]
    return nome if ano == ano_do_evento else f"{nome} de {ano}"
