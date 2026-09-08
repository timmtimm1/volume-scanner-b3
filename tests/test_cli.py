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
        from scanner.alerts import ScanReport
        from scanner.digest import Resumo
        from scanner.ingest import pipeline
        from scanner.recompute import Contexto, RecomputeReport
        from scanner.storage import engine as engine_mod
        from scanner.storage import repository

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

        def resumo(*a: object, **k: object) -> Resumo:
            self.contextos.append(k.get("contexto"))
            anota("resumo", None)
            return Resumo(date(2026, 9, 4), pd.DataFrame(), 1, 0, 6.0, None)

        monkeypatch.setattr(digest, "run_resumo", resumo)
        monkeypatch.setattr(repository, "retention_cutoff", lambda *a: date(2025, 1, 30))
        monkeypatch.setattr(repository, "prune_bars", lambda *a: (anota("poda", None), (0, 0))[1])


def test_daily_roda_as_seis_etapas_do_pregao(monkeypatch: pytest.MonkeyPatch) -> None:
    etapas = _EtapasFalsas(monkeypatch)
    result = runner.invoke(app, ["daily", "--date", "2026-09-04"])

    assert result.exit_code == 0, result.output
    assert etapas.chamadas == ["ingest", "contexto", "metricas", "scan", "resumo", "poda"]
    for numero in range(1, 7):
        assert f"[{numero}/6]" in result.output


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
    assert etapas.chamadas == ["contexto", "scan", "resumo"]


# --- "ultimo": o pregao completo mais recente --------------------------------


def test_parse_trade_date_aceita_ultimo() -> None:
    from scanner.calendar import is_trading_day

    for token in ("ultimo", "ULTIMO", "last"):
        dia = parse_trade_date(token)
        assert dia < date.today(), "o ultimo pregao ja terminou; hoje pode nem ter aberto"
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
