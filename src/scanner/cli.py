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
calendar_app = typer.Typer(help="Calendario de pregoes da B3.", no_args_is_help=True)
universe_app = typer.Typer(help="Universo de papeis acompanhados.", no_args_is_help=True)
db_app = typer.Typer(help="Operacoes de banco.", no_args_is_help=True)

app.add_typer(ingest_app, name="ingest")
app.add_typer(metrics_app, name="metrics")
app.add_typer(report_app, name="report")
app.add_typer(config_app, name="config")
app.add_typer(calendar_app, name="calendar")
app.add_typer(universe_app, name="universe")
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


@calendar_app.command("holidays")
def calendar_holidays(
    year: Annotated[int, typer.Option("--year", help="Ano a listar.")],
) -> None:
    """Lista os dias sem pregao do ano, com o dia da semana."""
    from scanner.calendar import UnsupportedYearError, holidays

    try:
        dias = sorted(holidays(year))
    except UnsupportedYearError as exc:
        typer.secho(f"[erro] {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    semana = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
    for dia in dias:
        typer.echo(f"{dia.isoformat()}  {semana[dia.weekday()]}")
    typer.echo(f"total: {len(dias)}")


@calendar_app.command("sessions")
def calendar_sessions(
    start: Annotated[str, typer.Option("--start", help="Data inicial (AAAA-MM-DD).")],
    end: Annotated[str, typer.Option("--end", help="Data final. Padrao: hoje.")] = "today",
) -> None:
    """Conta e lista os pregoes do intervalo."""
    from scanner.calendar import UnsupportedYearError, trading_days

    try:
        dias = trading_days(parse_trade_date(start), parse_trade_date(end))
    except (UnsupportedYearError, ValueError) as exc:
        typer.secho(f"[erro] {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    for dia in dias:
        typer.echo(dia.isoformat())
    typer.echo(f"total: {len(dias)}")


@universe_app.command("show")
def universe_show(
    trade_date: Annotated[str, typer.Option("--date", help="Pregao de referencia.")] = "today",
) -> None:
    """Universo vigente, do mais liquido para o menos."""
    from scanner.storage.engine import build_engine
    from scanner.universe import load_universe

    as_of = parse_trade_date(trade_date)
    universo = load_universe(build_engine(), as_of, load_config().universe)

    for ticker, linha in universo.iterrows():
        typer.echo(
            f"{ticker:<8} mediana R$ {linha['median_volume']:>15,.2f}"
            f"  pregoes {int(linha['sessions_traded']):>3}"
            f"  cobertura {linha['coverage']:.0%}"
        )
    typer.echo(f"total: {len(universo)} tickers em {as_of.isoformat()}")


@ingest_app.command("backfill")
def ingest_backfill(
    start: Annotated[str, typer.Option("--start", help="Data inicial (AAAA-MM-DD).")],
    end: Annotated[str, typer.Option("--end", help="Data final. Padrao: hoje.")] = "today",
) -> None:
    """Carga historica do COTAHIST a partir dos arquivos anuais."""
    from scanner.ingest.pipeline import ingest_range

    inicio, fim = parse_trade_date(start), parse_trade_date(end)
    if fim < inicio:
        raise typer.BadParameter(f"intervalo invertido: {inicio} > {fim}")

    for relatorio in ingest_range(inicio, fim, load_config().ingest):
        typer.echo(relatorio)


@ingest_app.command("daily")
def ingest_daily(
    trade_date: Annotated[str, typer.Option("--date", help="Pregao a carregar.")] = "today",
) -> None:
    """Carga incremental do arquivo diario."""
    from scanner.calendar import is_trading_day
    from scanner.ingest.pipeline import ingest_day

    dia = parse_trade_date(trade_date)
    if not is_trading_day(dia):
        typer.secho(f"[pulado] {dia.isoformat()} nao e pregao.", fg=typer.colors.YELLOW)
        return
    typer.echo(ingest_day(dia, load_config().ingest))


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
