"""Setups, fase 2: alerta de confirmacao, validade e mensagens do Telegram."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import Engine, delete, select

from scanner.config import ScannerConfig
from scanner.cotacoes.base import Cotacao
from scanner.digest import Resumo, payload_do_resumo
from scanner.notify.telegram import ConsoleNotifier, format_resumo, format_rompimento
from scanner.rompimentos import Alerta, Disparo, checar_rompimentos, payload_do_disparo
from scanner.setups import run_setups
from scanner.storage.repository import alertas_ativos, apagar_alerta, criar_alerta
from tests.gatilhos_sinteticos import barras, dia_do_martelo

BASE = "https://scanner.exemplo"
CANDLE = date(2026, 10, 20)
SETUP = {
    "id": 7,
    "ticker": "SAPR11",
    "trade_date": CANDLE,
    "categoria": "reversao",
    "padroes": ["martelo"],
    "rvol": Decimal("2.3187"),
    "destaque": False,
    "maxima": Decimal("40.0000"),
    "minima": Decimal("38.4600"),
    "risco_pct": Decimal("3.850"),
    "resistencia": Decimal("45.1267"),
    "espaco_r": Decimal("3.33"),
    "estado": "armado",
    "confirmado_em": None,
    "entrada": None,
}


def _disparo(setup: dict[str, object] | None) -> dict[str, object]:
    alerta = Alerta(
        id=1,
        ticker="SAPR11",
        trade_date=CANDLE,
        preco=Decimal("40.01"),
        direcao="acima",
        criado_em=datetime(2026, 10, 20, 23, 0, tzinfo=UTC),
        expira_em=date(2026, 10, 21),
        setup_id=7 if setup else None,
    )
    cot = Cotacao("SAPR11", Decimal("40.05"), "yahoo", datetime(2026, 10, 21, 13, 42, tzinfo=UTC))
    return payload_do_disparo(Disparo(alerta, cot), setup)


def test_mensagem_do_setup_confirmado() -> None:
    texto = format_rompimento(_disparo(SETUP), BASE)
    assert "SAPR11 confirmou o setup" in texto
    assert "máxima do martelo de 20/10 (R$ 40,00)" in texto
    assert "R$ 40,05 às 10:42 · yahoo" in texto
    assert "mínima do padrão R$ 38,46" in texto
    assert "resistência R$ 45,13 (3,3R)" in texto
    assert "<pre>" not in texto  # no iPhone o bloco de codigo cobre os numeros


def test_alerta_manual_continua_com_a_mensagem_de_sempre() -> None:
    texto = format_rompimento(_disparo(None), BASE)
    assert "SAPR11 subiu até R$ 40,01" in texto
    assert "setup" not in texto


def _resumo_com(setups: pd.DataFrame) -> str:
    resumo = Resumo(
        CANDLE,
        pd.DataFrame(
            {
                "ticker": ["PETR4"],
                "z_log": [6.2],
                "close": [38.0],
                "ret_day": [0.01],
                "volume_financial": [9e8],
            }
        ),
        1,
        1,
        6.0,
        None,
    )
    return format_resumo(payload_do_resumo(resumo, None, setups), BASE)


def test_resumo_ganha_o_bloco_de_setups_armados() -> None:
    forca = {**SETUP, "id": 8, "ticker": "CYRE4", "categoria": "forca", "padroes": ["forca"]}
    confirmado = {
        **SETUP,
        "id": 9,
        "ticker": "VBBR3",
        "trade_date": date(2026, 10, 17),
        "estado": "confirmado",
        "confirmado_em": CANDLE,
        "entrada": Decimal("36.98"),
    }
    texto = _resumo_com(pd.DataFrame([SETUP, forca, confirmado]))
    assert "<b>Setups armados</b>" in texto
    assert "SAPR11</a></b> martelo" in texto
    assert "acima de R$ 40,00" in texto
    assert "Candle de força (não passou na conferência)" in texto and "CYRE4" in texto
    assert "Confirmados hoje:" in texto and "VBBR3" in texto and "R$ 36,98" in texto
    assert texto.count("<pre>") == 1  # so a tabela de sempre; o bloco novo e lista
    assert f'<a href="{BASE}/setups/">abrir setups</a>' in texto


def test_resumo_sem_setups_fica_igual() -> None:
    sem = _resumo_com(pd.DataFrame(columns=list(SETUP)))
    assert "Setups" not in sem


def test_destaque_tem_marca_propria() -> None:
    texto = _resumo_com(pd.DataFrame([{**SETUP, "destaque": True}]))
    assert "★ <b>" in texto


@pytest.fixture
def limpo(engine: Engine) -> None:
    from scanner.storage.models import Nivel, PriceAlert, Setup

    with engine.begin() as conn:
        conn.execute(delete(PriceAlert).where(PriceAlert.setup_id.is_not(None)))
        conn.execute(delete(Setup))
        conn.execute(delete(Nivel))


@pytest.mark.db
@pytest.mark.usefixtures("limpo")
def test_armado_ao_vivo_ganha_alerta_que_vale_um_pregao(engine: Engine) -> None:
    from scanner.storage.models import PriceAlert, Setup

    noite = barras()
    dia = dia_do_martelo(noite)
    assert isinstance(dia, date)
    rel = run_setups(engine, ScannerConfig(), dia, bars=noite)
    assert rel.alertas == 1
    with engine.connect() as conn:
        alerta = (
            conn.execute(select(PriceAlert).where(PriceAlert.setup_id.is_not(None))).one()._mapping
        )
        setup_id = conn.execute(select(Setup.id)).scalar_one()
    assert alerta["setup_id"] == setup_id
    assert alerta["preco"] == Decimal("10.49")  # um centavo acima da maxima (10,48)
    assert alerta["direcao"] == "acima"
    seguinte = pd.bdate_range(dia, periods=2)[1].date()
    assert alerta["expira_em"] == seguinte

    # vale no pregao seguinte e some depois dele
    assert alerta["id"] in {a.id for a in alertas_ativos(engine, seguinte)}
    depois = pd.bdate_range(dia, periods=3)[2].date()
    assert alerta["id"] not in {a.id for a in alertas_ativos(engine, depois)}

    # rodar a mesma noite de novo nao cria outro alerta
    assert run_setups(engine, ScannerConfig(), dia, bars=noite).alertas == 0


@pytest.mark.db
@pytest.mark.usefixtures("limpo")
def test_setup_retroativo_nao_ganha_alerta(engine: Engine) -> None:
    # noite perdida: o martelo e de ontem, a passada e de hoje -> sem alerta
    noite = barras(extra=[(10.40, 10.45, 10.20, 10.30)])
    hoje = noite["trade_date"].iloc[-1]
    rel = run_setups(engine, ScannerConfig(), hoje, bars=noite)
    assert rel.gravados == 1 and rel.alertas == 0


@pytest.mark.db
@pytest.mark.usefixtures("limpo")
def test_checagem_avisa_o_setup_confirmado(engine: Engine) -> None:
    from scanner.storage.models import PriceAlert

    noite = barras()
    dia = dia_do_martelo(noite)
    assert isinstance(dia, date)
    run_setups(engine, ScannerConfig(), dia, bars=noite)
    seguinte = pd.bdate_range(dia, periods=2)[1].date()
    with engine.connect() as conn:
        alerta_id = conn.execute(
            select(PriceAlert.id).where(PriceAlert.setup_id.is_not(None))
        ).scalar_one()

    class Provedor:
        nome = "falso"
        hora_e_do_negocio = True

        def cotacoes(self, tickers: object) -> dict[str, Cotacao]:
            hora = datetime(seguinte.year, seguinte.month, seguinte.day, 14, 5, tzinfo=UTC)
            return {"AAAA3": Cotacao("AAAA3", Decimal("10.55"), "falso", hora)}

    enviadas: list[str] = []
    rel = checar_rompimentos(
        engine, Provedor(), notifier=ConsoleNotifier(sent=enviadas), hoje=seguinte
    )
    assert rel.disparados == 1
    assert "AAAA3 confirmou o setup" in enviadas[0]
    assert alerta_id not in {a.id for a in alertas_ativos(engine, seguinte)}


@pytest.mark.db
def test_religar_tira_a_validade(engine: Engine) -> None:
    from scanner.storage.repository import marcar_disparado, reativar_alerta

    alerta_id = criar_alerta(
        engine, "PETR4", date(2026, 10, 20), Decimal("38.00"), "acima", expira_em=date(2026, 10, 21)
    )
    try:
        marcar_disparado(engine, alerta_id, preco=Decimal("38.10"), fonte="falso")
        reativar_alerta(engine, alerta_id)
        ativo = {a.id: a for a in alertas_ativos(engine, date(2026, 12, 1))}
        assert alerta_id in ativo and ativo[alerta_id].expira_em is None
    finally:
        apagar_alerta(engine, alerta_id)


def test_links_do_setup_centram_no_candle_e_nao_no_evento() -> None:
    """Regressao de 21/10/2026: com `?data=` a ficha abria no evento mais recente.

    O dia do setup quase nunca e evento de volume; a ficha caia no ultimo evento
    do papel e o grafico pulava para meses antes.
    """
    confirmado = format_rompimento(_disparo(SETUP), BASE)
    resumo = _resumo_com(pd.DataFrame([SETUP]))
    for texto in (confirmado, resumo):
        assert f"{BASE}/papel/SAPR11?foco=2026-10-20" in texto
        assert "?data=" not in texto
