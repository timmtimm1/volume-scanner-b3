"""Fornecedores de cotacao: leitura das respostas, lote, token e escolha da mais recente.

Nada aqui toca a rede. `httpx.get` e trocado por uma funcao que registra o
pedido e devolve a resposta montada no teste.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from scanner import cli
from scanner.calendar import hoje_na_b3
from scanner.cotacoes import (
    BrapiClient,
    Cota,
    Cotacao,
    ProvedorMaisRecente,
    YahooClient,
    brapi,
    yahoo,
)

TOKEN = "token-de-teste-nao-e-real"
HORA = datetime(2026, 9, 14, 16, 14, 30, tzinfo=UTC)


def _item_brapi(
    simbolo: str,
    preco: object = 49.13,
    hora: object = "2026-09-14T16:14:30.000Z",
    *,
    pedido: str | None = None,
    trocado: bool = False,
) -> dict[str, object]:
    """Um item de `results` no formato do v2: `symbol` + `data` aninhado."""
    return {
        "requestedSymbol": pedido or simbolo,
        "symbol": simbolo,
        "changed": trocado,
        "data": {"regularMarketPrice": preco, "regularMarketTime": hora},
    }


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
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(brapi.httpx, "get", _falso_get(pedidos, responder))

    BrapiClient(token=TOKEN).cotacoes(["PETR4", "vale3", "../x", "ITUB4"])

    assert [p.params["symbols"] for p in pedidos] == ["PETR4", "VALE3", "ITUB4"]
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
    assert [len(p.params["symbols"].split(",")) for p in pedidos] == [10, 2]


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


def test_brapi_ticker_renomeado_entra_pelo_codigo_novo(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`changed: true` significa que o papel foi renomeado -- o dicionario usa
    o codigo NOVO (`symbol`), que e o que um alerta precisa achar."""
    item = _item_brapi("RAIL3", pedido="ALLL3", trocado=True)
    monkeypatch.setattr(brapi.logger, "disabled", False)
    with caplog.at_level(logging.INFO):
        cotacoes = brapi.extrair({"results": [item]})
    assert set(cotacoes) == {"RAIL3"}
    assert "ALLL3" in caplog.text and "RAIL3" in caplog.text


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
    """Fornecedor de mentira. `hora_e_do_negocio` como o de verdade declara."""

    nome: str
    horas: dict[str, datetime]
    hora_e_do_negocio: bool = True
    # Para quem chegou a ser perguntado, e por quais papeis.
    pedidos: list[list[str]] = field(default_factory=list)

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        self.pedidos.append(list(tickers))
        return {
            t: Cotacao(t, Decimal("10"), self.nome, self.horas[t])
            for t in tickers
            if t in self.horas
        }


@dataclass(frozen=True)
class Quebrado:
    nome: str = "quebrado"
    hora_e_do_negocio: bool = True

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        raise RuntimeError("bug no adaptador")


def test_fica_com_a_cotacao_de_hora_mais_nova_independente_da_ordem() -> None:
    """Entre relogios que medem a mesma coisa, a hora mais nova ganha."""
    cedo = datetime(2026, 9, 14, 15, 45, tzinfo=UTC)
    tarde = datetime(2026, 9, 14, 16, 0, tzinfo=UTC)
    um = Fixo("um", {"PETR4": cedo, "VALE3": tarde})
    outro = Fixo("outro", {"PETR4": tarde, "VALE3": cedo})

    escolhidas = ProvedorMaisRecente((um, outro)).cotacoes(["PETR4", "VALE3"])

    assert escolhidas["PETR4"].fonte == "outro"
    assert escolhidas["VALE3"].fonte == "um"


def test_empate_fica_com_o_primeiro_fornecedor() -> None:
    primeiro = Fixo("primeiro", {"PETR4": HORA})
    segundo = Fixo("segundo", {"PETR4": HORA})
    assert ProvedorMaisRecente((primeiro, segundo)).cotacoes(["PETR4"])["PETR4"].fonte == "primeiro"


def test_um_fornecedor_quebrado_nao_impede_os_outros() -> None:
    provedor = ProvedorMaisRecente((Quebrado(), Fixo("yahoo", {"PETR4": HORA})))
    assert provedor.cotacoes(["PETR4", "VALE3"])["PETR4"].fonte == "yahoo"


# --- Hora nao confiavel: a reserva ----------------------------------------------


def test_hora_nao_confiavel_nao_ganha_de_quem_respondeu() -> None:
    """O caso de 23/09/2026: a brapi carimba "agora" e venceria por isso.

    Com dado da vespera carimbado como agora, a versao antiga -- que comparava
    todas as horas -- escolhia a brapi e o alerta podia disparar com o preco de
    ontem. Agora ela nem disputa.
    """
    agora = datetime(2026, 9, 23, 13, 19, 30, tzinfo=UTC)
    ultimo_negocio = datetime(2026, 9, 23, 13, 10, 14, tzinfo=UTC)
    brapi = Fixo("brapi", {"VIVA3": agora}, hora_e_do_negocio=False)
    yahoo = Fixo("yahoo", {"VIVA3": ultimo_negocio})

    escolhidas = ProvedorMaisRecente((brapi, yahoo)).cotacoes(["VIVA3"])

    assert escolhidas["VIVA3"].fonte == "yahoo"
    assert escolhidas["VIVA3"].hora == ultimo_negocio


