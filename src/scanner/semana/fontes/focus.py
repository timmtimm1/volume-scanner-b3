"""Consenso do Focus (BC): mediana da Selic por reuniao e do IPCA por mes.

Sempre `baseCalculo eq 0` (a base de 30 dias, a que o BC destaca) e a maior
`Data` <= a sexta da semana que acabou: o Focus que o mercado tinha na mao.
So Copom e IPCA: para IPCA-15, PIB, PNAD, PMC e PIM o Focus nao tem a serie, ou
a metrica nao e a da divulgacao, e inventar consenso seria pior que nao ter.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import quote

import httpx

from scanner.semana.fontes import FonteIndisponivelError, baixar

FONTE = "focus"
BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"
RECURSOS = {
    "selic": ("ExpectativasMercadoSelic", "Reuniao", "% a.a.", "Selic"),
    "ipca": ("ExpectativaMercadoMensais", "DataReferencia", "%", "IPCA"),
}


def url(indicador: str, chave: str, ate: date) -> str:
    recurso, campo, _unidade, _nome = RECURSOS[indicador]
    filtro = f"{campo} eq '{chave}' and baseCalculo eq 0 and Data le '{ate.isoformat()}'"
    if indicador == "ipca":
        filtro = f"Indicador eq 'IPCA' and {filtro}"
    ordem = quote("Data desc")
    return f"{BASE}/{recurso}?$top=1&$format=json&$orderby={ordem}&$filter={quote(filtro)}"


def ler_consenso(dados: Any, indicador: str) -> dict[str, Any] | None:
    """O consenso da linha mais recente, ou None se o Focus nao tem a serie."""
    if not isinstance(dados, dict) or not isinstance(dados.get("value"), list):
        raise FonteIndisponivelError(FONTE, "formato inesperado (sem 'value')")
    if not dados["value"]:
        return None
    linha = dados["value"][0]
    try:
        return {
            "mediana": float(linha["Mediana"]),
            "unidade": RECURSOS[indicador][2],
            "fonte": "Focus",
            "data": str(linha["Data"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise FonteIndisponivelError(FONTE, f"linha ilegivel: {linha!r}") from exc


def consenso(
    indicador: str, chave: str, ate: date, *, cliente: httpx.Client | None = None
) -> dict[str, Any] | None:
    resposta = baixar(FONTE, url(indicador, chave, ate), cliente=cliente)
    try:
        dados = resposta.json()
    except ValueError as exc:
        raise FonteIndisponivelError(FONTE, "resposta nao e JSON") from exc
    return ler_consenso(dados, indicador)
