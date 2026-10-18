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
    from scanner.calendar import hoje_na_b3

    assert parse_trade_date("2024-03-15") == date(2024, 3, 15)
    # "hoje" e o dia em Sao Paulo, nao o da maquina: o runner roda em UTC.
    assert parse_trade_date("today") == hoje_na_b3()
    assert parse_trade_date("HOJE") == hoje_na_b3()


def test_fundamentos_help_lista_os_tres_comandos() -> None:
    result = runner.invoke(app, ["fundamentos", "--help"])
    assert result.exit_code == 0
    assert "atualizar" in result.output
    assert "status" in result.output
    assert "empresa" in result.output


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


# --- scanner daily -----------------------------------------------------------


def test_daily_pula_dia_sem_pregao() -> None:
    # Feriado nao pode nem tentar baixar arquivo nem notificar nada.
    result = runner.invoke(app, ["daily", "--date", "2026-09-07"])
    assert result.exit_code == 0
    assert "[pulado]" in result.output


class _EtapasFalsas:
    """Substitui cada etapa do pregao e anota o que foi chamado.

    O `daily` importa as funcoes dentro do corpo, entao o patch vai no modulo
    de origem, nao em `scanner.cli`.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import pandas as pd

        from scanner import alerts, digest, recompute
        from scanner import trades as trades_mod
        from scanner.alerts import ScanReport
        from scanner.digest import Resumo
        from scanner.ingest import pipeline
        from scanner.recompute import Contexto, RecomputeReport
        from scanner.storage import engine as engine_mod
        from scanner.storage import repository
        from scanner.trades import RelatorioSnapshots

        self.chamadas: list[str] = []
        self.contextos: list[object] = []
        barras = pd.DataFrame(
            {"ticker": ["AAAA3"], "trade_date": [pd.Timestamp("2026-09-04")]},
        )
        self.contexto = Contexto(barras, pd.DataFrame(), pd.DataFrame(), (30,))

        def anota(nome: str, retorno: object) -> object:
            self.chamadas.append(nome)
            return retorno

        monkeypatch.setattr(engine_mod, "build_engine", lambda: object())
        monkeypatch.setattr(
            pipeline, "ingest_day", lambda *a, **k: str(anota("ingest", "carregado"))
        )

        def carregar(*a: object, **k: object) -> Contexto:
            anota("contexto", None)
            return self.contexto

        monkeypatch.setattr(recompute, "carregar_contexto", carregar)

        def metricas(*a: object, **k: object) -> RecomputeReport:
            self.contextos.append(k.get("contexto"))
            anota("metricas", None)
            return RecomputeReport("incremental", 1, 1, 1, 1, None, None)

        monkeypatch.setattr(recompute, "refresh_metrics", metricas)

        def scan(*a: object, **k: object) -> tuple[ScanReport, object]:
            self.contextos.append(k.get("contexto"))
            anota("scan", None)
            return ScanReport(date(2026, 9, 4), 1, 0, 0, 0, 0, False), pd.DataFrame()

        monkeypatch.setattr(alerts, "run_scan", scan)

        def snapshots(*a: object, **k: object) -> RelatorioSnapshots:
            anota("snapshots", None)
            return RelatorioSnapshots(
                trades=0, snapshots=0, dry_run=bool(k.get("dry_run")), dia=date(2026, 9, 4)
            )

        monkeypatch.setattr(trades_mod, "run_snapshots", snapshots)

        def resumo(*a: object, **k: object) -> Resumo:
            self.contextos.append(k.get("contexto"))
            anota("resumo", None)
            return Resumo(date(2026, 9, 4), pd.DataFrame(), 1, 0, 6.0, None)

        monkeypatch.setattr(digest, "run_resumo", resumo)
        monkeypatch.setattr(repository, "retention_cutoff", lambda *a: date(2025, 1, 30))
        monkeypatch.setattr(
            repository,
            "prune_bars",
            lambda *a: (anota("poda", None), repository.Poda(0, 0, 0))[1],
        )
        monkeypatch.setattr(
            repository,
            "tamanho_do_banco",
            lambda *a: (150 * 1_048_576, {"daily_features": 60 * 1_048_576}),
        )


def test_daily_roda_as_sete_etapas_do_pregao(monkeypatch: pytest.MonkeyPatch) -> None:
    etapas = _EtapasFalsas(monkeypatch)
    result = runner.invoke(app, ["daily", "--date", "2026-09-04"])

    assert result.exit_code == 0, result.output
    assert etapas.chamadas == [
        "ingest",
        "contexto",
        "metricas",
        "scan",
        "snapshots",
        "resumo",
        "poda",
    ]
    for numero in range(1, 8):
        assert f"[{numero}/7]" in result.output


def test_daily_calcula_uma_vez_so_e_reusa(monkeypatch: pytest.MonkeyPatch) -> None:
    # A razao do comando existir. Se alguem soltar o `contexto=` de uma das
    # etapas, ela volta a reler o banco e a refazer o calculo -- e o alerta e o
    # resumo do mesmo pregao passam a vir de contas independentes.
    etapas = _EtapasFalsas(monkeypatch)
    assert runner.invoke(app, ["daily", "--date", "2026-09-04"]).exit_code == 0

    assert etapas.chamadas.count("contexto") == 1
    assert len(etapas.contextos) == 3
    assert all(c is etapas.contexto for c in etapas.contextos)


def test_daily_em_ensaio_nao_grava_nem_carrega(monkeypatch: pytest.MonkeyPatch) -> None:
    etapas = _EtapasFalsas(monkeypatch)
    result = runner.invoke(app, ["daily", "--date", "2026-09-04", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "ingest" not in etapas.chamadas
    assert "metricas" not in etapas.chamadas
    assert "poda" not in etapas.chamadas
    assert etapas.chamadas == ["contexto", "scan", "snapshots", "resumo"]


# --- Repescagem: `--so-se-faltar` ---------------------------------------------


def _resumo_ja_enviado(monkeypatch: pytest.MonkeyPatch, enviado: bool) -> list[date]:
    """Troca o carimbo do resumo e devolve os pregoes pelos quais perguntaram."""
    from scanner.storage import repository

    consultas: list[date] = []

    def carimbo(_engine: object, dia: date) -> bool:
        consultas.append(dia)
        return enviado

    monkeypatch.setattr(repository, "digest_enviado", carimbo)
    return consultas


def test_repescagem_sai_sem_fazer_nada_se_o_resumo_ja_saiu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A noite normal: as 21:30 resolveram e a repescagem nao repete nada."""
    from scanner import cli

    etapas = _EtapasFalsas(monkeypatch)
    consultas = _resumo_ja_enviado(monkeypatch, True)

    result = runner.invoke(app, ["daily", "--date", "2026-09-04", "--so-se-faltar"])

    assert result.exit_code == 0, result.output
    assert result.output.startswith(cli.MARCA_PRONTO), "o pregao.yml procura a marca"
    assert consultas == [date(2026, 9, 4)]
    assert etapas.chamadas == [], "pronto nao baixa, nao calcula, nao notifica e nao poda"


