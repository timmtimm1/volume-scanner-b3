"""CLI: os comandos da secao 11 existem, validam argumentos e sinalizam a fase."""

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
        ["ingest", "backfill", "--start", "2024-01-01"],
        ["ingest", "daily"],
        ["metrics", "compute", "--mode", "incremental"],
        ["scan", "--date", "today", "--dry-run"],
        ["report", "ticker", "PETR4", "--window", "60"],
    ],
)
def test_comandos_do_plano_existem_e_sinalizam_pendencia(argv: list[str]) -> None:
    result = runner.invoke(app, argv)
    # Argumentos validos: nao pode ser erro de uso (2), e sim pendencia declarada (1).
    assert result.exit_code == 1, result.output
    assert "[pendente]" in result.output


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
