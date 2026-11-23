"""A carga diaria de cripto contra o banco: ranking, candles que faltam, moeda que saiu."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, text

from scanner.config import CriptoConfig
from scanner.cripto.carga import carregar
from scanner.storage.models import SCHEMA

pytestmark = pytest.mark.db

DIA = 86_400_000
AGORA = datetime(2026, 11, 16, 0, 5, tzinfo=UTC)
ONTEM_MS = int(datetime(2026, 11, 15, tzinfo=UTC).timestamp() * 1000)
CFG = CriptoConfig(top=2, categorias_excluidas=["stablecoins"], dias_iniciais=5)


class Fontes:
    """Binance e CoinGecko de mentira; anota o que foi pedido."""

    def __init__(self, ranking: list[dict[str, Any]] | None, pares: list[str]) -> None:
        self.ranking = ranking
        self.pares = pares
        self.candles: list[tuple[str, date]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        caminho = request.url.path
        if caminho.endswith("/exchangeInfo"):
            return httpx.Response(
                200,
                json={
                    "symbols": [
                        {
                            "symbol": f"{m}USDT",
                            "baseAsset": m,
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                        }
                        for m in self.pares
                    ]
                },
            )
        if caminho.endswith("/klines"):
            de = int(request.url.params["startTime"])
            par = request.url.params["symbol"]
            self.candles.append((par, datetime.fromtimestamp(de / 1000, UTC).date()))
            corpo = [
                [t, "10", "12", "9", "11", "1000", t + DIA - 1, "10500", 42]
                for t in range(de, ONTEM_MS + 2 * DIA, DIA)  # inclui o dia em andamento
            ]
            return httpx.Response(200, json=corpo)
        if caminho.endswith("/coins/markets"):
            if self.ranking is None:
                return httpx.Response(429, headers={"Retry-After": "1"})
            if "category" in request.url.params:
                return httpx.Response(200, json=[{"id": "tether"}])
            return httpx.Response(200, json=self.ranking)
        return httpx.Response(404)


def rodar(engine: Engine, fontes: Fontes) -> str:
    with httpx.Client(transport=httpx.MockTransport(fontes)) as cliente:
        return carregar(engine, CFG, agora=AGORA, cliente=cliente, dormir=lambda _: None)


@pytest.fixture
def limpo(engine: Engine) -> Iterator[Engine]:
    """Tabelas vazias antes e depois: as barras daqui nao podem vazar para outro teste."""

    def esvaziar() -> None:
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {SCHEMA}.moedas, {SCHEMA}.daily_bars CASCADE"))

    esvaziar()
    yield engine
    esvaziar()


def _moeda(id_: str, simbolo: str, valor: float) -> dict[str, Any]:
    return {"id": id_, "symbol": simbolo, "name": simbolo.upper(), "market_cap": valor}


RANKING = [
    _moeda("bitcoin", "btc", 3.0),
    _moeda("tether", "usdt", 2.5),
    _moeda("ethereum", "eth", 2.0),
]


def _barras(engine: Engine) -> dict[str, list[date]]:
    with engine.connect() as conn:
        linhas = conn.execute(
            text(f"SELECT ticker, trade_date FROM {SCHEMA}.daily_bars ORDER BY 1, 2")
        ).all()
    saida: dict[str, list[date]] = {}
    for ticker, dia in linhas:
        saida.setdefault(ticker, []).append(dia)
    return saida


def test_primeira_carga_traz_o_historico_inicial_ate_ontem(limpo: Engine) -> None:
    fontes = Fontes(RANKING, ["BTC", "ETH", "USDT"])
    texto = rodar(limpo, fontes)
    barras = _barras(limpo)
    assert set(barras) == {"BTC", "ETH"}  # a stablecoin ficou de fora
    # 5 dias de historico inicial + ontem; o candle de hoje (aberto) nao entra.
    assert barras["BTC"][0] == date(2026, 11, 10)
    assert barras["BTC"][-1] == date(2026, 11, 15)
    assert len(barras["BTC"]) == 6
    assert "12 barras de 2 moedas" in texto and "ranking: 2 moedas" in texto


def test_segunda_carga_no_mesmo_dia_nao_pede_nada(limpo: Engine) -> None:
    rodar(limpo, Fontes(RANKING, ["BTC", "ETH"]))
    fontes = Fontes(RANKING, ["BTC", "ETH"])
    texto = rodar(limpo, fontes)
    assert fontes.candles == []
    assert "0 barras de 0 moedas" in texto


def test_so_pede_os_dias_depois_da_ultima_barra(limpo: Engine) -> None:
    rodar(limpo, Fontes(RANKING, ["BTC", "ETH"]))
    with limpo.begin() as conn:
        conn.execute(text(f"DELETE FROM {SCHEMA}.daily_bars WHERE trade_date > '2026-11-13'"))
    fontes = Fontes(RANKING, ["BTC", "ETH"])
    rodar(limpo, fontes)
    assert sorted(fontes.candles) == [
        ("BTCUSDT", date(2026, 11, 14)),
        ("ETHUSDT", date(2026, 11, 14)),
    ]
    assert _barras(limpo)["ETH"][-1] == date(2026, 11, 15)


def test_ranking_fora_do_ar_nao_derruba_a_carga(limpo: Engine) -> None:
    rodar(limpo, Fontes(RANKING, ["BTC", "ETH"]))
    with limpo.begin() as conn:
        conn.execute(text(f"DELETE FROM {SCHEMA}.daily_bars WHERE trade_date = '2026-11-15'"))
    texto = rodar(limpo, Fontes(None, ["BTC", "ETH"]))
    assert "ranking nao atualizado" in texto
    assert _barras(limpo)["BTC"][-1] == date(2026, 11, 15)


def test_moeda_que_saiu_do_ranking_continua_carregando_mas_sai_do_top(limpo: Engine) -> None:
    rodar(limpo, Fontes(RANKING, ["BTC", "ETH", "SOL"]))
    with limpo.begin() as conn:
        conn.execute(text(f"DELETE FROM {SCHEMA}.daily_bars WHERE trade_date = '2026-11-15'"))
    novo = [
        _moeda("bitcoin", "btc", 3.0),
        _moeda("solana", "sol", 2.5),
        _moeda("ethereum", "eth", 2.0),
    ]
    rodar(limpo, Fontes(novo, ["BTC", "ETH", "SOL"]))
    with limpo.connect() as conn:
        moedas = {
            t: (p, topo)
            for t, p, topo in conn.execute(
                text(f"SELECT ticker, posicao, no_top FROM {SCHEMA}.moedas")
            )
        }
    assert moedas == {"BTC": (1, True), "SOL": (2, True), "ETH": (None, False)}
    # um setup aberto em ETH precisa do candle de ontem para encerrar
    assert _barras(limpo)["ETH"][-1] == date(2026, 11, 15)


def test_par_suspenso_fica_com_as_barras_antigas_e_avisa(limpo: Engine) -> None:
    rodar(limpo, Fontes(RANKING, ["BTC", "ETH"]))
    with limpo.begin() as conn:
        conn.execute(text(f"DELETE FROM {SCHEMA}.daily_bars WHERE trade_date = '2026-11-15'"))
    texto = rodar(limpo, Fontes(None, ["BTC"]))
    assert "sem negociacao: ETH" in texto
    assert _barras(limpo)["ETH"][-1] == date(2026, 11, 14)


def test_sem_ranking_e_sem_moeda_nenhuma_e_falha(limpo: Engine) -> None:
    from scanner.semana.fontes import FonteIndisponivelError

    with pytest.raises(FonteIndisponivelError):
        rodar(limpo, Fontes(None, ["BTC"]))


class FontesComKraken(Fontes):
    """As mesmas fontes, mais a Kraken, com a XMR no ranking e fora da Binance."""

    def __init__(self, *, kraken_no_ar: bool = True) -> None:
        super().__init__([*RANKING, _moeda("monero", "xmr", 1.0)], ["BTC", "ETH"])
        self.kraken_no_ar = kraken_no_ar
        self.pedidos_xmr_na_binance = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.params.get("symbol", "").startswith("XMR"):
            self.pedidos_xmr_na_binance += 1
        if request.url.host != "api.kraken.com":
            return super().__call__(request)
        if not self.kraken_no_ar:
            return httpx.Response(200, json={"error": ["EService:Unavailable"], "result": {}})
        ontem = ONTEM_MS // 1000
        corpo = [
            [t, "500", "520", "490", "510", "505", "100", 42]
            # inclui o dia em andamento, que nao pode ser gravado
            for t in range(ontem - 4 * 86_400, ontem + 2 * 86_400, 86_400)
        ]
        return httpx.Response(200, json={"error": [], "result": {"XXMRZUSD": corpo, "last": 1}})


def test_xmr_vem_da_kraken_e_nao_tira_ninguem_das_maiores(limpo: Engine) -> None:
    fontes = FontesComKraken()
    rodar(limpo, fontes)
    barras = _barras(limpo)
    assert barras["XMR"][-1] == date(2026, 11, 15)
    assert len(barras["XMR"]) == 5
    assert {"BTC", "ETH"} <= set(barras)
    assert fontes.pedidos_xmr_na_binance == 0
    with limpo.connect() as conn:
        linha = conn.execute(
            text(f"SELECT par, no_top FROM {SCHEMA}.moedas WHERE ticker = 'XMR'")
        ).one()
    assert tuple(linha) == ("XMRUSD", True)


def test_kraken_fora_do_ar_nao_derruba_as_outras_moedas(limpo: Engine) -> None:
    relatorio = rodar(limpo, FontesComKraken(kraken_no_ar=False))
    barras = _barras(limpo)
    assert "XMR" not in barras
    assert {"BTC", "ETH"} <= set(barras)
    assert "sem negociacao: XMR" in relatorio
