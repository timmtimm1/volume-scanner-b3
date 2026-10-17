"""Calendario de divulgacoes do IBGE: IPCA, IPCA-15, PIB, PNAD, PMC e PIM-PF.

O horario da API vem em UTC: o IPCA-15 sai as 9h de Brasilia e a API diz
"12:00:00" (medido em 17/10/2026), entao a conversao para o fuso de Brasilia e
parte do parse. Os produtos entram pelo `produto_id`, nunca pelo nome: o nome
muda ("Divulgacao mensal#pnadc1", "PIM-PF Brasil#pimpf1").

O periodo de referencia sai dos campos `ano/mes_referencia_inicio/fim` da
propria API e nao de uma regra "mes anterior": medido em 17/10/2026, o IPCA de
12/11 diz referencia 10 (outubro), a PMC de 13/11 diz 9 (setembro, ~40 dias
antes) e o PIB de 02/12 diz meses 7 a 9 (3o trimestre). Campo 0 = a API nao disse
e o `detalhe` fica nulo, sem chute.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx

from scanner.semana.eventos import (
    FUSO_BRASILIA,
    FUSO_UTC,
    Evento,
    PedidoFocus,
    mes_por_extenso,
)
from scanner.semana.fontes import FonteIndisponivelError, baixar

FONTE = "ibge"
URL = "https://servicodados.ibge.gov.br/api/v3/calendario/?de={de}&ate={ate}&qtd=500"

IPCA = 9256
IPCA_15 = 9260
PIB = 9300
PNAD = 9171
PMC = 9227
PIM_PF = 9294
NOMES = {
    IPCA: "IPCA",
    IPCA_15: "IPCA-15",
    PIB: "PIB (trimestral)",
    PNAD: "Desemprego (PNAD Contínua)",
    PMC: "Varejo (PMC)",
    PIM_PF: "Produção industrial (PIM-PF)",
}


def _detalhe(produto: int, item: dict[str, Any], ano_do_evento: int) -> str | None:
    ano = int(item.get("ano_referencia_inicio") or 0)
    mes = int(item.get("mes_referencia_inicio") or 0)
    if ano == 0 or mes == 0:
        return None
    if produto == PIB:
        mes_fim = int(item.get("mes_referencia_fim") or 0)
        ano_fim = int(item.get("ano_referencia_fim") or 0)
        if mes_fim == 0 or ano_fim == 0:
            return None
        trimestre = f"{(mes_fim - 1) // 3 + 1}º trimestre"
        return trimestre if ano_fim == ano_do_evento else f"{trimestre} de {ano_fim}"
    nome = mes_por_extenso(ano, mes, ano_do_evento)
    if produto == PNAD:
        return f"trimestre até {nome}"
    return nome


def ler_calendario(dados: Any, inicio: date, fim: date) -> list[Evento]:
    """Os eventos dos produtos que interessam, com a data de Brasilia dentro de [inicio, fim]."""
    if not isinstance(dados, dict) or not isinstance(dados.get("items"), list):
        raise FonteIndisponivelError(FONTE, "formato inesperado (sem 'items')")
    eventos: list[Evento] = []
    for item in dados["items"]:
        try:
            produto = int(item["produto_id"])
            if produto not in NOMES:
                continue
            instante = datetime.strptime(item["data_divulgacao"], "%d/%m/%Y %H:%M:%S").replace(
                tzinfo=FUSO_UTC
            )
            local = instante.astimezone(FUSO_BRASILIA)
            if not inicio <= local.date() <= fim:
                continue
            detalhe = _detalhe(produto, item, local.year)
        except (KeyError, TypeError, ValueError) as exc:
            raise FonteIndisponivelError(FONTE, f"item ilegivel: {item!r}") from exc
        focus = None
        if produto == IPCA and detalhe is not None:
            ano, mes = int(item["ano_referencia_inicio"]), int(item["mes_referencia_inicio"])
            focus = PedidoFocus("ipca", f"{mes:02d}/{ano}")
        eventos.append(
            Evento(
                local.date(),
                local.time().replace(second=0),
                "BR",
                NOMES[produto],
                detalhe,
                "IBGE",
                focus,
            )
        )
    return eventos


def eventos(inicio: date, fim: date, *, cliente: httpx.Client | None = None) -> list[Evento]:
    # A API do IBGE pede MM-DD-AAAA. O filtro final e feito aqui, pela data de
    # Brasilia, depois da conversao do horario UTC.
    url = URL.format(de=inicio.strftime("%m-%d-%Y"), ate=fim.strftime("%m-%d-%Y"))
    resposta = baixar(FONTE, url, cliente=cliente)
    try:
        dados = resposta.json()
    except ValueError as exc:
        raise FonteIndisponivelError(FONTE, "resposta nao e JSON") from exc
    return ler_calendario(dados, inicio, fim)
