"""Calendario do FOMC, lido da pagina do Fed.

A pagina tem um painel por ano ("2026 FOMC Meetings"), e cada reuniao tem o mes
(`fomc-meeting__month`) e os dias (`fomc-meeting__date`, "27-28" ou "17-18*").
O asterisco marca a reuniao com projecoes (dot plot). O parse e feito POR
PAINEL: o texto depois de "2026 FOMC Meetings" continua no painel de 2025, e
sem delimitar cada ano as reunioes de um ano cairiam no outro.

Casos reais da pagina (medidos em 17/10/2026): reuniao que atravessa o mes
mostra "Apr/May" com "30-1"; e as votacoes sem reuniao aparecem como
"22 (notation vote)", que nao e reuniao e e ignorada.
"""

from __future__ import annotations

import re
from datetime import date, time

import httpx

from scanner.semana.eventos import FUSO_NOVA_YORK, Evento, em_brasilia
from scanner.semana.fontes import FonteIndisponivelError, baixar

FONTE = "fed"
URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
HORA_DECISAO = time(14, 0)  # Nova York

_PAINEL = re.compile(r"(\d{4}) FOMC Meetings</a>")
_REUNIAO = re.compile(
    r'fomc-meeting__month[^"]*"><strong>([^<]+)</strong></div>\s*'
    r'<div class="fomc-meeting__date[^"]*">\s*([^<]*?)\s*</div>'
)
_DIAS = re.compile(r"^(\d{1,2})-(\d{1,2})(\*?)$")
_MESES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def _mes(texto: str) -> int:
    try:
        return _MESES.index(texto.strip()[:3].lower()) + 1
    except ValueError as exc:
        raise FonteIndisponivelError(FONTE, f"mes ilegivel: {texto!r}") from exc


def reunioes(html: str) -> list[tuple[date, bool]]:
    """[(ultimo dia da reuniao, tem projecoes)] de todos os paineis de ano."""
    achados = list(_PAINEL.finditer(html))
    if not achados:
        raise FonteIndisponivelError(FONTE, "nenhum painel 'FOMC Meetings' na pagina")
    resultado: list[tuple[date, bool]] = []
    for i, painel in enumerate(achados):
        ano = int(painel.group(1))
        fim_do_painel = achados[i + 1].start() if i + 1 < len(achados) else len(html)
        for mes_txt, dias_txt in _REUNIAO.findall(html[painel.end() : fim_do_painel]):
            dias = _DIAS.match(dias_txt)
            if dias is None:
                continue
            meses = [_mes(m) for m in mes_txt.split("/")]
            resultado.append((date(ano, meses[-1], int(dias.group(2))), dias.group(3) == "*"))
    return resultado


def ler_eventos(html: str, inicio: date, fim: date) -> tuple[list[Evento], list[str]]:
    """Os FOMC dentro de [inicio, fim] e o aviso se a pagina nao cobre o ano."""
    todas = reunioes(html)
    anos = {dia.year for dia, _ in todas}
    avisos = [
        f"calendário do FOMC sem {ano}"
        for ano in sorted({inicio.year, fim.year})
        if ano not in anos
    ]
    eventos: list[Evento] = []
    for dia, projecoes in todas:
        if not inicio <= dia <= fim:
            continue
        data, hora = em_brasilia(dia, HORA_DECISAO, FUSO_NOVA_YORK)
        eventos.append(
            Evento(
                data, hora, "EUA", "FOMC: decisão", "com projeções" if projecoes else None, "Fed"
            )
        )
    return eventos, avisos


def eventos(
    inicio: date, fim: date, *, cliente: httpx.Client | None = None
) -> tuple[list[Evento], list[str]]:
    return ler_eventos(baixar(FONTE, URL, cliente=cliente).text, inicio, fim)