def test_repescagem_processa_o_pregao_que_as_21h30_adiaram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A noite do atraso: sem carimbo, a repescagem e um `daily` como outro."""
    etapas = _EtapasFalsas(monkeypatch)
    _resumo_ja_enviado(monkeypatch, False)

    result = runner.invoke(app, ["daily", "--date", "2026-09-04", "--so-se-faltar"])

    assert result.exit_code == 0, result.output
    assert "[pronto]" not in result.output
    assert etapas.chamadas[0] == "ingest"
    assert "resumo" in etapas.chamadas
    for numero in range(1, 8):
        assert f"[{numero}/7]" in result.output


def test_sem_a_opcao_o_daily_reprocessa_mesmo_com_o_resumo_enviado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """As 07:40 e o manual continuam como eram: nem perguntam pelo carimbo."""
    etapas = _EtapasFalsas(monkeypatch)
    consultas = _resumo_ja_enviado(monkeypatch, True)

    result = runner.invoke(app, ["daily", "--date", "2026-09-04"])

    assert result.exit_code == 0, result.output
    assert consultas == []
    assert "ingest" in etapas.chamadas


def test_adiado_depois_da_meia_noite_continua_adiado(monkeypatch: pytest.MonkeyPatch) -> None:
    """A espera pelo arquivo dura 15 minutos e pode atravessar a meia-noite.

    "Hoje" e lido antes da carga. Lido depois, a passada que comecou no dia do
    pregao terminaria no dia seguinte, e o 404 viraria falha com aviso.
    """
    from scanner import cli
    from scanner.ingest import pipeline
    from scanner.ingest.download import AindaNaoPublicadoError

    _EtapasFalsas(monkeypatch)
    relogio = {"hoje": date(2026, 9, 4)}
    monkeypatch.setattr(cli, "hoje_na_b3", lambda: relogio["hoje"])

    def espera_e_falha(*_a: object, **_k: object) -> str:
        relogio["hoje"] = date(2026, 9, 5)
        raise AindaNaoPublicadoError("404")

    monkeypatch.setattr(pipeline, "ingest_day", espera_e_falha)

    result = runner.invoke(app, ["daily", "--date", "2026-09-04"])

    assert result.exit_code == cli.SAIDA_ADIADO, result.output


# --- "ultimo": o pregao completo mais recente --------------------------------


def test_parse_trade_date_aceita_ultimo() -> None:
    from scanner.calendar import hoje_na_b3, is_trading_day, ultimo_pregao_encerrado

    for token in ("ultimo", "ULTIMO", "last"):
        dia = parse_trade_date(token)
        assert dia == ultimo_pregao_encerrado()
        assert dia <= hoje_na_b3(), "o ultimo pregao encerrado nunca esta no futuro"
        assert is_trading_day(dia), "o que volta tem de ser pregao"


def test_ultimo_pregao_pula_feriado_e_nao_e_simplesmente_ontem() -> None:
    # E a diferenca que faz o job da manha funcionar: numa terca depois de
    # feriado na segunda, "ontem" nao teve pregao e o arquivo nao existe.
    from scanner.calendar import previous_trading_day

    # 07/09/2026 e Independencia, numa segunda.
    assert previous_trading_day(date(2026, 9, 8)) == date(2026, 9, 4)


def test_ontem_continua_invalido() -> None:
    # Recusado de proposito: ontem pode nao ter sido pregao, e a ambiguidade
    # entre "o dia anterior" e "o ultimo pregao" e a origem do bug.
    assert runner.invoke(app, ["scan", "--date", "ontem"]).exit_code == 2


# --- Pregao de hoje ainda nao publicado -----------------------------------------


def _ingest_que_falha(monkeypatch: pytest.MonkeyPatch, erro: Exception) -> None:
    from scanner.ingest import pipeline

    def falha(*_a: object, **_k: object) -> str:
        raise erro

    monkeypatch.setattr(pipeline, "ingest_day", falha)


@pytest.mark.parametrize("status", [404, 403])
def test_daily_de_hoje_sem_arquivo_sai_como_adiado(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    """A noite, a B3 ainda nao ter publicado e esperado: sai 75, sem traceback."""
    from scanner import cli
    from scanner.ingest.download import AindaNaoPublicadoError, B3IndisponivelError

    etapas = _EtapasFalsas(monkeypatch)
    erro = AindaNaoPublicadoError("404") if status == 404 else B3IndisponivelError("403")
    _ingest_que_falha(monkeypatch, erro)
    monkeypatch.setattr(cli, "hoje_na_b3", lambda: date(2026, 9, 4))

    result = runner.invoke(app, ["daily", "--date", "2026-09-04"])

    assert result.exit_code == cli.SAIDA_ADIADO, result.output
    assert "[1/7] adiado" in result.output
    assert etapas.chamadas == [], "adiado nao calcula, nao notifica e nao poda"


def test_daily_de_pregao_passado_sem_arquivo_e_falha_de_verdade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """De manha o arquivo da vespera ja devia existir: ai e falha, com aviso."""
    from scanner import cli
    from scanner.ingest.download import AindaNaoPublicadoError

    _EtapasFalsas(monkeypatch)
    _ingest_que_falha(monkeypatch, AindaNaoPublicadoError("404"))
    monkeypatch.setattr(cli, "hoje_na_b3", lambda: date(2026, 9, 8))

    result = runner.invoke(app, ["daily", "--date", "2026-09-04"])

    assert result.exit_code not in (0, cli.SAIDA_ADIADO)
    assert isinstance(result.exception, AindaNaoPublicadoError)


def test_daily_diz_quanto_o_banco_ocupa(monkeypatch: pytest.MonkeyPatch) -> None:
    # O limite do plano gratuito do Neon e 0,5 GB: o log de cada pregao mostra
    # quanto ja foi, sem precisar abrir o painel.
    _EtapasFalsas(monkeypatch)
    result = runner.invoke(app, ["daily", "--date", "2026-09-04"])
    assert result.exit_code == 0, result.output
    assert "banco com 150 MB (daily_features 60 MB)" in result.output


# --- Rompimentos: `--migrar-antes` ---------------------------------------------


def _checagem_falsa(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Troca a checagem, o banco e a migracao e devolve a ordem das chamadas."""
    from scanner import calendar, cli, rompimentos
    from scanner.storage import engine as engine_mod
    from scanner.storage import migracao

    ordem: list[str] = []

    class _Relatorio:
        def summary(self) -> str:
            return "0 alertas ativos"

    def checar(*_a: object, **_k: object) -> _Relatorio:
        ordem.append("checar")
        return _Relatorio()

    def migrar(_engine: object) -> str | None:
        ordem.append("migrar")
        return None

    monkeypatch.setattr(calendar, "is_trading_day", lambda _dia: True)
    monkeypatch.setattr(engine_mod, "build_engine", lambda: object())
    monkeypatch.setattr(rompimentos, "checar_rompimentos", checar)
    monkeypatch.setattr(migracao, "migrar_se_preciso", migrar)
    monkeypatch.setattr(cli, "_notificador", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "_provedor_de_cotacoes", lambda: None)
    return ordem


