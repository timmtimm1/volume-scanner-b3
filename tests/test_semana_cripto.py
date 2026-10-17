"""CoinGecko: exclusao de categorias e destaques, contra o ranking real de 17/10/2026."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from scanner.semana.fontes import FonteIndisponivelError
from scanner.semana.fontes.cripto import buscar_cripto, ids_da_categoria, montar_cripto

FIXTURES = Path(__file__).parent / "fixtures" / "semana"
MERCADO: list[dict[str, Any]] = json.loads((FIXTURES / "coingecko_mercado.json").read_text())
CATEGORIAS: dict[str, list[dict[str, Any]]] = json.loads(
    (FIXTURES / "coingecko_categorias.json").read_text()
)
EXCLUIDOS = set().union(*(ids_da_categoria(v) for v in CATEGORIAS.values()))


def test_fixture_tem_as_10_exclusoes_medidas_no_top_40() -> None:
    assert len(EXCLUIDOS) == 10
    assert {"tether", "usd-coin", "figure-heloc", "tether-gold", "paypal-usd"} <= EXCLUIDOS


def test_top_20_sem_stablecoins_nem_tokenizados() -> None:
    bloco = montar_cripto(MERCADO, EXCLUIDOS, top=20, destaques=5)

    moedas = bloco["moedas"]
    assert len(moedas) == 20
    assert not {m["id"] for m in moedas} & EXCLUIDOS
    assert [m["rank"] for m in moedas] == list(range(1, 21))
    assert moedas[0]["id"] == "bitcoin"
    assert moedas[1]["id"] == "ethereum"
    # tether (3o no ranking cru) saiu: o 3o agora e a BNB.
    assert moedas[2]["id"] == "binancecoin"
    assert moedas[2]["simbolo"] == "BNB"


def test_btc_e_eth_em_campo_proprio_com_variacao_em_fracao() -> None:
    bloco = montar_cripto(MERCADO, EXCLUIDOS, top=20, destaques=5)

    assert bloco["btc"]["id"] == "bitcoin"
    assert bloco["btc"]["variacao_7d"] == pytest.approx(-0.018915)
    assert bloco["btc"]["preco"] == 81554
    assert bloco["eth"]["variacao_7d"] == pytest.approx(-0.036205)


def test_altas_e_quedas_sem_btc_e_eth() -> None:
    bloco = montar_cripto(MERCADO, EXCLUIDOS, top=20, destaques=5)

    altas, quedas = bloco["altas"], bloco["quedas"]
    assert len(altas) == len(quedas) == 5
    ids = {m["id"] for m in altas + quedas}
    assert not ids & {"bitcoin", "ethereum"}
    assert [m["variacao_7d"] for m in altas] == sorted(
        (m["variacao_7d"] for m in altas), reverse=True
    )
    assert [m["variacao_7d"] for m in quedas] == sorted(m["variacao_7d"] for m in quedas)
    # No top 20 filtrado: maior alta a monero (+6,5885%), maior queda a rain (-14,5283%).
    assert altas[0]["id"] == "monero"
    assert altas[0]["variacao_7d"] == pytest.approx(0.065885)
    assert quedas[0]["id"] == "rain"


def test_variacao_ausente_nao_entra_nos_destaques() -> None:
    mercado: list[dict[str, Any]] = [
        {"id": "a", "symbol": "a", "name": "A", "price_change_percentage_7d_in_currency": None},
        {"id": "b", "symbol": "b", "name": "B", "price_change_percentage_7d_in_currency": 3.0},
    ]

    bloco = montar_cripto(mercado, set(), top=2, destaques=5)

    assert [m["id"] for m in bloco["altas"]] == ["b"]
    assert bloco["moedas"][0]["variacao_7d"] is None
    assert bloco["btc"] is None


def test_categoria_com_formato_errado() -> None:
    with pytest.raises(FonteIndisponivelError):
        ids_da_categoria({"status": {"error_code": 429}})


# --- busca (cliente falso, sem rede) --------------------------------------


class _Cliente:
    """Devolve respostas na ordem; guarda as URLs pedidas."""

    def __init__(self, respostas: list[httpx.Response]) -> None:
        self.respostas = list(respostas)
        self.urls: list[str] = []

    def request(self, metodo: str, url: str, **_kw: Any) -> httpx.Response:
        self.urls.append(url)
        return self.respostas.pop(0)

    def close(self) -> None:
        pass


def _ok(corpo: Any) -> httpx.Response:
    return httpx.Response(200, json=corpo)


def test_busca_consulta_ranking_e_cada_categoria_com_pausa() -> None:
    cliente = _Cliente([_ok(MERCADO), *(_ok(CATEGORIAS[c]) for c in CATEGORIAS)])
    pausas: list[float] = []

    bloco = buscar_cripto(
        categorias_excluidas=list(CATEGORIAS),
        top=20,
        destaques=5,
        agora=datetime(2026, 10, 17, 19, 0, tzinfo=UTC),
        cliente=cliente,  # type: ignore[arg-type]
        dormir=pausas.append,
    )

    assert len(cliente.urls) == 5
    assert "per_page=60" in cliente.urls[0]
    assert "price_change_percentage=7d" in cliente.urls[0]
    assert "category=stablecoins" in cliente.urls[1]
    assert pausas == [4.0, 4.0, 4.0, 4.0]
    assert bloco["coletado_em"] == "2026-10-17T19:00:00+00:00"
    assert len(bloco["moedas"]) == 20


def test_429_respeita_retry_after_e_tenta_uma_vez_mais() -> None:
    cliente = _Cliente([httpx.Response(429, headers={"Retry-After": "90"}), _ok(MERCADO)])
    pausas: list[float] = []

    bloco = buscar_cripto(
        categorias_excluidas=[],
        top=5,
        destaques=2,
        cliente=cliente,  # type: ignore[arg-type]
        dormir=pausas.append,
    )

    assert pausas == [60.0]  # Retry-After de 90 s limitado ao teto
    assert len(bloco["moedas"]) == 5


def test_dois_429_seguidos_viram_fonte_indisponivel() -> None:
    cliente = _Cliente([httpx.Response(429), httpx.Response(429)])

    with pytest.raises(FonteIndisponivelError, match="429"):
        buscar_cripto(
            categorias_excluidas=[],
            top=5,
            destaques=2,
            cliente=cliente,  # type: ignore[arg-type]
            dormir=lambda _s: None,
        )


def test_status_diferente_de_200_nao_tenta_de_novo() -> None:
    cliente = _Cliente([httpx.Response(500)])

    with pytest.raises(FonteIndisponivelError, match="500"):
        buscar_cripto(
            categorias_excluidas=[],
            top=5,
            destaques=2,
            cliente=cliente,  # type: ignore[arg-type]
            dormir=lambda _s: None,
        )
    assert len(cliente.urls) == 1
