"""Data de resultado de um ADR, pela API da Nasdaq (Zacks).

`data.reportText` vem em dois formatos (medidos em 17/10/2026):

- CONFIRMADO: "... is expected* to report earnings on  10/22/2026 after market
  close.  The report will be for the fiscal Quarter ending Sep 2026. ..." (as
  vezes "before market open", as vezes sem a expressao de horario);
- ESTIMADO: "... is estimated to report earnings on  10/29/2026. The upcoming
  earnings date is derived from an algorithm based on a company's historical
  reporting dates. ..." -- uma conta em cima do historico, nao um anuncio da
  empresa. Nao entra: a lista de "confirmados" so tem o que a empresa anunciou.

Um texto que nao e nem um nem outro levanta erro: formato novo nao pode virar
"sem balanco na semana".
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, NamedTuple

import httpx

from scanner.semana.fontes import FonteIndisponivelError, baixar

FONTE = "nasdaq"
URL = "https://api.nasdaq.com/api/analyst/{adr}/earnings-date"

_CONFIRMADO = re.compile(
    r"is expected\*? to report earnings on\s+(\d{2}/\d{2}/\d{4})"
    r"(?:\s+(after market close|before market open))?",
    re.I,
)
_ESTIMADO = re.compile(r"is estimated to report earnings on", re.I)
# Sem data nenhuma: o texto e outro ("Our vendor, Zacks Investment Research, hasn't
# provided us with the upcoming earnings date ..."), medido em 17/10/2026 para
# BSBR e AZUL. Nao ha o que confirmar, e nao e falha da fonte.
_SEM_DATA = re.compile(r"hasn't provided us with the upcoming earn", re.I)
_TRIMESTRE = re.compile(r"fiscal Quarter ending\s+([A-Za-z]{3} \d{4})", re.I)
_HORARIOS = {"after market close": "após o fechamento", "before market open": "antes da abertura"}
# "Sep 2026" vira "3T26", o mesmo rotulo dos provaveis ("ITR 3T25"). Exercicio
# fiscal que nao fecha em trimestre civil fica como veio.
_TRIMESTRE_CIVIL = {"MAR": "1T", "JUN": "2T", "SEP": "3T", "DEC": "4T"}


def rotulo_do_trimestre(bruto: str) -> str:
    """'Sep 2026' -> '3T26'; o que nao for fim de trimestre civil fica como veio."""
    mes, _, ano = bruto.partition(" ")
    prefixo = _TRIMESTRE_CIVIL.get(mes.upper())
    return f"{prefixo}{ano[-2:]}" if prefixo and len(ano) == 4 else bruto


class DataConfirmada(NamedTuple):
    data: date
    horario: str | None
    trimestre: str | None


def ler_data(dados: Any) -> DataConfirmada | None:
    """A data confirmada pela empresa, ou None se a Nasdaq so tem estimativa."""
    try:
        texto = dados["data"]["reportText"]
    except (KeyError, TypeError) as exc:
        raise FonteIndisponivelError(FONTE, "formato inesperado (sem data.reportText)") from exc
    if not isinstance(texto, str):
        raise FonteIndisponivelError(FONTE, "formato inesperado (reportText nao e texto)")
    confirmado = _CONFIRMADO.search(texto)
    if confirmado is None:
        if _ESTIMADO.search(texto) or _SEM_DATA.search(texto):
            return None
        raise FonteIndisponivelError(FONTE, f"texto desconhecido: {texto[:80]!r}")
    dia = datetime.strptime(confirmado.group(1), "%m/%d/%Y").date()
    horario = confirmado.group(2)
    trimestre = _TRIMESTRE.search(texto)
    return DataConfirmada(
        dia,
        _HORARIOS[horario.lower()] if horario else None,
        rotulo_do_trimestre(trimestre.group(1)) if trimestre else None,
    )


def data_do_adr(adr: str, *, cliente: httpx.Client | None = None) -> DataConfirmada | None:
    resposta = baixar(FONTE, URL.format(adr=adr), cliente=cliente)
    try:
        dados = resposta.json()
    except ValueError as exc:
        raise FonteIndisponivelError(FONTE, f"{adr}: resposta nao e JSON") from exc
    return ler_data(dados)
