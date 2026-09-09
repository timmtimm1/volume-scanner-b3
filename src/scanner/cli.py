"""CLI do scanner (secao 11 do plano).

Os comandos do pipeline existem e validam argumentos desde a F0; a
implementacao de cada um entra na fase correspondente do plano.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Any

import pandas as pd
import typer

from scanner import __version__
from scanner.calendar import previous_trading_day
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


def parse_trade_date(value: str) -> date:
    """Aceita `today`/`hoje`, `ultimo`/`last`, ou uma data ISO (AAAA-MM-DD).

    `ultimo` e o pregao completo mais recente -- ontem, ou sexta numa segunda.
    E o que o job da manha pede: as 7h40 o arquivo do dia anterior ja saiu, e o
    do proprio dia nem existe (a B3 ainda nao abriu).

    Nao aceita "ontem" de proposito: ontem pode nao ter sido pregao, e a
    diferenca entre "o dia anterior" e "o ultimo pregao" e justamente o que o
    calendario resolve.
    """
    escolha = value.lower()
    if escolha in {"today", "hoje"}:
        return date.today()
    if escolha in {"ultimo", "último", "last"}:
        return previous_trading_day(date.today())
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(
            f"data invalida: {value!r} (use AAAA-MM-DD, 'today' ou 'ultimo')"
        ) from exc


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


@db_app.command("status")
def db_status() -> None:
    """Quanto o banco tem: barras, pregoes, metricas e eventos."""
    from sqlalchemy import func, select

    from scanner.storage.engine import build_engine
    from scanner.storage.models import Event
    from scanner.storage.repository import (
        count_bars,
        count_metrics,
        retention_cutoff,
        sessions_stored,
        stored_range,
    )

    engine = build_engine()
    primeiro, ultimo = stored_range(engine)
    with engine.connect() as conn:
        eventos = int(conn.execute(select(func.count()).select_from(Event)).scalar_one())

    keep = load_config().retention.keep_sessions
    corte = retention_cutoff(engine, keep)

    typer.echo(f"barras:    {count_bars(engine):>10,}")
    typer.echo(f"pregoes:   {sessions_stored(engine):>10,}")
    typer.echo(f"metricas:  {count_metrics(engine):>10,}")
    typer.echo(f"eventos:   {eventos:>10,}")
    typer.echo(f"periodo:   {primeiro} a {ultimo}")
    typer.echo(
        f"retencao:  {keep} pregoes" + (f", corte em {corte}" if corte else ", nada a podar")
    )


@db_app.command("prune")
def db_prune(
    keep: Annotated[
        int | None, typer.Option("--keep", help="Pregoes a manter. Padrao: config.yaml.")
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="So mostra o corte.")] = False,
) -> None:
    """Descarta barras e metricas antigas, mantendo os ultimos N pregoes.

    Eventos nunca sao apagados: a ficha do papel marca eventos antigos mesmo
    quando as barras daquele periodo ja sairam.
    """
    from scanner.storage.engine import build_engine
    from scanner.storage.repository import prune_bars, retention_cutoff

    engine = build_engine()
    manter = keep if keep is not None else load_config().retention.keep_sessions
    if manter < 1:
        raise typer.BadParameter("--keep minimo e 1")

    corte = retention_cutoff(engine, manter)
    if corte is None:
        typer.echo(f"nada a podar: ha menos de {manter} pregoes no banco")
        return

    if dry_run:
        typer.echo(f"[dry-run] apagaria tudo anterior a {corte.isoformat()}")
        return

    barras, metricas = prune_bars(engine, manter)
    typer.echo(
        f"podado ate {corte.isoformat()}: {barras:,} barras e {metricas:,} metricas removidas"
    )


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
    from scanner.recompute import refresh_metrics
    from scanner.storage.engine import build_engine

    if mode not in {"incremental", "full"}:
        raise typer.BadParameter("--mode aceita 'incremental' ou 'full'")
    typer.echo(refresh_metrics(build_engine(), load_config(), mode=mode).summary())


def _notificador(settings: Any, *, dry_run: bool) -> Any:
    """Para onde as mensagens vao: Telegram, ou o terminal se faltar segredo.

    Perder o evento em silencio seria pior do que nao manda-lo pelo canal
    certo, entao a falta de configuracao vira aviso, nao erro.
    """
    from scanner.notify.telegram import ConsoleNotifier, TelegramNotifier

    if dry_run:
        return ConsoleNotifier(base_url=settings.web_base_url)
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        typer.secho(
            "[aviso] SCANNER_TELEGRAM_BOT_TOKEN/CHAT_ID ausentes; as mensagens saem no terminal.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        return ConsoleNotifier(base_url=settings.web_base_url)
    return TelegramNotifier(
        token=settings.telegram_bot_token.get_secret_value(),
        chat_id=settings.telegram_chat_id,
        base_url=settings.web_base_url,
    )


@app.command("scan")
def scan(
    trade_date: Annotated[str, typer.Option("--date", help="Pregao a avaliar.")] = "today",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Lista os eventos sem notificar.")
    ] = False,
) -> None:
    """Aplica a regra de alerta e notifica os eventos do pregao."""
    from scanner.alerts import run_scan
    from scanner.calendar import is_trading_day
    from scanner.config import get_settings
    from scanner.storage.engine import build_engine

    dia = parse_trade_date(trade_date)
    if not is_trading_day(dia):
        typer.secho(f"[pulado] {dia.isoformat()} nao e pregao.", fg=typer.colors.YELLOW)
        return

    notifier = _notificador(get_settings(), dry_run=dry_run)
    relatorio, _ = run_scan(build_engine(), load_config(), dia, dry_run=dry_run, notifier=notifier)
    typer.echo(relatorio.summary())


@app.command("resumo")
def resumo(
    trade_date: Annotated[str, typer.Option("--date", help="Pregao a resumir.")] = "today",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Mostra sem enviar ao Telegram.")
    ] = False,
) -> None:
    """Manda o resumo do pregao: os papeis que mais fugiram do proprio normal."""
    from scanner.calendar import is_trading_day
    from scanner.config import get_settings
    from scanner.digest import run_resumo
    from scanner.storage.engine import build_engine

    dia = parse_trade_date(trade_date)
    if not is_trading_day(dia):
        typer.secho(f"[pulado] {dia.isoformat()} nao e pregao.", fg=typer.colors.YELLOW)
        return

    config = load_config()
    if not config.digest.enabled:
        typer.secho("[pulado] digest.enabled esta false no config.", fg=typer.colors.YELLOW)
        return

    notifier = _notificador(get_settings(), dry_run=dry_run)
    saida = run_resumo(build_engine(), config, dia, notifier=notifier)
    typer.echo(
        f"{dia.isoformat()}: {len(saida.linhas)} papeis no resumo, "
        f"{saida.avaliados} avaliados, {saida.cruzaram} acima do limiar"
    )


@app.command("daily")
def daily(
    trade_date: Annotated[str, typer.Option("--date", help="Pregao a processar.")] = "today",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Calcula e mostra, sem gravar nem notificar.")
    ] = False,
) -> None:
    """O pregao inteiro num comando: carga, metricas, alerta, resumo e poda.

    Os comandos separados continuam existindo e fazem exatamente o mesmo. A
    diferenca esta em quantas vezes o trabalho e feito: rodando um a um, cada
    um abre seu proprio Python, le as barras do banco e recalcula os z-scores
    do historico inteiro -- tres vezes o mesmo calculo por pregao. Aqui isso
    acontece uma vez e o resultado desce por todas as etapas.

    Alem do tempo, isso garante que o alerta e o resumo do mesmo pregao falam
    dos mesmos numeros, em vez de dois calculos independentes que se espera que
    coincidam.
    """
    from scanner.alerts import run_scan
    from scanner.calendar import is_trading_day
    from scanner.config import get_settings
    from scanner.digest import run_resumo
    from scanner.ingest.pipeline import ingest_day
    from scanner.recompute import carregar_contexto, refresh_metrics
    from scanner.storage.engine import build_engine
    from scanner.storage.repository import prune_bars, retention_cutoff

    dia = parse_trade_date(trade_date)
    if not is_trading_day(dia):
        typer.secho(f"[pulado] {dia.isoformat()} nao e pregao.", fg=typer.colors.YELLOW)
        return

    config = load_config()
    settings = get_settings()
    engine = build_engine()

    def etapa(numero: int, texto: str) -> None:
        """Uma linha por etapa: sem isto, um comando so vira uma caixa preta."""
        typer.echo(f"[{numero}/6] {texto}")

    if dry_run:
        # A carga grava; num ensaio ela fica de fora e vale o que ja esta la.
        etapa(1, "[dry-run] carga pulada; vale o que ja esta no banco")
    else:
        etapa(1, ingest_day(dia, config.ingest))

    # A unica leitura das barras e o unico calculo do dia. Tudo abaixo reusa.
    contexto = carregar_contexto(engine, config)
    # O periodo sai do proprio DataFrame, sem custo: e o que o `db status`
    # mostrava num passo separado que abria outro Python so para isso.
    periodo = ""
    if not contexto.vazio:
        datas = pd.to_datetime(contexto.bars["trade_date"])
        periodo = f", de {datas.min().date()} a {datas.max().date()}"
    etapa(2, f"contexto: {len(contexto.bars):,} barras{periodo}, janelas {list(contexto.janelas)}")

    if dry_run:
        etapa(3, "[dry-run] metricas nao gravadas")
    else:
        etapa(3, refresh_metrics(engine, config, mode="incremental", contexto=contexto).summary())

    notifier = _notificador(settings, dry_run=dry_run)
    relatorio, _ = run_scan(
        engine, config, dia, dry_run=dry_run, notifier=notifier, contexto=contexto
    )
    etapa(4, relatorio.summary())

    if not config.digest.enabled:
        etapa(5, "resumo desligado no config")
    else:
        saida = run_resumo(engine, config, dia, notifier=notifier, contexto=contexto)
        etapa(
            5,
            f"resumo: {len(saida.linhas)} papeis, {saida.avaliados} avaliados, "
            f"{saida.cruzaram} acima do limiar",
        )

    manter = config.retention.keep_sessions
    corte = retention_cutoff(engine, manter)
    if corte is None:
        etapa(6, f"nada a podar: ha menos de {manter} pregoes no banco")
    elif dry_run:
        etapa(6, f"[dry-run] podaria tudo anterior a {corte.isoformat()}")
    else:
        barras, metricas = prune_bars(engine, manter)
        etapa(6, f"podado ate {corte.isoformat()}: {barras:,} barras e {metricas:,} metricas")


alerta_app = typer.Typer(help="Alertas de rompimento de preco.", no_args_is_help=True)
app.add_typer(alerta_app, name="alerta")


def _provedor_de_cotacoes() -> Any:
    """brapi na frente, Yahoo cobrindo as lacunas."""
    from scanner.cotacoes import BrapiClient, ProvedorEncadeado, YahooClient

    settings = _settings()
    token = settings.brapi_token.get_secret_value() if settings.brapi_token else None
    return ProvedorEncadeado((BrapiClient(token=token), YahooClient()))


def _settings() -> Any:
    from scanner.config import get_settings

    return get_settings()


@alerta_app.command("add")
def alerta_add(
    ticker: Annotated[str, typer.Argument(help="Papel, ex.: PETR4.")],
    preco: Annotated[float, typer.Option("--preco", help="Nivel a vigiar.")],
    direcao: Annotated[str, typer.Option("--direcao", help="acima | abaixo")] = "acima",
    trade_date: Annotated[
        str, typer.Option("--date", help="Pregao do evento que motivou.")
    ] = "ultimo",
) -> None:
    """Cria um alerta de rompimento."""
    from decimal import Decimal

    from scanner.cotacoes.base import ticker_valido
    from scanner.rompimentos import DIRECOES
    from scanner.storage.engine import build_engine
    from scanner.storage.repository import criar_alerta

    codigo = ticker.upper()
    if not ticker_valido(codigo):
        raise typer.BadParameter(f"ticker invalido: {ticker!r}")
    if direcao not in DIRECOES:
        raise typer.BadParameter("--direcao aceita 'acima' ou 'abaixo'")
    if preco <= 0:
        raise typer.BadParameter("--preco tem de ser positivo")

    novo = criar_alerta(
        build_engine(), codigo, parse_trade_date(trade_date), Decimal(str(preco)), direcao
    )
    typer.echo(f"alerta {novo}: {codigo} {direcao} de R$ {preco:.2f}")


@alerta_app.command("list")
def alerta_list(
    ticker: Annotated[str | None, typer.Option("--ticker", help="Filtra por papel.")] = None,
) -> None:
    """Lista os alertas, ativos primeiro."""
    from scanner.storage.engine import build_engine
    from scanner.storage.repository import listar_alertas

    alertas = listar_alertas(build_engine(), ticker)
    if not alertas:
        typer.echo("nenhum alerta")
        return
    for a in alertas:
        estado = (
            "ativo"
            if a.ativo
            else f"disparou em {a.disparado_em:%d/%m %H:%M} a R$ {a.preco_disparo}"
        )
        typer.echo(f"{a.id:>4}  {a.ticker:<8} {a.direcao:<6} R$ {a.preco:>9}  {estado}")


@alerta_app.command("rm")
def alerta_rm(alerta_id: Annotated[int, typer.Argument(help="Id do alerta.")]) -> None:
    """Apaga um alerta."""
    from scanner.storage.engine import build_engine
    from scanner.storage.repository import apagar_alerta

    typer.echo("apagado" if apagar_alerta(build_engine(), alerta_id) else "nao encontrado")


@alerta_app.command("on")
def alerta_on(alerta_id: Annotated[int, typer.Argument(help="Id do alerta.")]) -> None:
    """Religa um alerta que ja disparou."""
    from scanner.storage.engine import build_engine
    from scanner.storage.repository import reativar_alerta

    typer.echo("reativado" if reativar_alerta(build_engine(), alerta_id) else "nao encontrado")


@alerta_app.command("checar")
def alerta_checar(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Mostra sem gravar nem desativar.")
    ] = False,
) -> None:
    """Consulta o preco atual e dispara os alertas que romperam."""
    from scanner.calendar import is_trading_day
    from scanner.config import get_settings
    from scanner.rompimentos import checar_rompimentos
    from scanner.storage.engine import build_engine

    # O cron roda de segunda a sexta, mas feriado da B3 tambem cai em dia util.
    # Sem esta guarda, um feriado gastaria 36 consultas aos fornecedores para
    # reler um preco que nao se move.
    if not is_trading_day(date.today()):
        typer.secho("[pulado] hoje nao e pregao.", fg=typer.colors.YELLOW)
        return

    notifier = _notificador(get_settings(), dry_run=dry_run)
    relatorio = checar_rompimentos(
        build_engine(), _provedor_de_cotacoes(), notifier=notifier, dry_run=dry_run
    )
    typer.echo(relatorio.summary())


@report_app.command("ticker")
def report_ticker(
    ticker: Annotated[str, typer.Argument(help="Codigo do papel, ex.: PETR4.")],
    window: Annotated[int, typer.Option("--window", help="Janela em pregoes.")] = 60,
) -> None:
    """Historico de eventos e metricas de um papel."""
    from scanner.recompute import ticker_history
    from scanner.storage.engine import build_engine

    if not ticker.strip():
        raise typer.BadParameter("informe um ticker")
    if window < 2:
        raise typer.BadParameter("--window minimo e 2")

    linhas = ticker_history(build_engine(), ticker, window)
    if linhas.empty:
        typer.secho(f"[vazio] sem barras para {ticker.upper()}.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    typer.echo(f"{ticker.upper()} - ultimos {len(linhas)} pregoes, janela {window}")
    typer.echo(f"{'data':<12}{'fech.':>9}{'ret':>8}{'z_log':>8}{'rvol':>8}{'ticket':>12}")
    for _, r in linhas.iterrows():
        z = "-" if pd.isna(r["z_log"]) else f"{r['z_log']:.2f}"
        rv = "-" if pd.isna(r["rvol"]) else f"{r['rvol']:.1f}x"
        tk = "-" if pd.isna(r["avg_ticket"]) else f"{r['avg_ticket']:,.0f}"
        ret = "-" if pd.isna(r["ret_day"]) else f"{r['ret_day']:+.1%}"
        typer.echo(
            f"{r['trade_date'].date().isoformat():<12}{float(r['close']):>9.2f}"
            f"{ret:>8}{z:>8}{rv:>8}{tk:>12}"
        )


if __name__ == "__main__":  # pragma: no cover
    app()
