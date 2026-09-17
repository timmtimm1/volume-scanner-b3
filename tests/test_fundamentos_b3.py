"""Busca de empresa na B3 por ticker, com as guardas que evitam ligar errado."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from scanner.fundamentos.b3 import (
    B3IndisponivelError,
    buscar_candidatos,
    codigos_da_empresa,
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
