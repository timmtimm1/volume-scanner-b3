"""Montagem da agenda: fontes reais recortadas atras de um transporte simulado."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx

from scanner.semana.agenda import montar_agenda

FIXTURES = Path(__file__).parent / "fixtures" / "semana"
SEXTA = date(2026, 10, 16)


def _cliente(**falhas: int) -> httpx.Client:
    def resposta(nome: str) -> httpx.Response:
        return httpx.Response(200, content=(FIXTURES / nome).read_bytes())

    def handler(req: httpx.Request) -> httpx.Response:
        host = req.url.host
        if host in falhas:
            return httpx.Response(falhas[host])
        if host == "servicodados.ibge.gov.br":
            return resposta("ibge_calendario.json")
        if host == "www.federalreserve.gov":
            return resposta("fed_fomc_calendario.htm")
        if host == "www.bea.gov":
            return resposta("bea_agenda.htm")
        if host == "olinda.bcb.gov.br":
            return resposta(
                "focus_selic_r7_2026.json" if "Selic" in req.url.path else "focus_ipca_10_2026.json"
            )
        raise AssertionError(f"host inesperado: {host}")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_semana_de_19_a_23_de_outubro() -> None:
    eventos, avisos = montar_agenda(
        date(2026, 10, 19), date(2026, 10, 23), focus_ate=SEXTA, cliente=_cliente()
    )

    assert avisos == []
    assert eventos == [
        {
            "data": "2026-10-23",
            "hora": "09:00",
            "pais": "BR",
            "evento": "IPCA-15",
            "detalhe": "outubro",
            "consenso": None,
            "fonte": "IBGE",
        }
    ]


def test_semana_de_2_a_6_de_novembro_ordenada_e_com_consenso() -> None:
    eventos, avisos = montar_agenda(
        date(2026, 11, 2), date(2026, 11, 6), focus_ate=SEXTA, cliente=_cliente()
    )

    assert avisos == []
    assert [(e["data"], e["hora"], e["pais"], e["evento"]) for e in eventos] == [
        ("2026-11-04", "18:30", "BR", "Copom: decisão"),
        ("2026-11-05", "09:00", "BR", "Produção industrial (PIM-PF)"),
        ("2026-11-06", "10:30", "EUA", "Payroll"),
    ]
    assert eventos[0]["consenso"] == {
        "mediana": 13.5,
        "unidade": "% a.a.",
        "fonte": "Focus",
        "data": "2026-10-09",
    }
    assert eventos[1]["consenso"] is None  # o Focus nao tem PIM-PF
    assert eventos[0]["detalhe"] == "reunião 7/2026"


def test_ordem_no_dia_hora_depois_pais_e_sem_hora_por_ultimo() -> None:
    # 29/10: BEA 09:30 (PIB e PCE, mesmo horario, ordem por nome) e IBGE 30/10 PNAD.
    eventos, _ = montar_agenda(
        date(2026, 10, 26), date(2026, 10, 30), focus_ate=SEXTA, cliente=_cliente()
    )

    assert [(e["data"], e["hora"], e["evento"]) for e in eventos] == [
        ("2026-10-28", "15:00", "FOMC: decisão"),
        ("2026-10-29", "09:30", "PCE (renda e gastos pessoais)"),
        ("2026-10-29", "09:30", "PIB dos EUA"),
        ("2026-10-30", "09:00", "Desemprego (PNAD Contínua)"),
    ]


def test_ipca_recebe_o_consenso_do_mes() -> None:
    eventos, _ = montar_agenda(
        date(2026, 11, 9), date(2026, 11, 13), focus_ate=SEXTA, cliente=_cliente()
    )

    ipca = next(e for e in eventos if e["evento"] == "IPCA")
    assert ipca["consenso"]["mediana"] == 0.3277


def test_focus_fora_do_ar_deixa_consenso_nulo_e_avisa_uma_vez() -> None:
    eventos, avisos = montar_agenda(
        date(2026, 11, 2),
        date(2026, 11, 13),
        focus_ate=SEXTA,
        cliente=_cliente(**{"olinda.bcb.gov.br": 503}),
    )

    assert len(eventos) >= 4
    assert all(e["consenso"] is None for e in eventos)
    assert avisos == ["Focus indisponível (HTTP 503): eventos sem consenso"]


def test_fonte_que_cai_vira_aviso_e_as_outras_seguem() -> None:
    eventos, avisos = montar_agenda(
        date(2026, 11, 2),
        date(2026, 11, 6),
        focus_ate=SEXTA,
        cliente=_cliente(**{"servicodados.ibge.gov.br": 500}),
    )

    assert avisos == ["agenda IBGE indisponível: HTTP 500"]
    assert [e["evento"] for e in eventos] == ["Copom: decisão", "Payroll"]


def test_agenda_fixa_vencida_vira_aviso_no_resultado() -> None:
    _, avisos = montar_agenda(
        date(2028, 1, 10), date(2028, 1, 14), focus_ate=SEXTA, cliente=_cliente()
    )

    assert any("Copom depois de 2027" in a for a in avisos)
    assert "calendário do FOMC sem 2028" in avisos
    assert "agenda do BEA sem 2028" in avisos