def test_alerta_checar_migra_antes_de_checar(monkeypatch: pytest.MonkeyPatch) -> None:
    ordem = _checagem_falsa(monkeypatch)

    result = runner.invoke(app, ["alerta", "checar", "--migrar-antes"])

    assert result.exit_code == 0, result.output
    assert ordem == ["migrar", "checar"], "checar num schema velho e o que a opcao evita"


def test_alerta_checar_sem_a_opcao_nao_mexe_no_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rodando a mao na maquina, ninguem espera que o comando migre o banco.
    ordem = _checagem_falsa(monkeypatch)

    result = runner.invoke(app, ["alerta", "checar"])

    assert result.exit_code == 0, result.output
    assert ordem == ["checar"]


# --- semana montar ---------------------------------------------------------


def _semana_falsa(monkeypatch: pytest.MonkeyPatch, *, pregao_ausente: bool = False) -> list[object]:
    """Troca engine, montagem e gravacao; devolve as gravacoes feitas."""
    from scanner.semana import montagem
    from scanner.storage import engine as engine_mod
    from scanner.storage import repository

    gravacoes: list[object] = []
    payload = {"versao": 1, "semana": {"sexta": "2026-10-16"}}

    def montar(
        engine: object, config: object, semana: object, *, gravar_juros: bool = False
    ) -> dict[str, object]:
        if pregao_ausente:
            raise montagem.PregaoAusenteError("o pregao de 2026-10-16 ainda nao esta em daily_bars")
        gravacoes.append(("montou", semana, gravar_juros))
        return payload

    def gravar(engine: object, **kw: object) -> bool:
        gravacoes.append(kw)
        return True

    monkeypatch.setattr(engine_mod, "build_engine", lambda: object())
    monkeypatch.setattr(montagem, "montar_dados_de_mercado", montar)
    monkeypatch.setattr(montagem, "previa", lambda p: "PREVIA DE TESTE")
    monkeypatch.setattr(repository, "gravar_resumo_semanal", gravar)
    return gravacoes