def test_a_reserva_so_e_perguntada_pelo_que_faltou() -> None:
    """Preencher ausencia e o que ela ainda faz bem -- e gasta menos cota."""
    brapi = Fixo("brapi", {"PETR4": HORA, "VALE3": HORA}, hora_e_do_negocio=False)
    yahoo = Fixo("yahoo", {"PETR4": HORA})

    escolhidas = ProvedorMaisRecente((brapi, yahoo)).cotacoes(["PETR4", "VALE3"])

    assert escolhidas["PETR4"].fonte == "yahoo"
    assert escolhidas["VALE3"].fonte == "brapi"
    # O papel que o Yahoo respondeu nao chega a ser pedido a brapi.
    assert brapi.pedidos == [["VALE3"]]


def test_reserva_nao_e_consultada_quando_nada_falta() -> None:
    """Nenhuma requisicao, nao uma requisicao descartada."""
    brapi = Fixo("brapi", {"PETR4": HORA}, hora_e_do_negocio=False)
    yahoo = Fixo("yahoo", {"PETR4": HORA})

    ProvedorMaisRecente((brapi, yahoo)).cotacoes(["PETR4"])

    assert brapi.pedidos == []


def test_so_reserva_ainda_responde() -> None:
    """Sem nenhum fornecedor de hora confiavel, a reserva cobre tudo.

    E o que acontece se o Yahoo cair: melhor um preco com hora duvidosa do que
    alerta nenhum. A hora vai na mensagem para quem le saber de quando e.
    """
    brapi = Fixo("brapi", {"PETR4": HORA}, hora_e_do_negocio=False)
    assert ProvedorMaisRecente((brapi,)).cotacoes(["PETR4"])["PETR4"].fonte == "brapi"


# --- A cota da brapi ------------------------------------------------------------


def _resposta_com_cota(restantes: str | None, limite: str | None = "15000") -> httpx.Response:
    cabecalhos = {}
    if restantes is not None:
        cabecalhos["x-ratelimit-remaining"] = restantes
    if limite is not None:
        cabecalhos["x-ratelimit-limit"] = limite
    return httpx.Response(200, json={"results": []}, headers=cabecalhos)


def test_cota_sai_dos_cabecalhos_da_resposta() -> None:
    cota = brapi.ler_cota({"x-ratelimit-remaining": "14231", "x-ratelimit-limit": "15000"})
    assert cota == Cota(14231, 15000)
    assert cota.resumo() == "14.231/15.000"


@pytest.mark.parametrize(
    "cabecalhos",
    [{}, {"x-ratelimit-remaining": "muitas"}, {"x-ratelimit-limit": ""}],
)
def test_cabecalho_ausente_ou_estranho_nao_vira_cota(cabecalhos: dict[str, str]) -> None:
    """Fornecedor que muda o formato nao pode derrubar a checagem."""
    assert brapi.ler_cota(cabecalhos).vazia


def test_cota_parcial_ainda_serve() -> None:
    assert brapi.ler_cota({"x-ratelimit-remaining": "7"}).resumo() == "7"
    assert brapi.ler_cota({"x-ratelimit-limit": "15000"}).resumo() == "?/15.000"


def test_cliente_guarda_a_cota_da_ultima_resposta(monkeypatch: pytest.MonkeyPatch) -> None:
    respostas = iter([_resposta_com_cota("14231"), _resposta_com_cota("14230")])

    monkeypatch.setattr(brapi.httpx, "get", _falso_get([], lambda url: next(respostas)))

    cliente = BrapiClient(token=TOKEN)
    assert cliente.cota.vazia
    cliente.cotacoes(["PETR4", "VALE3"])
    assert cliente.cota == Cota(14230, 15000)


def test_cota_e_lida_tambem_quando_a_brapi_recusa(monkeypatch: pytest.MonkeyPatch) -> None:
    """O 429 carrega o numero, e e nele que saber quanto sobrou importa."""
    recusa = httpx.Response(
        429,
        json={"erro": "cota"},
        headers={"x-ratelimit-remaining": "0", "x-ratelimit-limit": "15000"},
    )
    monkeypatch.setattr(brapi.httpx, "get", _falso_get([], lambda url: recusa))

    cliente = BrapiClient(token=TOKEN)
    assert cliente.cotacoes(["PETR4"]) == {}
    assert cliente.cota == Cota(0, 15000)


def test_cota_baixa_sobe_para_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(brapi.httpx, "get", _falso_get([], lambda url: _resposta_com_cota("40")))
    with caplog.at_level(logging.INFO, logger="scanner.cotacoes.brapi"):
        BrapiClient(token=TOKEN).cotacoes(["PETR4"])
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    assert "cota baixa" in caplog.text


def test_a_cota_nao_muda_a_identidade_do_cliente() -> None:
    """A caixa mutavel nao pode quebrar a igualdade da dataclass congelada."""
    assert BrapiClient(token=TOKEN) == BrapiClient(token=TOKEN)


def test_provedor_junta_as_cotas_de_quem_reporta() -> None:
    cliente = BrapiClient(token=TOKEN)
    provedor = ProvedorMaisRecente((cliente, YahooClient()))
    assert provedor.cotas == ()

    cliente._cota.valor = Cota(14231, 15000)
    assert provedor.cotas == (("brapi", Cota(14231, 15000)),)


def test_relatorio_mostra_a_cota_na_linha_de_log() -> None:
    from scanner.rompimentos import RelatorioDeChecagem

    relatorio = RelatorioDeChecagem(
        ativos=4,
        consultados=4,
        sem_cotacao=0,
        disparados=1,
        fontes=(("yahoo", 4),),
        cotas=(("brapi", Cota(14231, 15000)),),
    )
    assert relatorio.summary().endswith("; cota brapi 14.231/15.000")
    # Sem cota reportada a linha fica exatamente como era antes.
    assert "cota" not in RelatorioDeChecagem(4, 4, 0, 1, fontes=(("yahoo", 4),)).summary()


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
