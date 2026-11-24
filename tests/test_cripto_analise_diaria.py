"""A rodada da noite da pagina Analise, ponta a ponta no banco de teste."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine, func, select, text

from scanner.cripto import analise_diaria
from scanner.cripto.commodities import Contrato
from scanner.storage.models import (
    SCHEMA,
    AnaliseAnual,
    AnaliseCesta,
    AnaliseJanela,
    AnaliseJanelaAno,
    AnaliseMensal,
    AnaliseMoeda,
    AnaliseMovel,
)
from scanner.storage.repository import ler_historicos_de_cripto

pytestmark = pytest.mark.db

ONTEM = date(2026, 11, 23)


def _barras(moeda: str, desde: date, ate: date) -> pd.DataFrame:
    rng = np.random.default_rng(abs(hash(moeda)) % 1000)
    # A NVDAB estreia em julho de 2026, como as acoes tokenizadas da Binance.
    comeco = date(2026, 7, 1) if moeda == "NVDAB" else date(2025, 1, 1)
    dias = pd.date_range(max(desde, comeco), ate, freq="D")
    preco = {"BTC": 50_000.0, "USDC": 1.0}.get(moeda, 2.0)
    passos = rng.normal(0, 0.0005 if moeda == "USDC" else 0.03, len(dias))
    return pd.DataFrame(
        {"trade_date": dias, "close": preco * np.cumprod(1 + passos), "volume_financial": 1e6}
    )


class Busca:
    def __init__(self, ate: date = ONTEM) -> None:
        self.pedidos: list[tuple[str, date]] = []
        self.ate = ate

    def __call__(self, moeda: str, par: str, desde: date) -> pd.DataFrame:
        self.pedidos.append((moeda, desde))
        return _barras(moeda, desde, self.ate)


@pytest.fixture
def limpo(engine: Engine) -> Engine:
    with engine.begin() as conn:
        for tabela in (
            "analise_movel",
            "analise_mensal",
            "analise_anual",
            "analise_moedas",
            "analise_cesta",
            "analise_janelas",
            "analise_janela_anos",
        ):
            conn.execute(text(f"DELETE FROM {SCHEMA}.{tabela}"))
    return engine


PARES = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "USDC": "USDCUSDT", "NVDAB": "NVDABUSDT"}


def _rodar(
    engine: Engine, busca: Busca, ontem: date = ONTEM, **kw: bool
) -> analise_diaria.RelatorioDaAnalise:
    return analise_diaria.rodar(
        engine,
        ontem=ontem,
        pares=PARES,
        negociando=set(PARES),
        binance=busca,
        kraken=Busca(),
        fora_da_binance={},
        **kw,
    )


def _contar(engine: Engine, modelo: type) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(modelo)).scalar_one())


def test_primeira_rodada_grava_as_quatro_tabelas(limpo: Engine) -> None:
    rel = _rodar(limpo, Busca())
    assert rel.na_conta == 2
    assert rel.fora == {"estavel": ["USDC"], "acao tokenizada": ["NVDAB"]}
    assert _contar(limpo, AnaliseMoeda) == 4
    assert _contar(limpo, AnaliseAnual) == rel.linhas["anual"] > 0
    assert _contar(limpo, AnaliseMensal) == rel.linhas["mensal"] > 0
    assert _contar(limpo, AnaliseMovel) == rel.linhas["movel"] > 0
    with limpo.connect() as conn:
        usdc = conn.execute(
            select(AnaliseMoeda.fora_por, AnaliseMoeda.volume_12m).where(
                AnaliseMoeda.moeda == "USDC"
            )
        ).one()
        btc_2026 = conn.execute(
            select(AnaliseAnual.relativo, AnaliseAnual.parcial).where(
                AnaliseAnual.moeda == "BTC", AnaliseAnual.ano == 2026
            )
        ).one()
        moedas_na_anual = set(conn.execute(select(AnaliseAnual.moeda).distinct()).scalars())
    assert usdc.fora_por == "estavel"
    assert usdc.volume_12m is None
    assert btc_2026.relativo == pytest.approx(0.0, abs=1e-12)
    assert btc_2026.parcial
    assert moedas_na_anual == {"BTC", "ETH"}


def test_o_estado_volta_do_banco_igual_inclusive_os_dias_vazios(limpo: Engine) -> None:
    _rodar(limpo, Busca())
    estado = ler_historicos_de_cripto(limpo)
    eth = estado["ETH"]
    assert eth.ultimo_dia == ONTEM
    assert eth.primeiro_dia == date(2025, 1, 1)
    assert eth.serie().notna().all()


def test_a_noite_seguinte_so_pede_o_dia_novo(limpo: Engine) -> None:
    _rodar(limpo, Busca(ate=date(2026, 11, 22)), ontem=date(2026, 11, 22))
    busca = Busca()
    rel = _rodar(limpo, busca)
    assert set(busca.pedidos) == {(m, ONTEM) for m in PARES}
    assert rel.carga is not None and rel.carga.atualizadas == 4
    assert ler_historicos_de_cripto(limpo)["BTC"].ultimo_dia == ONTEM


def test_so_se_faltar_nao_refaz_o_que_ja_foi_gravado(limpo: Engine) -> None:
    _rodar(limpo, Busca())
    busca = Busca()
    rel = _rodar(limpo, busca, so_se_faltar=True)
    assert rel.pronto
    assert busca.pedidos == []
    assert "nada a fazer" in rel.summary()


def test_dry_run_calcula_sem_gravar(limpo: Engine) -> None:
    rel = _rodar(limpo, Busca(), dry_run=True)
    assert rel.linhas["anual"] > 0
    assert _contar(limpo, AnaliseMoeda) == 0
    assert rel.summary().startswith("[dry-run]")


def test_resumo_diz_quem_ficou_de_fora_e_por_que(limpo: Engine) -> None:
    texto = _rodar(limpo, Busca()).summary()
    assert "2 criptos e 0 commodities na conta (2 fora: 1 acao tokenizada, 1 estavel)" in texto
    assert "[analise] fora (estavel): USDC" in texto
    assert "[analise] fora (acao tokenizada): NVDAB" in texto


def test_o_estudo_sazonal_vai_junto_na_mesma_rodada(limpo: Engine) -> None:
    rel = analise_diaria.rodar(
        limpo,
        ontem=ONTEM,
        pares=PARES,
        negociando=set(PARES),
        binance=Busca(),
        kraken=Busca(),
        fora_da_binance={},
        periodos=((2025, 2025), (2026, 2026)),
    )
    assert _contar(limpo, AnaliseCesta) == rel.linhas["cesta"] > 0
    assert _contar(limpo, AnaliseJanela) == rel.linhas["janelas"] == 2 * 12 * 6
    assert _contar(limpo, AnaliseJanelaAno) == rel.linhas["janela_anos"] > 0
    texto = rel.summary()
    assert "[estudo] compra: " in texto
    assert "[estudo] venda: " in texto


def test_commodities_entram_contra_o_btc_mas_fora_da_cesta(limpo: Engine) -> None:
    pares = {**PARES, "PAXG": "PAXGUSDT"}
    futuros = Busca(ate=date(2026, 11, 22))  # o arquivo de futuros atrasa um dia
    rel = analise_diaria.rodar(
        limpo,
        ontem=ONTEM,
        pares=pares,
        negociando=set(pares),
        binance=Busca(),
        kraken=Busca(),
        fora_da_binance={},
        futuros=futuros,
        contratos={"XAU": Contrato("XAUUSDT", date(2025, 3, 1))},
        periodos=((2025, 2025), (2026, 2026)),
    )
    assert futuros.pedidos == [("XAU", date(2025, 3, 1))]
    assert (rel.na_conta, rel.commodities) == (4, 2)
    assert "2 criptos e 2 commodities na conta" in rel.summary()
    with limpo.connect() as conn:
        grupos = dict(conn.execute(select(AnaliseMoeda.moeda, AnaliseMoeda.grupo)).all())
        fora_por = dict(conn.execute(select(AnaliseMoeda.moeda, AnaliseMoeda.fora_por)).all())
        na_anual = set(conn.execute(select(AnaliseAnual.moeda).distinct()).scalars())
        cesta = conn.execute(select(func.max(AnaliseCesta.moedas))).scalar_one()
        xau = conn.execute(
            select(AnaliseMoeda.fonte, AnaliseMoeda.ultimo_dia).where(AnaliseMoeda.moeda == "XAU")
        ).one()
    assert grupos == {
        "BTC": "cripto",
        "ETH": "cripto",
        "USDC": "cripto",
        "NVDAB": "cripto",
        "PAXG": "commodity",
        "XAU": "commodity",
    }
    # O PAXG e "embrulhado" no backtest; na analise ele entra, como commodity.
    assert fora_por["PAXG"] is None
    assert na_anual == {"BTC", "ETH", "PAXG", "XAU"}
    # A cesta do estudo continua so cripto: BTC e ETH.
    assert cesta == 2
    assert xau.fonte == "binance-futuros"
    assert xau.ultimo_dia == date(2026, 11, 22)
