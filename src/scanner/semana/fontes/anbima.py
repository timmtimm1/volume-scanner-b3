"""Curva de juros prefixada (ETTJ) da ANBIMA.

O download e um POST de formulario que devolve CSV em latin-1. A primeira
celula da primeira linha e a data da curva: a ANBIMA nao devolve erro para data
sem curva (fim de semana, feriado), devolve corpo vazio ou outra data, e uma
taxa de outro dia mostrada como da semana seria um erro silencioso. Por isso a
data devolvida e conferida contra a pedida.

Vertices em dias uteis, com separador de milhar ("2.520"). A coluna usada e a
`ETTJ PREF` (% a.a.).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx

from scanner.semana.fontes import FonteIndisponivelError, baixar
from scanner.semana.periodo import Semana

FONTE = "anbima"
URL = "https://www.anbima.com.br/informacoes/est-termo/CZ-down.asp"
DIAS_UTEIS_POR_ANO = 252


def ler_curva(texto: str) -> tuple[date, dict[int, float]]:
    """(data da curva, {vertice em dias uteis: taxa prefixada em % a.a.})."""
    linhas = texto.replace("\r\n", "\n").split("\n")
    primeira = linhas[0].split(";")[0].strip() if linhas else ""
    try:
        data = datetime.strptime(primeira, "%d/%m/%Y").date()
    except ValueError as exc:
        raise FonteIndisponivelError(FONTE, f"1a celula nao e data: {primeira[:40]!r}") from exc

    cabecalho = next((i for i, linha in enumerate(linhas) if linha.startswith("Vertices;")), None)
    if cabecalho is None:
        raise FonteIndisponivelError(FONTE, "tabela ETTJ ausente (sem linha 'Vertices;')")
    colunas = [c.strip() for c in linhas[cabecalho].split(";")]
    if "ETTJ PREF" not in colunas:
        raise FonteIndisponivelError(FONTE, f"coluna ETTJ PREF ausente em {colunas}")
    indice = colunas.index("ETTJ PREF")

    curva: dict[int, float] = {}
    for linha in linhas[cabecalho + 1 :]:
        if not linha.strip():
            break
        celulas = linha.split(";")
        try:
            vertice = int(celulas[0].replace(".", ""))
        except ValueError as exc:
            raise FonteIndisponivelError(FONTE, f"vertice ilegivel: {celulas[0]!r}") from exc
        # Vertices longos do IPCA nao tem prefixado: celula vazia, sem ponto.
        if len(celulas) > indice and celulas[indice].strip():
            curva[vertice] = float(celulas[indice].replace(",", "."))
    if not curva:
        raise FonteIndisponivelError(FONTE, "curva prefixada sem nenhum vertice")
    return data, curva


def buscar_curva(dia: date, *, cliente: httpx.Client | None = None) -> dict[int, float]:
    """Baixa a curva de `dia` e confere que a data devolvida e a pedida."""
    resposta = baixar(
        FONTE,
        URL,
        cliente=cliente,
        metodo="POST",
        data={"Idioma": "PT", "Dt_Ref": dia.strftime("%d/%m/%Y"), "saida": "csv"},
    )
    data, curva = ler_curva(resposta.content.decode("latin-1"))
    if data != dia:
        raise FonteIndisponivelError(FONTE, f"pedi {dia.isoformat()} e veio {data.isoformat()}")
    return curva


def montar_curva(
    fim: date,
    inicio: date,
    curva_fim: dict[int, float],
    curva_inicio: dict[int, float],
    vertices_du: list[int],
) -> dict[str, Any]:
    """Os vertices pedidos, com a taxa do fim, a da base e a variacao em pontos-base."""
    linhas: list[dict[str, Any]] = []
    for du in vertices_du:
        if du not in curva_fim:
            raise FonteIndisponivelError(FONTE, f"vertice {du} ausente na curva de {fim}")
        taxa = curva_fim[du]
        anterior = curva_inicio.get(du)
        linhas.append(
            {
                "du": du,
                "anos": du / DIAS_UTEIS_POR_ANO,
                "taxa": taxa,
                "taxa_anterior": anterior,
                "variacao_bp": None if anterior is None else (taxa - anterior) * 100,
            }
        )
    return {"data": fim.isoformat(), "data_anterior": inicio.isoformat(), "vertices": linhas}


def curva_prefixada(
    semana: Semana, vertices_du: list[int], *, cliente: httpx.Client | None = None
) -> dict[str, Any]:
    """A curva prefixada do ultimo pregao da semana contra a do pregao-base."""
    curva_fim = buscar_curva(semana.fim, cliente=cliente)
    curva_inicio = buscar_curva(semana.inicio, cliente=cliente)
    return montar_curva(semana.fim, semana.inicio, curva_fim, curva_inicio, vertices_du)
