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
from scanner.calendar import hoje_na_b3, ultimo_pregao_encerrado
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
fundamentos_app = typer.Typer(help="Empresas e balancos da CVM.", no_args_is_help=True)

app.add_typer(ingest_app, name="ingest")
app.add_typer(metrics_app, name="metrics")
app.add_typer(report_app, name="report")
app.add_typer(config_app, name="config")
app.add_typer(calendar_app, name="calendar")
app.add_typer(universe_app, name="universe")
app.add_typer(db_app, name="db")
app.add_typer(fundamentos_app, name="fundamentos")


# Codigo de saida do `daily` quando o arquivo do pregao de HOJE ainda nao saiu
# da B3. E o EX_TEMPFAIL do sysexits.h: "tente mais tarde". O workflow trata
# como adiado, e nao como falha -- a passada das 07:40 processa o pregao.
SAIDA_ADIADO = 75


def parse_trade_date(value: str) -> date:
    """Aceita `today`/`hoje`, `ultimo`/`last`, ou uma data ISO (AAAA-MM-DD).

    `ultimo` e o pregao encerrado mais recente, no relogio de Sao Paulo: as
    21:30 e o proprio dia, as 07:40 e a vespera (sexta, numa segunda). E o que
    os dois disparos do `daily` pedem, sem cada um precisar dizer a data.
    `hoje` tambem e o dia em Sao Paulo, e nao o da maquina.

    Nao aceita "ontem" de proposito: ontem pode nao ter sido pregao, e a
    diferenca entre "o dia anterior" e "o ultimo pregao" e justamente o que o
    calendario resolve.
    """
    escolha = value.lower()
    if escolha in {"today", "hoje"}:
        return hoje_na_b3()
    if escolha in {"ultimo", "último", "last"}:
        return ultimo_pregao_encerrado()
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
        mb,
        retention_cutoff,
        sessions_stored,
        stored_range,
        tamanho_do_banco,
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
    total, tabelas = tamanho_do_banco(engine)
    typer.echo(f"tamanho:   {mb(total):>10}")
    for nome, tamanho in tabelas.items():
        typer.echo(f"  {nome:<16}{mb(tamanho):>10}")


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

    poda = prune_bars(engine, manter)
    typer.echo(
        f"podado ate {corte.isoformat()}: {poda.barras:,} barras, {poda.metricas:,} metricas "
        f"e {poda.contexto:,} linhas de contexto removidas"
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
    saida = run_resumo(build_engine(), config, dia, notifier=notifier, dry_run=dry_run)
    if saida.repetido:
        typer.secho(
            f"[pulado] o resumo de {dia.isoformat()} ja foi enviado.", fg=typer.colors.YELLOW
        )
        return
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
    """O pregao inteiro num comando: carga, metricas, alerta, trades, resumo e poda.

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
    from scanner.storage.repository import mb, prune_bars, retention_cutoff, tamanho_do_banco
    from scanner.trades import run_snapshots

    dia = parse_trade_date(trade_date)
    if not is_trading_day(dia):
        typer.secho(f"[pulado] {dia.isoformat()} nao e pregao.", fg=typer.colors.YELLOW)
        return

    config = load_config()
    settings = get_settings()
    engine = build_engine()

    def etapa(numero: int, texto: str) -> None:
        """Uma linha por etapa: sem isto, um comando so vira uma caixa preta."""
        typer.echo(f"[{numero}/7] {texto}")

    if dry_run:
        # A carga grava; num ensaio ela fica de fora e vale o que ja esta la.
        etapa(1, "[dry-run] carga pulada; vale o que ja esta no banco")
    else:
        from scanner.ingest.download import DownloadTemporarioError

        try:
            etapa(1, ingest_day(dia, config.ingest, engine=engine))
        except DownloadTemporarioError as exc:
            # A noite isso e esperado: a B3 publica o arquivo do dia com atraso
            # que varia de um dia para outro. Sair como falha mandaria aviso no
            # Telegram quase toda sexta. Para um pregao que nao e o de hoje, o
            # arquivo ja devia existir, e ai e falha de verdade.
            if dia != hoje_na_b3():
                raise
            etapa(1, f"adiado: {exc}. A passada das 07:40 processa este pregao.")
            raise typer.Exit(code=SAIDA_ADIADO) from exc

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

    relatorio_snapshots = run_snapshots(engine, dia, bars=contexto.bars, dry_run=dry_run)
    etapa(5, relatorio_snapshots.summary())

    if not config.digest.enabled:
        etapa(6, "resumo desligado no config")
    else:
        saida = run_resumo(
            engine, config, dia, notifier=notifier, contexto=contexto, dry_run=dry_run
        )
        if saida.repetido:
            etapa(6, f"resumo de {dia.isoformat()} ja enviado antes; nao reenviado")
        else:
            etapa(
                6,
                f"resumo: {len(saida.linhas)} papeis, {saida.avaliados} avaliados, "
                f"{saida.cruzaram} acima do limiar",
            )

    manter = config.retention.keep_sessions
    corte = retention_cutoff(engine, manter)
    if corte is None:
        poda_texto = f"nada a podar: ha menos de {manter} pregoes no banco"
    elif dry_run:
        poda_texto = f"[dry-run] podaria tudo anterior a {corte.isoformat()}"
    else:
        poda = prune_bars(engine, manter)
        poda_texto = (
            f"podado ate {corte.isoformat()}: {poda.barras:,} barras, "
            f"{poda.metricas:,} metricas e {poda.contexto:,} linhas de contexto"
        )
    # O tamanho vai na mesma linha: e o numero que diz quanto falta para o limite
    # do plano gratuito do Neon, sem precisar abrir o painel.
    total, tabelas = tamanho_do_banco(engine)
    maiores = ", ".join(f"{nome} {mb(tam)}" for nome, tam in list(tabelas.items())[:3])
    etapa(7, f"{poda_texto}; banco com {mb(total)} ({maiores})")


alerta_app = typer.Typer(help="Alertas de rompimento de preco.", no_args_is_help=True)
app.add_typer(alerta_app, name="alerta")


def _provedor_de_cotacoes() -> Any:
    """brapi e Yahoo, ficando com a cotacao mais recente de cada papel.

    Sem token a brapi fica de fora: ela responde 401 para qualquer papel alem
    dos quatro de teste, e cada passada gastaria uma requisicao por papel so
    para encher o log de recusa.
    """
    from scanner.cotacoes import BrapiClient, ProvedorMaisRecente, YahooClient

    settings = _settings()
    provedores: list[Any] = []
    if settings.brapi_token:
        provedores.append(
            BrapiClient(token=settings.brapi_token.get_secret_value(), lote=settings.brapi_lote)
        )
    provedores.append(YahooClient())
    return ProvedorMaisRecente(tuple(provedores))


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
    from scanner.calendar import hoje_na_b3, is_trading_day
    from scanner.config import get_settings
    from scanner.rompimentos import checar_rompimentos
    from scanner.storage.engine import build_engine

    # O cron roda de segunda a sexta, mas feriado da B3 tambem cai em dia util.
    # Sem esta guarda, um feriado gastaria 36 consultas aos fornecedores para
    # reler um preco que nao se move. O dia e o de Sao Paulo, nao o do runner.
    if not is_trading_day(hoje_na_b3()):
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


@fundamentos_app.command("atualizar")
def fundamentos_atualizar(
    forcar: Annotated[
        bool, typer.Option("--forcar", help="Ignora o cache e reprocessa tudo.")
    ] = False,
    sem_b3: Annotated[
        bool,
        typer.Option(
            "--sem-b3",
            help=(
                "Pula cadastro e proventos da B3: so a CVM (balancos) e o "
                "recalculo dos trimestres. E o que o pregao roda -- a CVM "
                "publica por trimestre, nao por dia; a B3 fica para o "
                "workflow semanal."
            ),
        ),
    ] = False,
) -> None:
    """Liga empresas ao ticker e carrega os balancos da CVM (ITR/DFP)."""
    from scanner.fundamentos.carga import atualizar_fundamentos
    from scanner.storage.engine import build_engine

    relatorio = atualizar_fundamentos(
        build_engine(), load_config().fundamentos, forcar=forcar, com_b3=not sem_b3
    )
    for linha in relatorio.linhas():
        typer.echo(f"[fundamentos] {linha}")
    if relatorio.teve_falha:
        raise typer.Exit(code=1)


@fundamentos_app.command("status")
def fundamentos_status() -> None:
    """Empresas, documentos por tipo/ano e tickers ainda sem empresa ligada."""
    from scanner.storage.engine import build_engine
    from scanner.storage.repository import (
        contagem_do_mapeamento,
        contar_empresas,
        contar_proventos,
        contar_trimestres,
        datas_dos_arquivos_externos,
        documentos_por_tipo_e_ano,
        tickers_sem_empresa,
    )

    engine = build_engine()
    ligados, sem_empresa = contagem_do_mapeamento(engine)
    proventos, papeis_com_provento = contar_proventos(engine)
    trimestres, empresas_com_trimestre = contar_trimestres(engine)
    typer.echo(f"empresas: {contar_empresas(engine):>6,}")
    typer.echo(f"tickers ligados: {ligados:>6,}")
    typer.echo(f"proventos: {proventos:>6,} em {papeis_com_provento} papeis")
    typer.echo(f"trimestres: {trimestres:>5,} em {empresas_com_trimestre} empresas")

    docs = documentos_por_tipo_e_ano(engine)
    if docs.empty:
        typer.echo("documentos: nenhum")
    else:
        for _, linha in docs.iterrows():
            typer.echo(
                f"  {linha['tipo']:<4} {int(linha['ano'])}: {int(linha['total']):>5,} documentos"
            )

    datas = datas_dos_arquivos_externos(engine)
    for _, linha in datas.iterrows():
        quando = linha["modificado_em"]
        data = quando.strftime("%d/%m/%Y") if pd.notna(quando) else "-"
        typer.echo(f"  {linha['url']}: dados de {data}")

    orfaos = tickers_sem_empresa(engine)
    typer.echo(f"tickers sem empresa ligada: {sem_empresa}")
    for ticker in orfaos[:10]:
        typer.echo(f"  {ticker}")


@fundamentos_app.command("empresa")
def fundamentos_empresa(
    ticker: Annotated[str, typer.Argument(help="Papel, ex.: UNIP6.")],
) -> None:
    """O que esta gravado da empresa do ticker -- ferramenta de conferencia manual."""
    from scanner.storage.engine import build_engine
    from scanner.storage.repository import (
        balanco_da_empresa,
        empresa_do_ticker,
        resultados_da_empresa,
        ultimos_documentos_da_empresa,
    )

    engine = build_engine()
    empresa = empresa_do_ticker(engine, ticker)
    if empresa is None:
        typer.secho(
            f"[erro] nenhuma empresa ligada a {ticker.upper()}", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)

    typer.echo(f"{empresa['nome']} (CD_CVM {empresa['cd_cvm']}, CNPJ {empresa['cnpj']})")
    typer.echo(
        f"setor CVM: {empresa['setor_cvm']}  situacao: {empresa['situacao']}"
        f"  ligacao pelo {empresa['fonte'].upper()}"
    )

    documentos = ultimos_documentos_da_empresa(engine, int(empresa["cd_cvm"]), limite=4)
    if documentos.empty:
        typer.echo("nenhum documento carregado")
        return

    for _, doc in documentos.iterrows():
        typer.echo(
            f"\n{doc['tipo']} {doc['dt_refer']} (escopo {doc['escopo']}, "
            f"layout {doc['layout']}, versao {doc['versao']}, "
            f"recebido {doc['recebido_original']} -> {doc['recebido_ultima']})"
        )
        resultados = resultados_da_empresa(
            engine, int(empresa["cd_cvm"]), str(doc["tipo"]), doc["dt_refer"]
        )
        for _, r in resultados.iterrows():
            typer.echo(
                f"  {r['dt_ini']} a {r['dt_fim']}: receita {r['receita']}, "
                f"lucro_liquido {r['lucro_liquido']}, "
                f"lucro_controladores {r['lucro_controladores']}, "
                f"ebit {r['ebit']}, "
                f"depreciacao_amortizacao {r['depreciacao_amortizacao']}"
            )
        balanco = balanco_da_empresa(
            engine, int(empresa["cd_cvm"]), str(doc["tipo"]), doc["dt_refer"]
        )
        if not balanco.empty:
            b = balanco.iloc[0]
            typer.echo(
                f"  ativo_total {b['ativo_total']}, patrimonio_liquido {b['patrimonio_liquido']}, "
                f"passivo_circulante {b['passivo_circulante']}, caixa {b['caixa']}"
            )


@fundamentos_app.command("indicadores")
def fundamentos_indicadores(
    ticker: Annotated[str, typer.Argument(help="Papel, ex.: UNIP6.")],
) -> None:
    """Os trimestres calculados da empresa do papel, em milhoes de reais."""
    from scanner.storage.engine import build_engine
    from scanner.storage.repository import trimestres_do_ticker

    linhas = trimestres_do_ticker(build_engine(), ticker)
    if linhas.empty:
        typer.secho(f"[vazio] nenhum trimestre de {ticker.upper()}", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    def milhoes(valor: Any) -> str:
        return "-" if pd.isna(valor) else f"{float(valor) / 1_000_000:,.1f}"

    typer.echo(f"{ticker.upper()} - {len(linhas)} trimestres, em R$ milhoes")
    cabecalho = f"{'tri':<6}{'publicado':<12}{'receita':>10}{'EBITDA':>10}{'lucro':>10}"
    typer.echo(cabecalho + f"{'rec 12m':>12}{'lucro 12m':>12}{'PL':>12}{'div.liq':>12}  origem")
    for _, linha in linhas.iterrows():
        typer.echo(
            f"{linha['rotulo']:<6}{linha['publicado_em']!s:<12}"
            f"{milhoes(linha['receita_tri']):>10}{milhoes(linha['ebitda_tri']):>10}"
            f"{milhoes(linha['lucro_tri']):>10}{milhoes(linha['receita_12m']):>12}"
            f"{milhoes(linha['lucro_12m']):>12}{milhoes(linha['patrimonio_liquido']):>12}"
            f"{milhoes(linha['divida_liquida']):>12}  {linha['origem']}"
        )


@fundamentos_app.command("proventos")
def fundamentos_proventos(
    ticker: Annotated[str, typer.Argument(help="Papel, ex.: UNIP6.")],
) -> None:
    """Os proventos guardados de um papel, do mais novo para o mais antigo."""
    from scanner.storage.engine import build_engine
    from scanner.storage.repository import proventos_do_papel

    linhas = proventos_do_papel(build_engine(), ticker)
    if linhas.empty:
        typer.secho(f"[vazio] nenhum provento de {ticker.upper()}", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    typer.echo(f"{ticker.upper()} - {len(linhas)} proventos mais recentes")
    typer.echo(f"{'data com':<12}{'tipo':<18}{'R$/acao':>14}{'pagamento':>13}  fonte")
    for _, linha in linhas.iterrows():
        pagamento = linha["data_pagamento"]
        pago = "-" if pd.isna(pagamento) else str(pagamento)
        typer.echo(
            f"{linha['data_com']!s:<12}{linha['tipo'][:17]:<18}"
            f"{float(linha['valor']):>14.8f}{pago:>13}  {linha['fonte']}"
        )


if __name__ == "__main__":  # pragma: no cover
    app()