def test_semana_montar_so_mostra_a_previa(monkeypatch: pytest.MonkeyPatch) -> None:
    gravacoes = _semana_falsa(monkeypatch)

    result = runner.invoke(app, ["semana", "montar", "--semana", "2026-10-14"])

    assert result.exit_code == 0
    assert "PREVIA DE TESTE" in result.output
    assert "[gravado]" not in result.output
    (montou,) = gravacoes  # nada gravado
    assert montou[0] == "montou"  # type: ignore[index]
    assert montou[2] is False  # type: ignore[index]  # o historico de juros tambem nao
    assert montou[1].sexta == date(2026, 10, 16)  # type: ignore[index]


def test_semana_montar_grava_com_a_sexta_nominal(monkeypatch: pytest.MonkeyPatch) -> None:
    gravacoes = _semana_falsa(monkeypatch)

    result = runner.invoke(app, ["semana", "montar", "--semana", "2026-10-16", "--gravar"])

    assert result.exit_code == 0
    assert "[gravado] semana de 2026-10-16" in result.output
    assert gravacoes[0][2] is True  # type: ignore[index]  # com --gravar, grava os juros
    gravado = gravacoes[-1]
    assert gravado["semana"] == date(2026, 10, 16)  # type: ignore[index]
    assert gravado["inicio"] == date(2026, 10, 9)  # type: ignore[index]
    assert gravado["fim"] == date(2026, 10, 16)  # type: ignore[index]
    assert gravado["substituir_enviado"] is False  # type: ignore[index]


