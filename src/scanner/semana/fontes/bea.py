"""Agenda do BEA: PIB e PCE dos EUA.

A pagina `bea.gov/news/schedule/full` tem uma tabela cujo cabecalho diz "Year
2026"; cada linha tem o dia ("October 29"), a hora ("8:30 AM", ausente em
algumas) e o titulo. Entram so os releases NACIONAIS: o titulo comeca com
"GDP (" ou "Gross Domestic Product,". Os de recorte ("Gross Domestic Product by
State...", "GDP by County...") nao comecam assim, de proposito.

O ano vem do cabecalho. Se a semana cair num ano que a pagina nao tem, o aviso
diz isso em vez de devolver uma agenda vazia que pareceria "sem evento".
"""

from __future__ import annotations

import re
from datetime import date, time

import httpx

from scanner.semana.eventos import FUSO_NOVA_YORK, Evento, em_brasilia
from scanner.semana.fontes import FonteIndisponivelError, baixar

FONTE = "bea"
URL = "https://www.bea.gov/news/schedule/full"

_ANO = re.compile(r"Year (\d{4})</th>")
_LINHA = re.compile(r'<tr class="scheduled-releases-type[^"]*">(.*?)</tr>', re.S)
_DIA = re.compile(r'release-date">\s*([A-Za-z]+) (\d{1,2})\s*</div>')
_HORA = re.compile(r'<small class="text-muted">\s*(\d{1,2}):(\d{2}) ([AP])M\s*</small>')
_TITULO = re.compile(r"release-title[^>]*>\s*([^<]+)")
_MESES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)


def _nacional(titulo: str) -> str | None:
    """Nome do evento, ou None se o release nao interessa."""
    if titulo.startswith(("GDP (", "Gross Domestic Product,")):
        return "PIB dos EUA"
    if titulo.startswith("Personal Income and Outlays"):
        return "PCE (renda e gastos pessoais)"
    return None


def ler_agenda(html: str, inicio: date, fim: date) -> tuple[list[Evento], list[str]]:
    """Os releases do BEA dentro de [inicio, fim] e os avisos de cobertura."""
    ano_m = _ANO.search(html)
    if ano_m is None:
        raise FonteIndisponivelError(FONTE, "cabecalho 'Year AAAA' ausente")
    ano = int(ano_m.group(1))
    anos_da_semana = sorted({inicio.year, fim.year})
    avisos = [f"agenda do BEA sem {a}" for a in anos_da_semana if a != ano]

    eventos: list[Evento] = []
    for bloco in _LINHA.findall(html):
        titulo_m = _TITULO.search(bloco)
        dia_m = _DIA.search(bloco)
        if titulo_m is None or dia_m is None:
            continue
        titulo = " ".join(titulo_m.group(1).split())
        nome = _nacional(titulo)
        if nome is None:
            continue
        try:
            dia = date(ano, _MESES.index(dia_m.group(1).lower()) + 1, int(dia_m.group(2)))
        except ValueError as exc:
            raise FonteIndisponivelError(FONTE, f"data ilegivel: {dia_m.group(0)!r}") from exc
        hora_m = _HORA.search(bloco)
        if hora_m is None:
            data, hora = dia, None
        else:
            h = int(hora_m.group(1)) % 12 + (12 if hora_m.group(3) == "P" else 0)
            data, hora = em_brasilia(dia, time(h, int(hora_m.group(2))), FUSO_NOVA_YORK)
        if inicio <= data <= fim:
            eventos.append(Evento(data, hora, "EUA", nome, titulo, "BEA"))
    return eventos, avisos


def eventos(
    inicio: date, fim: date, *, cliente: httpx.Client | None = None
) -> tuple[list[Evento], list[str]]:
    return ler_agenda(baixar(FONTE, URL, cliente=cliente).text, inicio, fim)
