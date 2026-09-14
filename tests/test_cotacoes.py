"""Fornecedores de cotacao: leitura das respostas, lote, token e escolha da mais recente.

Nada aqui toca a rede. `httpx.get` e trocado por uma funcao que registra o
pedido e devolve a resposta montada no teste.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from scanner import cli
from scanner.calendar import hoje_na_b3
from scanner.cotacoes import BrapiClient, Cotacao, ProvedorMaisRecente, YahooClient, brapi, yahoo

TOKEN = "token-de-teste-nao-e-real"
HORA = datetime(2026, 9, 14, 16, 14, 30, tzinfo=UTC)


def _item_brapi(
    simbolo: str, preco: object = 49.13, hora: object = "2026-09-14T16:14:30.000Z"
) -> dict[str, object]:
    return {"symbol": simbolo, "regularMarketPrice": preco, "regularMarketTime": hora}


def _meta_yahoo(**meta: object) -> dict[str, object]:
    return {"chart": {"result": [{"meta": meta}]}}


@dataclass
class Pedido:
    url: str
    params: dict[str, Any]
    headers: dict[str, str]


def _falso_get(
    pedidos: list[Pedido], responder: Callable[[str], httpx.Response]
) -> Callable[..., httpx.Response]:
    def get(url: str, **kwargs: Any) -> httpx.Response:
        pedidos.append(
            Pedido(url, dict(kwargs.get("params") or {}), dict(kwargs.get("headers") or {}))
        )
        resposta = responder(url)
        resposta.request = httpx.Request("GET", url)
        return resposta

    return get


# --- brapi ----------------------------------------------------------------------


def test_brapi_le_preco_e_hora() -> None:
    cotacoes = brapi.extrair({"results": [_item_brapi("petr4")]})
    assert cotacoes == {"PETR4": Cotacao("PETR4", Decimal("49.13"), "brapi", HORA)}


@pytest.mark.parametrize(
    "item",
    [
        _item_brapi("PETR4", hora=None),
        _item_brapi("PETR4", hora="ontem"),
        _item_brapi("PETR4", hora="2026-09-14T16:14:30"),  # sem fuso: hora ambigua
        _item_brapi("PETR4", preco=0),
        _item_brapi("PETR4", preco=None),
    ],
)
def test_brapi_descarta_cotacao_sem_hora_ou_sem_preco(item: dict[str, object]) -> None:
    assert brapi.extrair({"results": [item]}) == {}


def test_brapi_resposta_fora_do_formato_nao_derruba() -> None:
    assert brapi.extrair(None) == {}
    assert brapi.extrair({"results": "x"}) == {}
    assert brapi.extrair({"results": ["x", 1]}) == {}


def test_brapi_manda_um_papel_por_requisicao_e_token_no_cabecalho(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pedidos: list[Pedido] = []

    def responder(url: str) -> httpx.Response:
        simbolos = url.rsplit("/", 1)[1].split(",")
        return httpx.Response(200, json={"results": [_item_brapi(s) for s in simbolos]})

    monkeypatch.setattr(brapi.httpx, "get", _falso_get(pedidos, responder))

    cotacoes = BrapiClient(token=TOKEN).cotacoes(["PETR4", "vale3", "../x", "ITUB4"])

    assert set(cotacoes) == {"PETR4", "VALE3", "ITUB4"}
    assert [p.url.rsplit("/", 1)[1] for p in pedidos] == ["PETR4", "VALE3", "ITUB4"]
    for pedido in pedidos:
        assert pedido.headers["Authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in pedido.url
        assert TOKEN not in str(pedido.params)


def test_brapi_respeita_o_lote_do_plano(monkeypatch: pytest.MonkeyPatch) -> None:
    pedidos: list[Pedido] = []
    monkeypatch.setattr(
        brapi.httpx,
        "get",
        _falso_get(pedidos, lambda url: httpx.Response(200, json={"results": []})),
    )
    BrapiClient(token=TOKEN, lote=10).cotacoes([f"ABCD{i}" for i in range(1, 13)])
    assert [len(p.url.rsplit("/", 1)[1].split(",")) for p in pedidos] == [10, 2]


def test_brapi_recusa_vira_log_com_status_e_sem_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pedidos: list[Pedido] = []
    monkeypatch.setattr(
        brapi.httpx,
        "get",
        _falso_get(pedidos, lambda url: httpx.Response(401, json={"error": True})),
    )
    # Os testes de banco rodam o Alembic, cujo `fileConfig` desliga os loggers
    # que ja existiam. Em producao a migration roda em outro processo.
    monkeypatch.setattr(brapi.logger, "disabled", False)
    with caplog.at_level(logging.WARNING):
        assert BrapiClient(token=TOKEN).cotacoes(["PETR4"]) == {}
    assert "HTTP 401" in caplog.text
    assert TOKEN not in caplog.text


# --- Yahoo ----------------------------------------------------------------------


def test_yahoo_le_preco_e_hora() -> None:
    dados = _meta_yahoo(regularMarketPrice=13.04, regularMarketTime=int(HORA.timestamp()))
    assert yahoo.extrair("ALPA4", dados) == Cotacao("ALPA4", Decimal("13.04"), "yahoo", HORA)


def test_yahoo_nao_usa_o_fechamento_de_ontem_como_preco_de_agora() -> None:
    dados = _meta_yahoo(chartPreviousClose=13.33, regularMarketTime=int(HORA.timestamp()))
    assert yahoo.extrair("ALPA4", dados) is None


@pytest.mark.parametrize(
    "dados",
    [
        _meta_yahoo(regularMarketPrice=13.04),
        _meta_yahoo(regularMarketPrice=0, regularMarketTime=int(HORA.timestamp())),
        {"chart": {"result": []}},
        None,
    ],
)
def test_yahoo_descarta_o_que_nao_da_para_confiar(dados: object) -> None:
    assert yahoo.extrair("ALPA4", dados) is None


def test_yahoo_papel_inexistente_nao_vira_cotacao(monkeypatch: pytest.MonkeyPatch) -> None:
    pedidos: list[Pedido] = []
    monkeypatch.setattr(
        yahoo.httpx, "get", _falso_get(pedidos, lambda url: httpx.Response(404, json={}))
    )
    assert YahooClient().cotacoes(["ABCD9"]) == {}
    assert pedidos[0].url.endswith("/ABCD9.SA")


# --- A mais recente -------------------------------------------------------------


@dataclass(frozen=True)
class Fixo:
    nome: str
    horas: dict[str, datetime]

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        return {
            t: Cotacao(t, Decimal("10"), self.nome, self.horas[t])
            for t in tickers
            if t in self.horas
        }


@dataclass(frozen=True)
class Quebrado:
    nome: str = "quebrado"

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        raise RuntimeError("bug no adaptador")


def test_fica_com_a_cotacao_de_hora_mais_nova_independente_da_ordem() -> None:
    cedo = datetime(2026, 9, 14, 15, 45, tzinfo=UTC)
    tarde = datetime(2026, 9, 14, 16, 0, tzinfo=UTC)
    brapi_lenta = Fixo("brapi", {"PETR4": cedo, "VALE3": tarde})
    yahoo_rapido = Fixo("yahoo", {"PETR4": tarde, "VALE3": cedo})

    escolhidas = ProvedorMaisRecente((brapi_lenta, yahoo_rapido)).cotacoes(["PETR4", "VALE3"])

    assert escolhidas["PETR4"].fonte == "yahoo"
    assert escolhidas["VALE3"].fonte == "brapi"


def test_empate_fica_com_o_primeiro_fornecedor() -> None:
    primeiro = Fixo("brapi", {"PETR4": HORA})
    segundo = Fixo("yahoo", {"PETR4": HORA})
    assert ProvedorMaisRecente((primeiro, segundo)).cotacoes(["PETR4"])["PETR4"].fonte == "brapi"


def test_um_fornecedor_quebrado_nao_impede_os_outros() -> None:
    provedor = ProvedorMaisRecente((Quebrado(), Fixo("yahoo", {"PETR4": HORA})))
    assert provedor.cotacoes(["PETR4", "VALE3"])["PETR4"].fonte == "yahoo"


# --- Montagem na CLI ------------------------------------------------------------


@dataclass
class SettingsFalsas:
    brapi_token: Any = None
    brapi_lote: int = 1


def test_sem_token_a_brapi_fica_de_fora(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_settings", lambda: SettingsFalsas())
    provedor = cli._provedor_de_cotacoes()
    assert [p.nome for p in provedor.provedores] == ["yahoo"]


def test_com_token_brapi_entra_na_frente_com_o_lote_configurado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(
        cli, "_settings", lambda: SettingsFalsas(brapi_token=SecretStr(TOKEN), brapi_lote=10)
    )
    provedor = cli._provedor_de_cotacoes()
    assert [p.nome for p in provedor.provedores] == ["brapi", "yahoo"]
    assert provedor.provedores[0].lote == 10


def test_hoje_e_o_dia_de_sao_paulo() -> None:
    # 23:30 de domingo em Brasilia ja e segunda em UTC.
    assert hoje_na_b3(datetime(2026, 9, 14, 2, 30, tzinfo=UTC)) == date(2026, 9, 13)
