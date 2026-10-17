"""Busca de empresa na B3 por ticker, com as guardas que evitam ligar errado."""

from __future__ import annotations

import base64
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from scanner.fundamentos.b3 import (
    B3IndisponivelError,
    buscar_candidatos,
    codigos_da_empresa,
    proventos_recentes,
    suplemento,
)


class _RespostaFalsa:
    def __init__(self, status: int, payload: Any = None, corpo_vazio: bool = False) -> None:
        self.status_code = status
        self._payload = payload
        self._corpo_vazio = corpo_vazio

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> Any:
        if self._corpo_vazio:
            raise ValueError("corpo vazio")
        return self._payload


class _ClienteFalso:
    """Substitui `httpx.Client`, devolvendo respostas na ordem e guardando as URLs."""

    def __init__(self, respostas: list[_RespostaFalsa]) -> None:
        self._respostas = list(respostas)
        self.urls: list[str] = []

    def get(self, url: str) -> _RespostaFalsa:
        self.urls.append(url)
        return self._respostas.pop(0)


def _payload_da_url(url: str) -> dict[str, Any]:
    corpo = url.rsplit("/", 1)[-1]
    lido: dict[str, Any] = json.loads(base64.b64decode(corpo))
    return lido


def _busca(*empresas: tuple[str, str]) -> _RespostaFalsa:
    return _RespostaFalsa(
        200,
        {
            "page": {"pageNumber": 1, "pageSize": 20, "totalRecords": len(empresas)},
            "results": [{"codeCVM": cd, "companyName": nome} for cd, nome in empresas],
        },
    )


def _detalhe(*codigos: str) -> _RespostaFalsa:
    principal, *outros = codigos
    return _RespostaFalsa(
        200,
        {"code": principal, "otherCodes": [{"code": c} for c in outros]},
    )


def test_busca_manda_o_ticker_em_maiusculo_no_payload() -> None:
    cliente = _ClienteFalso([_busca(("4030", "CIA SIDERURGICA NACIONAL"))])

    buscar_candidatos(cliente, "csna3")  # type: ignore[arg-type]

    payload = _payload_da_url(cliente.urls[0])
    assert payload["company"] == "CSNA3"
    assert payload["pageSize"] == 20


def test_candidato_sem_codigo_cvm_numerico_e_descartado() -> None:
    cliente = _ClienteFalso([_busca(("", "SEM CODIGO"), ("4030", "CIA SIDERURGICA NACIONAL"))])

    candidatos = buscar_candidatos(cliente, "CSNA3")  # type: ignore[arg-type]

    assert [c.cd_cvm for c in candidatos] == [4030]


def test_codigos_da_empresa_junta_o_principal_e_os_outros() -> None:
    cliente = _ClienteFalso([_detalhe("KLBN11", "KLBN3", "KLBN4")])

    assert codigos_da_empresa(cliente, 12653) == {"KLBN11", "KLBN3", "KLBN4"}  # type: ignore[arg-type]


def test_detalhe_com_corpo_vazio_nao_lista_codigo_nenhum() -> None:
    # `GetDetail` com codeCVM invalido devolve corpo vazio, e nao 404.
    cliente = _ClienteFalso([_RespostaFalsa(200, corpo_vazio=True)])

    assert codigos_da_empresa(cliente, 999999) == set()  # type: ignore[arg-type]


def test_empresa_homonima_nao_lista_o_ticker_procurado() -> None:
    """A guarda que separa a Embraer da EMBRAST.

    Procurar EMBR3 na B3 devolve a EMBRAST (codeCVM 917848). Os codigos que a
    B3 lista para ela nao incluem EMBR3, entao a ligacao tem de ser recusada.
    """
    cliente = _ClienteFalso([_detalhe("EMBP3")])

    assert "EMBR3" not in codigos_da_empresa(cliente, 917848)  # type: ignore[arg-type]


