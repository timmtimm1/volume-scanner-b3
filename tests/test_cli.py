"""CLI: todos os comandos da secao 11 existem e validam seus argumentos."""

from __future__ import annotations

import json
from datetime import date

import pytest
from typer.testing import CliRunner

from scanner import __version__
from scanner.cli import app, parse_trade_date

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_config_show_devolve_json_valido() -> None:
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["alert"]["windows"] == [30, 45, 60]


def test_config_show_nao_imprime_url_do_banco() -> None:
    result = runner.invoke(app, ["config", "show"])
    assert "postgresql" not in result.stdout


@pytest.mark.parametrize(
    "argv",
    [
        ["ingest", "backfill"],
        ["ingest", "daily"],
        ["metrics", "compute"],
        ["report", "ticker"],
        ["scan"],
    ],
)
def test_comandos_ja_implementados_nao_anunciam_pendencia(argv: list[str]) -> None:
    # Todos os comandos da secao 11 estao implementados: nenhum pode anunciar
    # pendencia no --help.
    result = runner.invoke(app, [*argv, "--help"])
    assert result.exit_code == 0
    assert "[pendente]" not in result.output


@pytest.mark.parametrize(
    "argv",
    [
        ["ingest", "backfill", "--start", "01/01/2024"],
        ["metrics", "compute", "--mode", "turbo"],
        ["report", "ticker", "PETR4", "--window", "1"],
        ["scan", "--date", "ontem"],
    ],
)
def test_argumentos_invalidos_sao_erro_de_uso(argv: list[str]) -> None:
    assert runner.invoke(app, argv).exit_code == 2


def test_parse_trade_date() -> None:
    assert parse_trade_date("2024-03-15") == date(2024, 3, 15)
    assert parse_trade_date("today") == date.today()
    assert parse_trade_date("HOJE") == date.today()


def test_calendar_holidays_lista_o_ano() -> None:
    result = runner.invoke(app, ["calendar", "holidays", "--year", "2026"])
    assert result.exit_code == 0
    assert "2026-02-16" in result.stdout  # carnaval
    assert "2026-12-31" in result.stdout  # B3 fechada
    assert "total: 15" in result.stdout


def test_calendar_holidays_ano_nao_suportado_sai_com_erro() -> None:
    result = runner.invoke(app, ["calendar", "holidays", "--year", "2019"])
    assert result.exit_code == 1
    assert "[erro]" in result.output


def test_calendar_sessions_conta_pregoes() -> None:
    result = runner.invoke(
        app, ["calendar", "sessions", "--start", "2026-01-01", "--end", "2026-01-31"]
    )
    assert result.exit_code == 0
    assert "total: 21" in result.stdout
    assert "2026-01-01" not in result.stdout  # feriado


def test_calendar_sessions_intervalo_invertido_sai_com_erro() -> None:
    result = runner.invoke(
        app, ["calendar", "sessions", "--start", "2026-01-31", "--end", "2026-01-01"]
    )
    assert result.exit_code == 1
    assert "invertido" in result.output


def test_scan_pula_dia_sem_pregao() -> None:
    # 07/09/2026 e Independencia: nao ha pregao, e o scan nao pode nem tentar.
    result = runner.invoke(app, ["scan", "--date", "2026-09-07", "--dry-run"])
    assert result.exit_code == 0
    assert "[pulado]" in result.output