def test_semana_montar_avisa_quando_o_resumo_ja_foi_enviado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scanner.storage import repository

    _semana_falsa(monkeypatch)
    monkeypatch.setattr(repository, "gravar_resumo_semanal", lambda *a, **k: False)

    result = runner.invoke(app, ["semana", "montar", "--semana", "2026-10-16", "--gravar"])

    assert result.exit_code == 0
    assert "[recusado]" in result.output
    assert "--substituir-enviado" in result.output


def test_semana_montar_pregao_ausente_sai_com_codigo_3(monkeypatch: pytest.MonkeyPatch) -> None:
    gravacoes = _semana_falsa(monkeypatch, pregao_ausente=True)

    result = runner.invoke(app, ["semana", "montar", "--semana", "2026-10-16", "--gravar"])

    assert result.exit_code == 3
    assert "[adiado]" in result.output
    assert gravacoes == []


def test_semana_montar_rejeita_data_invalida() -> None:
    result = runner.invoke(app, ["semana", "montar", "--semana", "ontem"])

    assert result.exit_code != 0


# --- semana juros ----------------------------------------------------------


def _juros_falso(
    monkeypatch: pytest.MonkeyPatch,
    por_serie: dict[str, int],
    erro_td: str | None = None,
    erro_selic: str | None = None,
) -> list[object]:
    """Troca engine, migracao e a gravacao do historico; devolve as chamadas."""
    from scanner.semana import montagem
    from scanner.storage import engine as engine_mod
    from scanner.storage import migracao

    chamadas: list[object] = []

    def gravar(engine: object, config: object, semana: object) -> montagem.HistoricoGravado:
        chamadas.append(semana)
        return montagem.HistoricoGravado(por_serie, erro_td, erro_selic)

    monkeypatch.setattr(engine_mod, "build_engine", lambda: object())
    monkeypatch.setattr(migracao, "migrar_se_preciso", lambda engine: chamadas.append("migrou"))
    monkeypatch.setattr(montagem, "gravar_historico_de_juros", gravar)
    # O comando nao monta o resumo: se tentar, o teste quebra.
    monkeypatch.setattr(montagem, "montar_dados_de_mercado", None)
    return chamadas


