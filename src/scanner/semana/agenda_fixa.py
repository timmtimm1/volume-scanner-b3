"""Agenda fixa: Copom e BLS (CPI e payroll), lida de `agenda_fixa.yaml`.

As duas fontes nao se leem por maquina: o bls.gov responde 403 a qualquer cliente
automatizado e a pagina do calendario do Copom e montada por JavaScript (ambos
medidos em 17/10/2026). As datas ficam num YAML versionado, revisavel, com a
origem escrita no topo. Quando a semana seguinte passa da ultima data coberta,
o aviso diz qual arquivo atualizar: dado velho nao pode parecer "sem evento".
"""

from __future__ import annotations

from datetime import date, time
from functools import lru_cache
from importlib.resources import files
from typing import Any

import yaml

from scanner.semana.eventos import (
    FUSO_NOVA_YORK,
    Evento,
    PedidoFocus,
    em_brasilia,
    mes_por_extenso,
)

ARQUIVO = "src/scanner/semana/agenda_fixa.yaml"
HORA_DECISAO_COPOM = time(18, 30)
HORA_ATA_COPOM = time(8, 0)
HORA_BLS = time(8, 30)  # Nova York


@lru_cache(maxsize=1)
def carregar() -> dict[str, Any]:
    texto = (files("scanner.semana") / "agenda_fixa.yaml").read_text(encoding="utf-8")
    dados = yaml.safe_load(texto)
    if not isinstance(dados, dict):
        raise ValueError("agenda_fixa.yaml: formato inesperado")
    return dados


def _referencia(texto: str, ano_do_evento: int) -> str:
    ano, mes = texto.split("-")
    return mes_por_extenso(int(ano), int(mes), ano_do_evento)


def _evento_bls(nome: str, item: dict[str, Any]) -> Evento:
    dia, hora = em_brasilia(item["data"], HORA_BLS, FUSO_NOVA_YORK)
    return Evento(
        data=dia,
        hora=hora,
        pais="EUA",
        evento=nome,
        detalhe=_referencia(item["referencia"], item["data"].year),
        fonte="BLS",
    )


def eventos_fixos(inicio: date, fim: date) -> tuple[list[Evento], list[str]]:
    """Os eventos da agenda fixa dentro de [inicio, fim] e os avisos de cobertura."""
    dados = carregar()
    eventos: list[Evento] = []
    avisos: list[str] = []

    copom: dict[int, list[dict[str, Any]]] = dados["copom"]
    for ano, reunioes in copom.items():
        for r in reunioes:
            rotulo = f"reunião {r['reuniao']}/{ano}"
            segundo_dia: date = r["dias"][1]
            if inicio <= segundo_dia <= fim:
                eventos.append(
                    Evento(
                        segundo_dia,
                        HORA_DECISAO_COPOM,
                        "BR",
                        "Copom: decisão",
                        rotulo,
                        "BC",
                        PedidoFocus("selic", f"R{r['reuniao']}/{ano}"),
                    )
                )
            ata: date = r["ata"]
            if inicio <= ata <= fim:
                eventos.append(Evento(ata, HORA_ATA_COPOM, "BR", "Copom: ata", rotulo, "BC"))
    ultimo_ano = max(copom)
    if fim.year > ultimo_ano:
        avisos.append(f"agenda fixa sem datas do Copom depois de {ultimo_ano}: atualizar {ARQUIVO}")

    for chave, nome, rotulo in (("cpi", "CPI", "CPI"), ("payroll", "Payroll", "payroll")):
        serie: list[dict[str, Any]] = dados["bls"][chave]
        for item in serie:
            # A data do YAML e a de Nova York; o filtro usa a de Brasilia, que
            # e a da agenda (nas horas de hoje elas coincidem, 08:30 NY = 10:30 ou 09:30).
            evento = _evento_bls(nome, item)
            if inicio <= evento.data <= fim:
                eventos.append(evento)
        ultima = max(item["data"] for item in serie)
        if fim > ultima:
            avisos.append(
                f"agenda fixa sem datas do {rotulo} depois de {ultima.isoformat()}: "
                f"atualizar {ARQUIVO}"
            )
    return eventos, avisos
