"""Setups classicos no pregao diario (secao 14 do plano, fase 3).

- `setups_classicos`: as linhas no formato da tabela `setups`;
- `avancar_pela_saida`: o "em andamento" pela saida escolhida, com a conta do
  backtest;
- preferencias: o que o usuario liga no app sobre o padrao do `config.yaml`.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine, delete, select

from scanner.config import ScannerConfig, SetupsConfig
from scanner.gatilhos.regra import analisar, setups_classicos
from scanner.setups import avancar_pela_saida, preferencias, run_setups
from scanner.storage.repository import gravar_preferencia
from tests.gatilhos_sinteticos import barras

Barra = tuple[float, float, float, float]
CFG = ScannerConfig()


def _frame(barras: list[Barra], ticker: str = "AAAA3") -> pd.DataFrame:
    datas = pd.bdate_range("2025-01-02", periods=len(barras))
    return pd.DataFrame(
        {
            "ticker": ticker,
            "trade_date": datas.date,
            "open": [b[0] for b in barras],
            "high": [b[1] for b in barras],
            "low": [b[2] for b in barras],
            "close": [b[3] for b in barras],
            "volume_financial": 2_000_000.0,
        }
    )


def _plano(n: int = 90) -> list[Barra]:
    # oscila pouco em torno de 10, para nenhum classico armar por acaso no fim
    rng = np.random.default_rng(0)
    c = 10 + rng.normal(0, 0.02, n).cumsum() * 0.1
    return [(x, x + 0.05, x - 0.05, x) for x in c]


UM_DOIS_TRES: list[Barra] = [(10.0, 10.2, 9.7, 9.9), (9.9, 10.0, 9.5, 9.8), (9.8, 10.3, 9.6, 10.2)]


def test_123_vira_linha_da_tabela() -> None:
    b = _frame(_plano() + UM_DOIS_TRES)
    a = analisar(b, CFG.setups, CFG.universe)
    linhas = setups_classicos(a, CFG.setups)
    dia = b["trade_date"].iloc[-1]
    linha = linhas[(linhas["categoria"] == "123") & (linhas["trade_date"] == dia)].iloc[0]
    assert linha["maxima"] == pytest.approx(10.3)
    assert linha["minima"] == pytest.approx(9.5)  # a minima do candle do meio
    assert linha["suporte_tipo"] == "minima" and linha["suporte"] == pytest.approx(9.5)
    assert linha["risco_pct"] == pytest.approx((10.2 - 9.5) / 10.2 * 100)
    assert linha["padroes"] == [] and linha["toques"] == 0
    assert linha["rvol"] == pytest.approx(1.0)
    assert linha["alta"] in (True, False)


def test_123_no_suporte_vira_linha_com_o_nivel() -> None:
    """A linha do 123 no suporte guarda o nivel tocado e os toques dele, e nao a
    minima do padrao (pedido de 09/11/2026)."""
    b = barras(martelo=False, extra=[(10.0, 10.4, 10.1, 10.3)])
    a = analisar(b, CFG.setups, CFG.universe)
    linhas = setups_classicos(a, CFG.setups)
    dia = b["trade_date"].iloc[-1]
    do_dia = linhas[linhas["trade_date"] == dia]
    linha = do_dia[do_dia["categoria"] == "123_suporte"].iloc[0]
    assert linha["suporte_tipo"] == "nivel"
    assert linha["suporte"] == pytest.approx(10.0, abs=0.1)
    assert linha["toques"] >= 3
    assert linha["minima"] == pytest.approx(9.95)  # a minima do candle do meio
    # o 123 de sempre arma no mesmo dia, como antes
    assert (do_dia["categoria"] == "123").any()


def test_contracao_vira_linha_com_a_maxima_do_bloco() -> None:
    """Na contracao o gatilho e a maxima do ultimo bloco de 10 pregoes: e ela que
    vai para a coluna `maxima`, de onde o alerta e a confirmacao tiram o preco."""
    barras: list[Barra] = [(x, x + 0.05, x - 0.05, x) for x in np.linspace(10.0, 20.0, 60)]
    for fundo, topo in ((18.0, 22.0), (20.0, 22.0), (21.0, 22.0)):
        for i in range(10):
            o, c = (fundo, topo) if i % 2 == 0 else (topo, fundo)
            barras.append((o, topo, fundo, c))
    # o ultimo pregao fica no meio do bloco: a maxima do dia NAO e a do bloco
    barras[-1] = (21.4, 21.6, 21.3, 21.5)
    b = _frame(barras)
    a = analisar(b, CFG.setups, CFG.universe)
    linhas = setups_classicos(a, CFG.setups)
    dia = b["trade_date"].iloc[-1]
    linha = linhas[(linhas["categoria"] == "contracao") & (linhas["trade_date"] == dia)].iloc[0]
    assert linha["maxima"] == pytest.approx(22.0)
    assert linha["minima"] == pytest.approx(21.0)
    assert linha["suporte_tipo"] == "minima"
    assert linha["risco_pct"] == pytest.approx((21.5 - 21.0) / 21.5 * 100)


def test_papel_iliquido_nao_arma() -> None:
    b = _frame(_plano() + UM_DOIS_TRES).assign(volume_financial=10_000.0)
    a = analisar(b, CFG.setups, CFG.universe)
    assert setups_classicos(a, CFG.setups).empty


def _aberto(
    b: pd.DataFrame, dia_do_candle: date, saida: str, *, maxima: float, minima: float
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": 1,
                "ticker": "AAAA3",
                "trade_date": dia_do_candle,
                "categoria": "123",
                "maxima": maxima,
                "minima": minima,
                "estado": "armado",
                "confirmado_em": None,
                "entrada": None,
                "saida_regra": saida,
            }
        ]
    )


def _avanca(depois: list[Barra], saida: str) -> pd.DataFrame:
    barras = _plano() + UM_DOIS_TRES + depois
    b = _frame(barras)
    dia_do_candle = b["trade_date"].iloc[len(_plano()) + 2]
    a = analisar(b, CFG.setups, CFG.universe)
    return avancar_pela_saida(_aberto(b, dia_do_candle, saida, maxima=10.3, minima=9.5), a)


def test_sem_pregao_seguinte_continua_armado() -> None:
    assert _avanca([], "alvo2").empty


def test_nao_passou_da_maxima_nao_confirmou() -> None:
    m = _avanca([(10.2, 10.3, 10.0, 10.1)], "alvo2").iloc[0]
    assert m["estado"] == "nao_confirmou"
    assert m["confirmado_em"] is None and m["encerrado_em"] is not None


def test_confirma_um_centavo_acima_e_vai_ao_alvo() -> None:
    # gatilho 10,31, stop 9,49 -> R = 0,82; alvo 2R = 11,95
    depois = [(10.25, 10.6, 10.2, 10.5), (10.5, 11.2, 10.4, 11.1), (11.1, 12.1, 11.0, 12.0)]
    m = _avanca(depois, "alvo2").iloc[0]
    assert m["estado"] == "alvo"
    assert m["entrada"] == pytest.approx(10.31)
    assert m["saida"] == pytest.approx(10.31 + 2 * (10.31 - 9.49))


def test_abriu_acima_do_gatilho_entra_na_abertura() -> None:
    m = _avanca([(10.5, 10.7, 10.4, 10.6)], "alvo2").iloc[0]
    assert m["estado"] == "confirmado" and m["entrada"] == pytest.approx(10.5)


def test_minima_no_stop_encerra_no_stop() -> None:
    depois = [(10.25, 10.6, 10.2, 10.5), (10.4, 10.45, 9.4, 9.6)]
    m = _avanca(depois, "alvo3").iloc[0]
    assert m["estado"] == "stop" and m["saida"] == pytest.approx(9.49)


def test_mme9_virando_encerra_na_abertura_seguinte() -> None:
    sobe = [(10.25 + 0.2 * i, 10.6 + 0.2 * i, 10.2 + 0.2 * i, 10.5 + 0.2 * i) for i in range(12)]
    vira = [(12.7, 12.75, 11.6, 11.7), (11.65, 11.8, 11.5, 11.6)]
    m = _avanca(sobe + vira, "mme9").iloc[0]
    assert m["estado"] == "mme9"
    assert m["saida"] == pytest.approx(11.65)  # a abertura do dia seguinte a virada


@pytest.fixture
def sem_preferencias(engine: Engine) -> None:
    from scanner.storage.models import PriceAlert, Setup, SetupPreferencia

    with engine.begin() as conn:
        conn.execute(delete(SetupPreferencia))
        conn.execute(delete(PriceAlert).where(PriceAlert.setup_id.is_not(None)))
        conn.execute(delete(Setup))


@pytest.mark.db
@pytest.mark.usefixtures("sem_preferencias")
def test_preferencia_do_app_vale_sobre_o_padrao(engine: Engine) -> None:
    cfg = SetupsConfig()
    p = preferencias(engine, cfg)
    assert p["forca"].alerta and p["forca"].saida == "mme9"  # padrao: firme no backtest
    assert not p["123"].alerta
    gravar_preferencia(engine, "123", alerta=True, saida="alvo1")
    gravar_preferencia(engine, "forca", alerta=False, saida="minimas")
    p = preferencias(engine, cfg)
    assert p["123"].alerta and p["123"].saida == "alvo1"
    assert not p["forca"].alerta and p["forca"].saida == "minimas"


@pytest.mark.db
@pytest.mark.usefixtures("sem_preferencias")
def test_alerta_e_saida_do_classico_seguem_a_preferencia(engine: Engine) -> None:
    from scanner.storage.models import PriceAlert, Setup

    b = _frame(_plano() + UM_DOIS_TRES)
    dia = b["trade_date"].iloc[-1]
    um_dois_tres = select(Setup).where(Setup.categoria == "123", Setup.trade_date == dia)

    rel = run_setups(engine, CFG, dia, bars=b)
    assert rel.classicos.get("123") == 1
    with engine.connect() as conn:
        linha = conn.execute(um_dois_tres).one()._mapping
        sem_alerta = conn.execute(
            select(PriceAlert).where(PriceAlert.setup_id == linha["id"])
        ).all()
    assert linha["saida_regra"] == "alvo3" and linha["ao_vivo"]  # padrao do 123
    assert sem_alerta == []  # 123 comeca com alerta desligado

    with engine.begin() as conn:
        conn.execute(delete(Setup))
    gravar_preferencia(engine, "123", alerta=True, saida="minimas")
    run_setups(engine, CFG, dia, bars=b)
    with engine.connect() as conn:
        linha = conn.execute(um_dois_tres).one()._mapping
        alerta = (
            conn.execute(select(PriceAlert).where(PriceAlert.setup_id == linha["id"]))
            .one()
            ._mapping
        )
    assert linha["saida_regra"] == "minimas"
    assert float(alerta["preco"]) == pytest.approx(10.31)


@pytest.mark.db
@pytest.mark.usefixtures("sem_preferencias")
def test_passado_so_entra_para_setup_com_alerta_ligado(engine: Engine) -> None:
    from sqlalchemy import func

    from scanner.storage.models import Setup

    # um 123 no meio da janela e outro no ultimo pregao (a serie aleatoria faz outros)
    b = _frame(_plano(60) + UM_DOIS_TRES + _plano(30) + UM_DOIS_TRES)
    dia = b["trade_date"].iloc[-1]
    contar = select(func.count()).select_from(Setup).where(Setup.categoria == "123")

    run_setups(engine, CFG, dia, bars=b)  # 123 sem alerta: so o de hoje
    with engine.connect() as conn:
        assert conn.execute(contar).scalar_one() == 1

    with engine.begin() as conn:
        conn.execute(delete(Setup))
    gravar_preferencia(engine, "123", alerta=True, saida="alvo3")
    run_setups(engine, CFG, dia, bars=b)  # com alerta: a janela inteira
    meio = b["trade_date"].iloc[62]
    with engine.connect() as conn:
        assert conn.execute(contar).scalar_one() > 1
        assert conn.execute(contar.where(Setup.trade_date == meio)).scalar_one() == 1


def test_grupamento_no_meio_do_trade_nao_estraga_o_resultado() -> None:
    """Regressao: ENJU3 fez grupamento de 10 para 1 em 09/10/2026, no dia da
    confirmacao de um 9.4. Os precos da linha ficam cada um na escala do proprio
    dia; o R feito com eles misturava as escalas. O pipeline faz o R na escala
    ajustada e grava em `resultado_r`."""
    custo = 0.0008
    # confirma a 10,31 (stop 9,49, R = 0,82) e no dia seguinte o papel agrupa 10:1
    depois = [(10.25, 10.6, 10.2, 10.5), (105.0, 106.0, 104.0, 105.5)]
    m = _avanca(depois, "mme9").iloc[0]
    assert m["estado"] == "confirmado"  # o stop nao "disparou" com a escala nova
    esperado = (10.55 * (1 - custo) - 10.31 * (1 + custo)) / (10.31 - 9.49)
    assert float(m["resultado_r"]) == pytest.approx(esperado, abs=1e-3)


def test_resultado_r_do_encerrado_e_o_do_backtest() -> None:
    depois = [(10.25, 10.6, 10.2, 10.5), (10.5, 11.2, 10.4, 11.1), (11.1, 12.1, 11.0, 12.0)]
    m = _avanca(depois, "alvo2").iloc[0]
    alvo = 10.31 + 2 * (10.31 - 9.49)
    esperado = (alvo * (1 - 0.0008) - 10.31 * (1 + 0.0008)) / (10.31 - 9.49)
    assert float(m["resultado_r"]) == pytest.approx(esperado, abs=1e-3)
