"""Agenda fixa (Copom, CPI, payroll): o YAML do pacote e os eventos que ele gera."""

from __future__ import annotations

from datetime import date, time

from scanner.semana import agenda_fixa
from scanner.semana.agenda_fixa import carregar, eventos_fixos


def test_yaml_entra_no_pacote_e_carrega() -> None:
    dados = carregar()

    assert set(dados) == {"copom", "bls"}
    assert set(dados["bls"]) == {"cpi", "payroll"}


def test_copom_tem_oito_reunioes_por_ano_e_ata_depois_do_segundo_dia() -> None:
    copom = carregar()["copom"]

    assert sorted(copom) == [2026, 2027]
    for ano, reunioes in copom.items():
        assert [r["reuniao"] for r in reunioes] == list(range(1, 9))
        for r in reunioes:
            primeiro, segundo = r["dias"]
            assert primeiro.year == segundo.year == ano
            assert (segundo - primeiro).days == 1
            assert r["ata"] > segundo
        segundos = [r["dias"][1] for r in reunioes]
        assert segundos == sorted(segundos)


def test_datas_do_bls_em_ordem_e_referencia_em_formato_aaaa_mm() -> None:
    for serie in carregar()["bls"].values():
        datas = [item["data"] for item in serie]
        assert datas == sorted(datas)
        for item in serie:
            assert len(item["referencia"]) == 7 and item["referencia"][4] == "-"


def test_semana_do_copom_de_novembro() -> None:
    eventos, avisos = eventos_fixos(date(2026, 11, 2), date(2026, 11, 6))

    assert avisos == []
    por_nome = {e.evento: e for e in eventos}
    decisao = por_nome["Copom: decisão"]
    assert (decisao.data, decisao.hora, decisao.detalhe) == (
        date(2026, 11, 4),
        time(18, 30),
        "reunião 7/2026",
    )
    assert decisao.focus is not None and decisao.focus.chave == "R7/2026"
    # Payroll 06/11 08:30 NY: o horario de verao dos EUA acabou em 01/11, entao
    # e UTC-5 e Brasilia (UTC-3) esta 2h a frente -> 10:30.
    payroll = por_nome["Payroll"]
    assert (payroll.data, payroll.hora, payroll.detalhe) == (
        date(2026, 11, 6),
        time(10, 30),
        "outubro",
    )
    assert "CPI" not in por_nome


def test_cpi_no_horario_de_verao_dos_eua_chega_as_nove_e_meia() -> None:
    # 13/01/2027 e inverno em Nova York (UTC-5): 10:30 em Brasilia. Em 14/10/2027
    # ainda e verao (UTC-4): 09:30. A conta nao pode usar diferenca fixa.
    inverno, _ = eventos_fixos(date(2027, 1, 11), date(2027, 1, 15))
    verao, _ = eventos_fixos(date(2027, 10, 11), date(2027, 10, 15))

    cpi_inverno = next(e for e in inverno if e.evento == "CPI")
    cpi_verao = next(e for e in verao if e.evento == "CPI")
    assert (cpi_inverno.hora, cpi_inverno.detalhe) == (time(10, 30), "dezembro de 2026")
    assert (cpi_verao.hora, cpi_verao.detalhe) == (time(9, 30), "setembro")


def test_ata_do_copom_as_oito() -> None:
    eventos, _ = eventos_fixos(date(2026, 11, 9), date(2026, 11, 13))

    ata = next(e for e in eventos if e.evento == "Copom: ata")
    assert (ata.data, ata.hora) == (date(2026, 11, 10), time(8, 0))


def test_semana_sem_nada_da_agenda_fixa() -> None:
    eventos, avisos = eventos_fixos(date(2026, 10, 19), date(2026, 10, 23))

    assert eventos == []
    assert avisos == []


def test_semana_alem_da_cobertura_avisa_qual_arquivo_atualizar() -> None:
    eventos, avisos = eventos_fixos(date(2028, 1, 10), date(2028, 1, 14))

    assert eventos == []
    assert len(avisos) == 3
    assert "Copom depois de 2027" in avisos[0]
    assert "CPI depois de 2027-12-10" in avisos[1]
    assert "payroll depois de 2027-12-03" in avisos[2]
    assert all(agenda_fixa.ARQUIVO in a for a in avisos)
