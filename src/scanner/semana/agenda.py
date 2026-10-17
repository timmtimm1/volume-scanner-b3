"""Agenda macro da semana seguinte: Brasil e EUA, de fontes independentes.

Cada fonte falha sozinha: a que cai vira um aviso e as outras seguem. A agenda
fixa (Copom, BLS) vem do YAML versionado; IBGE, Fed e BEA vem da rede; o consenso
do Focus e acrescentado depois, e a falha dele deixa `consenso: null` e um aviso.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx

from scanner.semana import agenda_fixa
from scanner.semana.eventos import Evento
from scanner.semana.fontes import FonteIndisponivelError, bea, focus, fomc, ibge

logger = logging.getLogger(__name__)


def _com_avisos(eventos: Any) -> tuple[list[Evento], list[str]]:
    """Normaliza o retorno das fontes: lista pura, ou (lista, avisos)."""
    if isinstance(eventos, tuple):
        lista, avisos = eventos
        return list(lista), list(avisos)
    return list(eventos), []


def _consensos(
    eventos: list[Evento], ate: date, cliente: httpx.Client | None
) -> tuple[dict[int, dict[str, Any] | None], list[str]]:
    """Consenso por posicao do evento. O Focus falhou uma vez, nao se insiste."""
    resultado: dict[int, dict[str, Any] | None] = {}
    for i, evento in enumerate(eventos):
        if evento.focus is None:
            continue
        try:
            resultado[i] = focus.consenso(
                evento.focus.indicador, evento.focus.chave, ate, cliente=cliente
            )
        except FonteIndisponivelError as exc:
            logger.warning("[semana] focus indisponivel: %s", exc)
            return resultado, [f"Focus indisponível ({exc.motivo}): eventos sem consenso"]
    return resultado, []


def montar_agenda(
    inicio: date,
    fim: date,
    *,
    focus_ate: date,
    cliente: httpx.Client | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """(eventos ordenados, avisos) para [inicio, fim]; `focus_ate` e o limite do Focus."""
    eventos: list[Evento] = []
    avisos: list[str] = []

    fontes: list[tuple[str, Callable[[], Any]]] = [
        ("agenda fixa", lambda: agenda_fixa.eventos_fixos(inicio, fim)),
        ("IBGE", lambda: ibge.eventos(inicio, fim, cliente=cliente)),
        ("FOMC", lambda: fomc.eventos(inicio, fim, cliente=cliente)),
        ("BEA", lambda: bea.eventos(inicio, fim, cliente=cliente)),
    ]
    for nome, busca in fontes:
        try:
            achados, extras = _com_avisos(busca())
        except FonteIndisponivelError as exc:
            logger.warning("[semana] agenda %s indisponivel: %s", nome, exc)
            avisos.append(f"agenda {nome} indisponível: {exc.motivo}")
            continue
        eventos += achados
        avisos += extras

    eventos.sort(key=lambda e: e.chave_de_ordem())
    consensos, avisos_focus = _consensos(eventos, focus_ate, cliente)
    avisos += avisos_focus
    return [e.como_dict(consensos.get(i)) for i, e in enumerate(eventos)], avisos