def test_retry_em_erro_5xx_e_depois_sucesso() -> None:
    cliente = _ClienteFalso([_RespostaFalsa(503), _busca(("4030", "CIA SIDERURGICA NACIONAL"))])

    candidatos = buscar_candidatos(cliente, "CSNA3", tentativas=2, espera=0)  # type: ignore[arg-type]

    assert [c.cd_cvm for c in candidatos] == [4030]
    assert len(cliente.urls) == 2


def test_falha_persistente_vira_erro_proprio() -> None:
    cliente = _ClienteFalso([_RespostaFalsa(500), _RespostaFalsa(500), _RespostaFalsa(500)])

    with pytest.raises(B3IndisponivelError):
        buscar_candidatos(cliente, "CSNA3", tentativas=3, espera=0)  # type: ignore[arg-type]


# Suplemento real da B3, capturado em 17/10/2026 e recortado: so os itens de
# stockDividends que os testes usam, mais um provento em dinheiro de cada.
_FIXTURE_SUPLEMENTO = Path(__file__).parent / "fixtures" / "semana" / "b3_suplemento.json"


def _suplemento_real(emissor: str) -> _RespostaFalsa:
    return _RespostaFalsa(200, json.loads(_FIXTURE_SUPLEMENTO.read_text())[emissor])


def test_suplemento_le_eventos_em_acoes_reais() -> None:
    cliente = _ClienteFalso([_suplemento_real("MGLU")])

    sup = suplemento(cliente, "MGLU")  # type: ignore[arg-type]

    por_tipo = {e.tipo: e for e in sup.eventos_em_acoes}
    assert set(por_tipo) == {"DESDOBRAMENTO", "GRUPAMENTO", "BONIFICACAO"}
    assert por_tipo["DESDOBRAMENTO"].fator == Decimal("300")
    assert por_tipo["DESDOBRAMENTO"].data_com == date(2020, 10, 13)
    assert por_tipo["DESDOBRAMENTO"].data_aprovacao == date(2020, 10, 7)
    assert por_tipo["DESDOBRAMENTO"].isin == "BRMGLUACNOR2"
    assert por_tipo["DESDOBRAMENTO"].multiplicador == Decimal("4")
    assert por_tipo["GRUPAMENTO"].multiplicador == Decimal("0.1")
    assert por_tipo["BONIFICACAO"].multiplicador == Decimal("1.05")


def test_desdobramento_do_bbas_vira_uma_acao_em_duas() -> None:
    sup = suplemento(_ClienteFalso([_suplemento_real("BBAS")]), "BBAS")  # type: ignore[arg-type]

    (evento,) = sup.eventos_em_acoes
    assert evento.isin == "BRBBASACNOR3"
    assert evento.data_com == date(2024, 4, 15)
    assert evento.multiplicador == Decimal("2")


def test_bonificacao_do_itub_casa_pelo_isin_de_quem_sofre_o_evento() -> None:
    sup = suplemento(_ClienteFalso([_suplemento_real("ITUB")]), "ITUB")  # type: ignore[arg-type]

    bonificacoes = {e.isin: e for e in sup.eventos_em_acoes if e.tipo == "BONIFICACAO"}
    assert set(bonificacoes) == {"BRITUBACNOR4", "BRITUBACNPR1"}
    assert all(e.multiplicador == Decimal("1.03") for e in bonificacoes.values())


def test_cisao_nao_se_ajusta_por_fator() -> None:
    sup = suplemento(_ClienteFalso([_suplemento_real("ITUB")]), "ITUB")  # type: ignore[arg-type]

    cisoes = [e for e in sup.eventos_em_acoes if e.tipo == "CIS RED CAP"]
    assert cisoes
    assert all(e.multiplicador is None for e in cisoes)
    # O ISIN e o da acao que sofre o evento, nao o do papel emitido (XPAR).
    assert {e.isin for e in cisoes} == {"BRITUBACNOR4", "BRITUBACNPR1"}