def test_semana_juros_grava_so_o_historico_ate_a_sexta(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas = _juros_falso(monkeypatch, {"pre_10a": 523, "selic": 523})

    result = runner.invoke(app, ["semana", "juros", "--semana", "2026-10-14"])

    assert result.exit_code == 0, result.output
    assert chamadas[0] == "migrou"
    assert chamadas[1].sexta == date(2026, 10, 16)  # type: ignore[attr-defined]
    assert "pre_10a: 523 semanas" in result.output
    assert "[gravado] 1046 taxas de juros ate a semana de 2026-10-16" in result.output


def test_semana_juros_avisa_a_fonte_fora_e_grava_a_outra(monkeypatch: pytest.MonkeyPatch) -> None:
    _juros_falso(monkeypatch, {"pre_1a": 496}, erro_selic="HTTP 502")

    result = runner.invoke(app, ["semana", "juros", "--semana", "2026-10-16"])

    assert result.exit_code == 0, result.output
    assert "[aviso] Selic indisponivel: HTTP 502" in result.output
    assert "[gravado]" in result.output


def test_semana_juros_sem_nada_gravado_sai_1(monkeypatch: pytest.MonkeyPatch) -> None:
    _juros_falso(monkeypatch, {}, erro_td="HTTP 503", erro_selic="HTTP 502")

    result = runner.invoke(app, ["semana", "juros", "--semana", "2026-10-16"])

    assert result.exit_code == 1
    assert "[erro] nenhuma taxa gravada" in result.output
    assert "[gravado]" not in result.output


# --- semana enviar ---------------------------------------------------------


class _Enviador:
    """Notificador falso: guarda o que seria enviado, ou falha como o Telegram."""

    def __init__(self, *, falha: bool = False) -> None:
        self.falha = falha
        self.enviados: list[str] = []

    def send_text(self, text: str) -> bool:
        from scanner.notify.telegram import TelegramError

        if self.falha:
            raise TelegramError("envio recusado: HTTP 500")
        self.enviados.append(text)
        return True


class _Cenario:
    def __init__(self) -> None:
        self.eventos: list[tuple[str, object]] = []
        self.enviador = _Enviador()
        self.ja_enviado = False
        # `gravar_juros` de cada montagem: o historico de juros so vai ao banco quando se grava.
        self.juros: list[bool] = []


def _enviar_falso(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ja_enviado: bool = False,
    pregao_ausente: bool = False,
    falha_no_envio: bool = False,
) -> _Cenario:
    """Troca banco, montagem, gravacao e notificador. Nada toca a rede."""
    from scanner import cli
    from scanner.semana import mensagem, montagem
    from scanner.storage import engine as engine_mod
    from scanner.storage import migracao, repository

    cenario = _Cenario()
    cenario.ja_enviado = ja_enviado
    cenario.enviador = _Enviador(falha=falha_no_envio)
    payload = {"versao": 1, "semana": {"sexta": "2026-10-16"}}

    def montar(
        engine: object, config: object, semana: object, *, gravar_juros: bool = False
    ) -> dict[str, object]:
        if pregao_ausente:
            raise montagem.PregaoAusenteError("o pregao de 2026-10-16 ainda nao esta em daily_bars")
        cenario.eventos.append(("montou", semana))
        cenario.juros.append(gravar_juros)
        return payload

    def gravar(engine: object, **kw: object) -> bool:
        cenario.eventos.append(("gravou", kw))
        return True

    def marcar(engine: object, semana: date, *, sobrescrever: bool = False) -> bool:
        cenario.eventos.append(("marcou", sobrescrever))
        return True

    monkeypatch.setattr(engine_mod, "build_engine", lambda: object())
    monkeypatch.setattr(migracao, "migrar_se_preciso", lambda engine: None)
    monkeypatch.setattr(montagem, "montar_dados_de_mercado", montar)
    monkeypatch.setattr(repository, "gravar_resumo_semanal", gravar)
    monkeypatch.setattr(repository, "resumo_semanal_enviado", lambda e, s: cenario.ja_enviado)
    monkeypatch.setattr(repository, "marcar_resumo_semanal_enviado", marcar)
    monkeypatch.setattr(cli, "_notificador", lambda settings, *, dry_run: cenario.enviador)
    monkeypatch.setattr(mensagem, "formatar_mensagem", lambda p, base: "MENSAGEM DE TESTE")
    return cenario


def _nomes(cenario: _Cenario) -> list[str]:
    return [nome for nome, _ in cenario.eventos]


def test_semana_enviar_pula_quando_ja_foi_enviado(monkeypatch: pytest.MonkeyPatch) -> None:
    cenario = _enviar_falso(monkeypatch, ja_enviado=True)

    result = runner.invoke(app, ["semana", "enviar", "--semana", "2026-10-16"])

    assert result.exit_code == 0
    assert "[pulado] o resumo da semana de 16/10/2026 ja foi enviado." in result.output
    assert cenario.eventos == [] and cenario.enviador.enviados == []


def test_semana_enviar_adiado_sai_com_codigo_3_sem_aviso(monkeypatch: pytest.MonkeyPatch) -> None:
    cenario = _enviar_falso(monkeypatch, pregao_ausente=True)

    result = runner.invoke(app, ["semana", "enviar", "--semana", "2026-10-16"])

    assert result.exit_code == 3
    assert "[adiado] o pregao de 16/10/2026 ainda nao esta no banco" in result.output
    assert cenario.enviador.enviados == [] and cenario.eventos == []


def test_semana_enviar_adiado_avisa_no_telegram_quando_pedido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cenario = _enviar_falso(monkeypatch, pregao_ausente=True)

    result = runner.invoke(
        app, ["semana", "enviar", "--semana", "2026-10-16", "--avisar-se-adiado"]
    )

    assert result.exit_code == 3
    assert cenario.enviador.enviados == [
        "⚠️ <b>Resumo da semana adiado</b>\n"
        "O pregão de 16/10/2026 ainda não está no banco. O resumo sai quando ele chegar."
    ]
    assert cenario.eventos == []


def test_semana_enviar_adiado_com_dry_run_nao_avisa(monkeypatch: pytest.MonkeyPatch) -> None:
    cenario = _enviar_falso(monkeypatch, pregao_ausente=True)

    result = runner.invoke(
        app, ["semana", "enviar", "--semana", "2026-10-16", "--avisar-se-adiado", "--dry-run"]
    )

    assert result.exit_code == 3
    assert cenario.enviador.enviados == []


def test_semana_enviar_dry_run_nao_grava_nem_envia(monkeypatch: pytest.MonkeyPatch) -> None:
    cenario = _enviar_falso(monkeypatch)

    result = runner.invoke(app, ["semana", "enviar", "--semana", "2026-10-16", "--dry-run"])

    assert result.exit_code == 0
    assert "MENSAGEM DE TESTE" in result.output
    assert _nomes(cenario) == ["montou"]
    assert cenario.enviador.enviados == []
    assert cenario.juros == [False]  # dry-run nao escreve nem o historico de juros


def test_semana_enviar_grava_envia_e_so_depois_marca(monkeypatch: pytest.MonkeyPatch) -> None:
    cenario = _enviar_falso(monkeypatch)
    enviador = cenario.enviador
    original = enviador.send_text

    def enviar(text: str) -> bool:
        cenario.eventos.append(("enviou", text))
        return original(text)

    monkeypatch.setattr(enviador, "send_text", enviar)

    result = runner.invoke(app, ["semana", "enviar", "--semana", "2026-10-16"])

    assert result.exit_code == 0
    assert "[enviado] resumo da semana de 16/10/2026" in result.output
    assert _nomes(cenario) == ["montou", "gravou", "enviou", "marcou"]
    assert enviador.enviados == ["MENSAGEM DE TESTE"]
    assert cenario.juros == [True]
    gravado = cenario.eventos[1][1]
    assert gravado["semana"] == date(2026, 10, 16)  # type: ignore[index]
    assert gravado["substituir_enviado"] is False  # type: ignore[index]


def test_semana_enviar_falha_de_envio_nao_marca(monkeypatch: pytest.MonkeyPatch) -> None:
    cenario = _enviar_falso(monkeypatch, falha_no_envio=True)

    result = runner.invoke(app, ["semana", "enviar", "--semana", "2026-10-16"])

    assert result.exit_code == 1
    assert "[enviado]" not in result.output
    assert "marcou" not in _nomes(cenario)


def test_semana_enviar_reenviar_substitui_e_marca_de_novo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cenario = _enviar_falso(monkeypatch, ja_enviado=True)

    result = runner.invoke(app, ["semana", "enviar", "--semana", "2026-10-16", "--reenviar"])

    assert result.exit_code == 0
    assert "[enviado] resumo da semana de 16/10/2026" in result.output
    assert len(cenario.enviador.enviados) == 1
    assert _nomes(cenario) == ["montou", "gravou", "marcou"]
    assert cenario.eventos[1][1]["substituir_enviado"] is True  # type: ignore[index]
    assert cenario.eventos[2] == ("marcou", True)


def test_semana_enviar_sem_telegram_configurado_nao_marca(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem segredo o notificador cai no terminal: isso nao pode virar 'enviado'."""
    from scanner import cli
    from scanner.notify.telegram import ConsoleNotifier

    cenario = _enviar_falso(monkeypatch)
    monkeypatch.setattr(cli, "_notificador", lambda settings, *, dry_run: ConsoleNotifier())

    result = runner.invoke(app, ["semana", "enviar", "--semana", "2026-10-16"])

    assert result.exit_code == 1
    assert "[enviado]" not in result.output
    assert "marcou" not in _nomes(cenario)


def test_semana_enviar_rejeita_data_invalida() -> None:
    result = runner.invoke(app, ["semana", "enviar", "--semana", "ontem"])
    assert result.exit_code != 0
