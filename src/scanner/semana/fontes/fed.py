"""Dot plot do Fed: a mediana projetada da taxa de juros, por ano.

A tabela de projecoes (Summary of Economic Projections) sai 4 vezes por ano,
nas reunioes de marco, junho, setembro e dezembro. A edicao valida para uma
semana e a mais nova com data <= sexta: usar uma posterior seria usar uma
projecao que ainda nao existia naquela semana.

A linha "Federal funds rate" fica sob "Memo: Projected appropriate policy
path". As colunas sao lidas pelo atributo `headers` de cada celula, e nao pela
posicao: as linhas "June projection" tem celulas vazias no meio (2029 ausente,
medido na tabela de 16/09/2026), e contar posicoes deslocaria os anos.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any

import httpx

from scanner.semana.fontes import FonteIndisponivelError, baixar
from scanner.semana.periodo import Semana

FONTE = "fed"
URL_CALENDARIO = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
URL_PROJECAO = "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl{data}.htm"
_LINK = re.compile(r"fomcprojtabl(\d{8})\.htm")
LINHA = "Federal funds rate"


class _PrimeiraTabela(HTMLParser):
    """Linhas de celulas da PRIMEIRA <table>: [{tag, id, headers, texto}]."""

    def __init__(self) -> None:
        super().__init__()
        self.linhas: list[list[dict[str, str]]] = []
        self._tabelas = 0
        self._dentro = False
        self._celula: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._tabelas += 1
            self._dentro = self._tabelas == 1
        elif not self._dentro:
            return
        elif tag == "tr":
            self.linhas.append([])
        elif tag in ("th", "td") and self.linhas:
            valores = {k: (v or "") for k, v in attrs}
            self._celula = {
                "tag": tag,
                "id": valores.get("id", ""),
                "headers": valores.get("headers", ""),
                "texto": "",
            }

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._dentro:
            self._dentro = False
        elif tag in ("th", "td") and self._celula is not None:
            self.linhas[-1].append(self._celula)
            self._celula = None

    def handle_data(self, data: str) -> None:
        if self._celula is not None:
            self._celula["texto"] += data


def _texto(celula: dict[str, str]) -> str:
    return " ".join(celula["texto"].split())


def edicao_valida(calendario_html: str, sexta: date) -> date:
    """A maior data de projecao <= `sexta` entre as que o calendario do Fed lista."""
    datas: set[date] = set()
    for achado in _LINK.findall(calendario_html):
        datas.add(datetime.strptime(achado, "%Y%m%d").date())
    validas = [d for d in datas if d <= sexta]
    if not validas:
        raise FonteIndisponivelError(FONTE, f"nenhuma edicao de projecoes ate {sexta.isoformat()}")
    return max(validas)


def ler_projecao(html: str, data: date) -> dict[str, Any]:
    """As medianas da taxa de juros projetadas, por ano e de longo prazo."""
    parser = _PrimeiraTabela()
    parser.feed(html)
    linhas = parser.linhas

    grupo = next(
        (
            c["id"]
            for linha in linhas
            for c in linha
            if c["tag"] == "th" and c["id"] and _texto(c).startswith("Median")
        ),
        None,
    )
    if grupo is None:
        raise FonteIndisponivelError(FONTE, "cabecalho 'Median' ausente na tabela")
    colunas = {
        c["id"]: _texto(c)
        for linha in linhas
        for c in linha
        if c["tag"] == "th" and c["id"] and c["headers"].split()[:1] == [grupo]
    }

    alvo = next(
        (
            linha
            for linha in linhas
            if linha and linha[0]["tag"] == "th" and _texto(linha[0]) == LINHA
        ),
        None,
    )
    if alvo is None:
        raise FonteIndisponivelError(FONTE, f"linha {LINHA!r} ausente na tabela")

    medianas: list[dict[str, Any]] = []
    for celula in alvo[1:]:
        ids = celula["headers"].split()
        if celula["tag"] != "td" or len(ids) < 2 or ids[0] != grupo or ids[1] not in colunas:
            continue
        rotulo = colunas[ids[1]]
        try:
            taxa = float(_texto(celula))
        except ValueError as exc:
            raise FonteIndisponivelError(FONTE, f"mediana ilegivel: {_texto(celula)!r}") from exc
        periodo = "longo prazo" if rotulo.lower().startswith("longer run") else rotulo
        medianas.append({"periodo": periodo, "taxa": taxa})
    if not medianas:
        raise FonteIndisponivelError(FONTE, f"linha {LINHA!r} sem medianas")
    return {"data_projecao": data.isoformat(), "medianas": medianas}


def dot_plot(semana: Semana, *, cliente: httpx.Client | None = None) -> dict[str, Any]:
    """A edicao das projecoes valida para a semana e suas medianas de juros."""
    calendario = baixar(FONTE, URL_CALENDARIO, cliente=cliente).text
    data = edicao_valida(calendario, semana.sexta)
    pagina = baixar(FONTE, URL_PROJECAO.format(data=data.strftime("%Y%m%d")), cliente=cliente)
    return ler_projecao(pagina.text, data)