def test_bonificacao_em_outra_classe_nao_se_ajusta_por_fator() -> None:
    # Quem tem ON recebe PN: a quantidade de ON nao muda, o fator nao basta.
    item = {
        "label": "BONIFICACAO",
        "factor": "10,0",
        "lastDatePrior": "15/04/2024",
        "isinCode": "BRXXXXACNOR1",
        "assetIssued": "BRXXXXACNPR8",
    }
    cliente = _ClienteFalso([_RespostaFalsa(200, {"stockDividends": [item]})])
    sup = suplemento(cliente, "XXXX")  # type: ignore[arg-type]

    (evento,) = sup.eventos_em_acoes
    assert evento.em_outro_papel
    assert evento.multiplicador is None


def test_item_antigo_sem_asset_issued_e_do_proprio_papel() -> None:
    item = {
        "label": "BONIFICACAO",
        "factor": "20,0",
        "lastDatePrior": "17/06/1996",
        "isinCode": "BRBBASACNOR3",
        "assetIssued": "",
    }
    cliente = _ClienteFalso([_RespostaFalsa(200, {"stockDividends": [item]})])
    sup = suplemento(cliente, "BBAS")  # type: ignore[arg-type]

    (evento,) = sup.eventos_em_acoes
    assert not evento.em_outro_papel
    assert evento.multiplicador == Decimal("1.2")


def test_desdobramento_e_grupamento_no_mesmo_dia_ficam_os_dois() -> None:
    sup = suplemento(_ClienteFalso([_suplemento_real("CASH")]), "CASH")  # type: ignore[arg-type]

    assert {e.data_com for e in sup.eventos_em_acoes} == {date(2023, 5, 31)}
    liquido = Decimal(1)
    for e in sup.eventos_em_acoes:
        assert e.multiplicador is not None
        liquido *= e.multiplicador
    assert liquido == Decimal("0.1")  # 10 acoes viram 1


def test_item_incompleto_de_stock_dividends_e_descartado() -> None:
    base = {"label": "DESDOBRAMENTO", "factor": "100,0", "lastDatePrior": "15/04/2024"}
    itens = [
        {**base, "isinCode": "BRXXXXACNOR1"},
        {**base},  # sem isinCode
        {**base, "isinCode": "BRXXXXACNOR1", "lastDatePrior": ""},
        {**base, "isinCode": "BRXXXXACNOR1", "factor": "0,0"},
        {**base, "isinCode": "BRXXXXACNOR1", "factor": "-5,0"},
        {**base, "isinCode": "BRXXXXACNOR1", "factor": "lixo"},
        "nao e dict",
    ]
    cliente = _ClienteFalso([_RespostaFalsa(200, {"stockDividends": itens})])

    sup = suplemento(cliente, "XXXX")  # type: ignore[arg-type]

    assert len(sup.eventos_em_acoes) == 1


def test_proventos_recentes_segue_igual_e_usa_so_cash_dividends() -> None:
    cliente = _ClienteFalso([_suplemento_real("ITUB")])

    proventos = proventos_recentes(cliente, "ITUB")  # type: ignore[arg-type]

    (p,) = proventos
    assert p.isin == "BRITUBACNOR4"
    assert p.tipo == "JRS CAP PROPRIO"
    assert p.valor == Decimal("0.01818200000")
    assert p.data_com == date(2026, 9, 30)
    assert p.data_pagamento == date(2026, 11, 3)
    payload = _payload_da_url(cliente.urls[0])
    assert payload == {"language": "pt-br", "issuingCompany": "ITUB"}


def test_suplemento_com_resposta_vazia() -> None:
    sup = suplemento(_ClienteFalso([_RespostaFalsa(200, [])]), "ZZZZ")  # type: ignore[arg-type]
    assert sup.proventos == []
    assert sup.eventos_em_acoes == []
