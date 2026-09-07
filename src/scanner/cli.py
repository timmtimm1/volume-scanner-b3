"""CLI do scanner (secao 11 do plano).

Os comandos do pipeline existem e validam argumentos desde a F0; a
implementacao de cada um entra na fase correspondente do plano.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, NoReturn

import typer

from scanner import __version__
from scanner.config import load_config

app = typer.Typer(
    name="scanner",
    help="Detector de volume financeiro anomalo na B3.",
    no_args_is_help=True,
    add_completion=False,
)
ingest_app = typer.Typer(help="Carga de dados COTAHIST.", no_args_is_help=True)
metrics_app = typer.Typer(help="Calculo de z-scores e features.", no_args_is_help=True)
report_app = typer.Typer(help="Relatorios de consulta.", no_args_is_help=True)
config_app = typer.Typer(help="Inspecao da configuracao.", no_args_is_help=True)
db_app = typer.Typer(help="Operacoes de banco.", no_args_is_help=True)

app.add_typer(ingest_app, name="ingest")
app.add_typer(metrics_app, name="metrics")
app.add_typer(report_app, name="report")
app.add_typer(config_app, name="config")
app.add_typer(db_app, name="db")


def _pending(phase: str, what: str) -> NoReturn:
    """Encerra um comando ainda nao implementado, nomeando a fase responsavel."""
    typer.secho(f"[pendente] {what} entra na fase {phase}.", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=1)


def parse_trade_date(value: str) -> date:
    """Aceita `today`/`hoje` ou uma data ISO (AAAA-MM-DD)."""
    if value.lower() in {"today", "hoje"}:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"data invalida: {value!r} (use AAAA-MM-DD ou 'today')") from exc


@app.command()
def version() -> None:
    """Mostra a versao instalada."""
    typer.echo(__version__)


@config_app.command("show")
def config_show() -> None:
    """Imprime a configuracao efetiva. Segredos nunca sao impressos."""
    typer.echo(json.dumps(load_config().model_dump(), indent=2, ensure_ascii=False))


@db_app.command("ping")
def db_ping() -> None:
    """Testa a conexao com o banco de SCANNER_DATABASE_URL."""
    from scanner.storage.engine import ping

    try:
        typer.echo(ping())
    # Excecao ampla de proposito: a mensagem crua do driver e o diagnostico util aqui.
    except Exception as exc:
        typer.secho(f"[erro] conexao falhou: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@ingest_app.command("backfill")
def ingest_backfill(
    start: Annotated[str, typer.Option("--start", help="Data inicial (AAAA-MM-DD).")],
    end: Annotated[str, typer.Option("--end", help="Data final. Padrao: hoje.")] = "today",
) -> None:
    """Carga historica do COTAHIST a partir dos arquivos anuais."""
    parse_trade_date(start)
    parse_trade_date(end)
    _pending("F2", "carga historica do COTAHIST")


@ingest_app.command("daily")
def ingest_daily(
    trade_date: Annotated[str, typer.Option("--date", help="Pregao a carregar.")] = "today",
) -> None:
    """Carga incremental do arquivo diario."""
    parse_trade_date(trade_date)
    _pending("F2", "carga diaria do COTAHIST")


@metrics_app.command("compute")
def metrics_compute(
    mode: Annotated[str, typer.Option("--mode", help="incremental | full")] = "incremental",
) -> None:
    """Calcula z-scores e features de contexto."""
    if mode not in {"incremental", "full"}:
        raise typer.BadParameter("--mode aceita 'incremental' ou 'full'")
    _pending("F3", "calculo de z-scores e features")


@app.command("scan")
def scan(
    trade_date: Annotated[str, typer.Option("--date", help="Pregao a avaliar.")] = "today",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Lista os eventos sem notificar.")
    ] = False,
) -> None:
    """Aplica a regra de alerta e notifica os eventos do pregao."""
    parse_trade_date(trade_date)
    _ = dry_run
    _pending("F4", "regra de alerta e notificacao")


@report_app.command("ticker")
def report_ticker(
    ticker: Annotated[str, typer.Argument(help="Codigo do papel, ex.: PETR4.")],
    window: Annotated[int, typer.Option("--window", help="Janela em pregoes.")] = 60,
) -> None:
    """Historico de eventos e metricas de um papel."""
    if not ticker.strip():
        raise typer.BadParameter("informe um ticker")
    if window < 2:
        raise typer.BadParameter("--window minimo e 2")
    _pending("F3", "relatorio por papel")


if __name__ == "__main__":  # pragma: no cover
    app()
