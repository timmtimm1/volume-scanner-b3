"""Proventos: de que papel e cada um, e a conferencia contra o COTAHIST."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from scanner.fundamentos.b3 import Provento
from scanner.fundamentos.proventos import (
    Conferencia,
    classe_do_isin,
    conferir_com_recentes,
    conferir_precos,
    ligar_historicos,
    ligar_recentes,
)

# ISINs reais da B3, conferidos contra o site dela.
ISIN_UNIP3 = "BRUNIPACNOR7"
ISIN_UNIP5 = "BRUNIPACNPA0"
ISIN_UNIP6 = "BRUNIPACNPB8"
ISIN_KLBN11 = "BRKLBNCDAM18"
ISIN_BPAC11 = "BRBPACUNT006"


def _recente(isin: str, valor: str, dia: date, tipo: str = "DIVIDENDO") -> Provento:
    return Provento(
        classe=None,
        isin=isin,
        tipo=tipo,
        valor=Decimal(valor),
        data_com=dia,
        data_aprovacao=None,
        data_pagamento=None,
    )


def _historico(
    classe: str, valor: str, dia: date, preco: str | None = None, tipo: str = "DIVIDENDO"
) -> Provento:
    return Provento(
        classe=classe,
        isin=None,
        tipo=tipo,
        valor=Decimal(valor),
        data_com=dia,
        data_aprovacao=None,
        data_pagamento=None,
        preco_data_com=None if preco is None else Decimal(preco),
    )


# --- Classe pelo ISIN --------------------------------------------------------


def test_classe_de_cada_tipo_de_isin() -> None:
    assert classe_do_isin(ISIN_UNIP3) == "ON"
    assert classe_do_isin(ISIN_UNIP5) == "PNA"
    assert classe_do_isin(ISIN_UNIP6) == "PNB"
    assert classe_do_isin("BRITUBACNPR1") == "PN"
    # Unit aparece nos dois formatos que a B3 usa.
    assert classe_do_isin(ISIN_KLBN11) == "UNT"
    assert classe_do_isin(ISIN_BPAC11) == "UNT"


def test_isin_desconhecido_nao_vira_classe_inventada() -> None:
    assert classe_do_isin("XX") is None
    assert classe_do_isin("BRXXXXZZZZ99") is None


# --- Recentes: o ISIN diz exatamente de que papel e --------------------------


def test_recentes_vao_para_o_papel_do_isin() -> None:
    por_isin = {ISIN_UNIP3: "UNIP3", ISIN_UNIP6: "UNIP6"}
    brutos = [
        _recente(ISIN_UNIP3, "5.48220258487", date(2025, 12, 5)),
        _recente(ISIN_UNIP6, "6.03042284335", date(2025, 12, 5)),
    ]

    linhas = ligar_recentes(brutos, por_isin)

    # O valor por acao e diferente em cada classe: e por isso que o provento e
    # guardado por papel, e nao por empresa.
    assert {(linha.ticker, str(linha.valor)) for linha in linhas} == {
        ("UNIP3", "5.48220258487"),
        ("UNIP6", "6.03042284335"),
    }
    assert {linha.fonte for linha in linhas} == {"recente"}


def test_isin_de_outra_empresa_nao_vira_linha() -> None:
    """A consulta dos recentes so aceita o codigo de emissor, que e chave fraca.

    Se a B3 responder com papel de outra companhia, o ISIN nao vai estar entre
    os desta -- e a linha fica de fora em vez de virar dado errado.
    """
    linhas = ligar_recentes(
        [_recente("BREMBRACNOR1", "1.00", date(2026, 3, 2))], {ISIN_UNIP6: "UNIP6"}
    )

    assert linhas == []


# --- Historico: entra so o que a consulta recente nao cobre ------------------


def test_historico_para_antes_da_fronteira() -> None:
    por_classe = {"ON": "UNIP3", "PNB": "UNIP6"}
    brutos = [
        _historico("ON", "2.08900905260", date(2025, 3, 18)),
        _historico("ON", "5.48220258487", date(2025, 12, 5)),
    ]

    linhas = ligar_historicos(brutos, por_classe, antes_de=date(2025, 12, 5))

    # A de 05/12 ja veio pela consulta recente, com ISIN: nao entra duas vezes.
    assert [(linha.ticker, linha.data_com) for linha in linhas] == [("UNIP3", date(2025, 3, 18))]
    assert linhas[0].fonte == "historico"


def test_historico_de_classe_que_a_empresa_nao_tem_fica_de_fora() -> None:
    linhas = ligar_historicos(
        [_historico("PNC", "1.00", date(2024, 5, 2))], {"ON": "UNIP3"}, antes_de=None
    )

    assert linhas == []


# --- Conferencia contra o COTAHIST ------------------------------------------


def test_precos_que_batem_aprovam_o_historico() -> None:
    por_classe = {"ON": "UNIP3"}
    brutos = [
        _historico("ON", "1.00", date(2025, 3, 18), preco="62.22"),
        _historico("ON", "1.00", date(2024, 11, 19), preco="70.00"),
        _historico("ON", "1.00", date(2024, 3, 19), preco="80.00"),
    ]
    fechamentos = {
        ("UNIP3", date(2025, 3, 18)): Decimal("62.2200"),
        # Dentro da tolerancia: a B3 arredonda em duas casas.
        ("UNIP3", date(2024, 11, 19)): Decimal("70.1500"),
        ("UNIP3", date(2024, 3, 19)): Decimal("80.0000"),
    }

    conferencia = conferir_precos(brutos, por_classe, fechamentos)

    assert conferencia == Conferencia(comparaveis=3, batendo=3)
    assert conferencia.aprovado


def test_historico_de_outra_empresa_reprova_pelo_preco() -> None:
    """A defesa contra o nome de pregao casar com a companhia errada.

    Uma empresa diferente pode ate ter pago nas mesmas datas, mas o preco dela
    nesses dias nao vai ser o do nosso papel.
    """
    por_classe = {"ON": "UNIP3"}
    brutos = [
        _historico("ON", "1.00", date(2025, 3, 18), preco="12.30"),
        _historico("ON", "1.00", date(2024, 11, 19), preco="11.80"),
        _historico("ON", "1.00", date(2024, 3, 19), preco="10.40"),
    ]
    fechamentos = {
        ("UNIP3", date(2025, 3, 18)): Decimal("62.2200"),
        ("UNIP3", date(2024, 11, 19)): Decimal("70.1500"),
        ("UNIP3", date(2024, 3, 19)): Decimal("80.0000"),
    }

    conferencia = conferir_precos(brutos, por_classe, fechamentos)

    assert conferencia.batendo == 0
    assert not conferencia.aprovado


def test_poucas_datas_comparaveis_nao_aprovam() -> None:
    """Sem prova nao entra. Papel antigo demais para o banco fica sem historico.

    O banco guarda 400 pregoes; um provento de 2019 nao tem barra para
    comparar. Preferimos ficar sem yield antigo a gravar o que nao da para
    conferir.
    """
    conferencia = conferir_precos(
        [_historico("ON", "1.00", date(2019, 5, 2), preco="30.00")],
        {"ON": "UNIP3"},
        {("UNIP3", date(2019, 5, 2)): Decimal("30.0000")},
    )

    assert conferencia == Conferencia(comparaveis=1, batendo=1)
    assert not conferencia.aprovado
    assert "1 datas comparaveis" in conferencia.resumo()


def test_uma_data_fora_nao_reprova_o_historico_todo() -> None:
    """Uma data destoando e ruido; oito de dez destoando e outra empresa."""
    por_classe = {"ON": "UNIP3"}
    datas = [
        date(2025, 3, 18),
        date(2024, 11, 19),
        date(2024, 3, 19),
        date(2023, 12, 18),
        date(2023, 5, 3),
    ]
    brutos = [_historico("ON", "1.00", dia, preco="50.00") for dia in datas]
    fechamentos = {("UNIP3", dia): Decimal("50.0000") for dia in datas}
    fechamentos[("UNIP3", datas[-1])] = Decimal("90.0000")

    conferencia = conferir_precos(brutos, por_classe, fechamentos)

    assert (conferencia.comparaveis, conferencia.batendo) == (5, 4)
    assert conferencia.aprovado, "4 de 5 e o limite: abaixo disso o historico cai"


def test_recentes_confirmam_historico_que_o_preco_nao_alcanca() -> None:
    """A segunda prova, para empresa cujos proventos sao anteriores as barras."""
    por_classe = {"ON": "UNIP3"}
    datas = [date(2026, 3, 18), date(2025, 11, 19), date(2025, 3, 19)]
    brutos = [_historico("ON", "1.50", dia) for dia in datas]
    ja_conhecidos = [("UNIP3", dia, Decimal("1.50")) for dia in datas]

    conferencia = conferir_com_recentes(brutos, por_classe, ja_conhecidos)

    assert conferencia == Conferencia(comparaveis=3, batendo=3)
    assert conferencia.aprovado


def test_valores_diferentes_nas_mesmas_datas_reprovam() -> None:
    por_classe = {"ON": "UNIP3"}
    datas = [date(2026, 3, 18), date(2025, 11, 19), date(2025, 3, 19)]
    brutos = [_historico("ON", "9.99", dia) for dia in datas]
    ja_conhecidos = [("UNIP3", dia, Decimal("1.50")) for dia in datas]

    conferencia = conferir_com_recentes(brutos, por_classe, ja_conhecidos)

    assert conferencia.batendo == 0
    assert not conferencia.aprovado


def test_sem_provento_recente_nao_ha_o_que_conferir() -> None:
    conferencia = conferir_com_recentes(
        [_historico("ON", "1.50", date(2025, 3, 19))], {"ON": "UNIP3"}, []
    )

    assert not conferencia.aprovado


def test_metade_fora_reprova() -> None:
    por_classe = {"ON": "UNIP3"}
    datas = [date(2025, 3, 18), date(2024, 11, 19), date(2024, 3, 19), date(2023, 12, 18)]
    brutos = [_historico("ON", "1.00", dia, preco="50.00") for dia in datas]
    fechamentos = {("UNIP3", dia): Decimal("50.0000") for dia in datas[:2]}
    fechamentos.update({("UNIP3", dia): Decimal("90.0000") for dia in datas[2:]})

    conferencia = conferir_precos(brutos, por_classe, fechamentos)

    assert (conferencia.comparaveis, conferencia.batendo) == (4, 2)
    assert not conferencia.aprovado
