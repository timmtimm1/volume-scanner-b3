"""O seletor de mercado: B3 por padrao, cripto por variavel de ambiente."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, date, datetime

import numpy as np
import pytest

from scanner import calendar, mercado


@pytest.fixture
def cripto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(mercado.VARIAVEL, "cripto")


def test_sem_variavel_e_a_b3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(mercado.VARIAVEL, raising=False)
    assert mercado.atual() == "b3"
    assert not mercado.e_cripto()
    assert mercado.schema() == "volume_scanner"
    assert mercado.arquivo_de_config() == "config.yaml"
    assert mercado.custo() == 0.0008
    assert mercado.periodos() == ((1995, 2015), (2016, 2026))


def test_cripto_troca_schema_config_custo_e_periodos(cripto: None) -> None:
    assert mercado.e_cripto()
    assert mercado.schema() == "cripto_scanner"
    assert mercado.arquivo_de_config() == "config-cripto.yaml"
    assert mercado.custo() == 0.0015
    assert mercado.periodos() == ((2017, 2021), (2022, 2026))
    assert mercado.moeda() == "US$"


def test_valor_desconhecido_falha_em_vez_de_cair_na_b3(monkeypatch: pytest.MonkeyPatch) -> None:
    # Um erro de digitacao ("crypto") gravaria moeda no schema das acoes.
    monkeypatch.setenv(mercado.VARIAVEL, "crypto")
    with pytest.raises(mercado.MercadoInvalidoError):
        mercado.atual()


def test_rotulos_de_periodo_cobrem_os_dois_mercados() -> None:
    assert mercado.rotulos_de_periodo() == (
        "1995-2015",
        "2016-2026",
        "2017-2021",
        "2022-2026",
        "tudo",
    )


def test_tick_da_b3_e_o_centavo_na_escala_ajustada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(mercado.VARIAVEL, raising=False)
    fechamento = np.array([[10.0, 50.0], [20.0, 25.0]])
    ajuste = np.array([[1.0, 0.5], [1.0, 1.0]])
    np.testing.assert_allclose(mercado.tick(fechamento, ajuste), 0.01 * ajuste)
    assert mercado.tick_do_preco(65_000.0) == 0.01


def test_tick_de_cripto_e_a_quinta_casa_significativa(cripto: None) -> None:
    assert mercado.tick_do_preco(65_351.05) == pytest.approx(1.0)
    assert mercado.tick_do_preco(0.52) == pytest.approx(0.00001)
    assert mercado.tick_do_preco(0.000004) == pytest.approx(1e-10)
    # Nunca passa de 10 pontos-base do preco, em nenhuma escala.
    for preco in (65_351.05, 3_120.0, 0.52, 0.000004, 9.99, 10.0):
        assert 0.00001 < mercado.tick_do_preco(preco) / preco <= 0.0001


def test_tick_de_cripto_em_matriz_herda_o_ultimo_dia_negociado(cripto: None) -> None:
    fechamento = np.array([[np.nan, 0.5], [100.0, np.nan], [np.nan, 0.6]])
    passo = mercado.tick(fechamento, np.ones_like(fechamento))
    assert np.isnan(passo[0, 0])  # antes do primeiro negocio nao ha passo
    np.testing.assert_allclose(passo[1:, 0], [0.01, 0.01])
    np.testing.assert_allclose(passo[:, 1], [0.00001, 0.00001, 0.00001])


def test_em_cripto_todo_dia_e_dia_de_negociacao(cripto: None) -> None:
    assert calendar.is_trading_day(date(2026, 11, 15))  # domingo e feriado
    assert calendar.is_trading_day(date(2019, 12, 25))  # antes de 2022, Natal
    assert calendar.next_trading_day(date(2026, 11, 14)) == date(2026, 11, 15)
    assert len(calendar.sessions_before(date(2026, 11, 16), 60)) == 60


def test_ultimo_candle_fechado_de_cripto_e_a_vespera_em_utc(cripto: None) -> None:
    # 21h05 de Brasilia do dia 15 = 00h05 UTC do dia 16: o candle do dia 15 fechou.
    depois = datetime(2026, 11, 16, 0, 5, tzinfo=UTC)
    assert calendar.ultimo_pregao_encerrado(depois) == date(2026, 11, 15)
    assert calendar.hoje_na_b3(depois) == date(2026, 11, 16)
    # 20h55 de Brasilia do dia 15 = 23h55 UTC: o do dia 15 ainda esta aberto.
    antes = datetime(2026, 11, 15, 23, 55, tzinfo=UTC)
    assert calendar.ultimo_pregao_encerrado(antes) == date(2026, 11, 14)


def test_calendario_da_b3_nao_muda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(mercado.VARIAVEL, raising=False)
    assert not calendar.is_trading_day(date(2026, 11, 15))
    assert calendar.next_trading_day(date(2026, 11, 13)) == date(2026, 11, 16)


@pytest.mark.parametrize(
    ("valor", "schema", "rotulo"),
    [("b3", "volume_scanner", "2016-2026"), ("cripto", "cripto_scanner", "2022-2026")],
)
def test_tabelas_e_backtest_seguem_o_mercado_do_processo(
    valor: str, schema: str, rotulo: str
) -> None:
    """O schema e fixado quando os modelos sao importados: um processo, um mercado."""
    codigo = (
        "from scanner.storage.models import DailyBar;"
        "from scanner.backtest.metricas import ROTULO_CONFERENCIA;"
        "from scanner.backtest.suite import CUSTO;"
        "print(DailyBar.__table__.schema, ROTULO_CONFERENCIA, CUSTO)"
    )
    saida = subprocess.run(
        [sys.executable, "-c", codigo],
        env={"SCANNER_MERCADO": valor, "PATH": ""},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert saida[:2] == [schema, rotulo]
    assert float(saida[2]) == (0.0015 if valor == "cripto" else 0.0008)


def test_quantidade_curta_da_b3_e_o_inteiro_de_sempre(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(mercado.VARIAVEL, raising=False)
    assert mercado.quantidade_curta(70.0) == "70"
    assert mercado.quantidade_curta(99_999.0) == "99999"


@pytest.mark.parametrize(
    "quantidade,texto",
    [
        (0.0152847, "0,0153"),
        (0.000769, "0,00077"),
        (0.5, "0,5"),
        (12.5, "12,5"),
        (3.0, "3"),
        (123_456.7, "123.457"),
        (1_234_567.0, "1,2mi"),
        (0.0, "0"),
    ],
)
def test_quantidade_curta_de_cripto_cabe_em_sete_caracteres(
    cripto: None, quantidade: float, texto: str
) -> None:
    assert mercado.quantidade_curta(quantidade) == texto
    assert len(texto) <= 7


def test_quantidade_curta_da_posicao_vendida_leva_o_sinal(cripto: None) -> None:
    """Venda a descoberto (0029): a posicao e negativa, e o Telegram mostra o sinal."""
    assert mercado.quantidade_curta(-0.5) == "-0,5"
    assert mercado.quantidade_curta(-0.0152847) == "-0,0153"
    assert len(mercado.quantidade_curta(-0.0152847)) <= 7
