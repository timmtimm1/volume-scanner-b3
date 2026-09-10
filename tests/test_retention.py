"""Retencao dos ultimos N pregoes (secao 5 do plano) e o workflow diario."""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import Engine, delete, select

from scanner.calendar import sessions_before
from scanner.storage.engine import session_scope
from scanner.storage.models import DailyBar, Event, VolumeMetric
from scanner.storage.repository import (
    count_bars,
    prune_bars,
    retention_cutoff,
    sessions_stored,
    upsert_metrics,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "daily.yml"
WORKFLOWS = sorted((PROJECT_ROOT / ".github" / "workflows").glob("*.yml"))
CRON_EXTERNO = PROJECT_ROOT / ".github" / "cron-externo.yml"

FIM = date(2026, 6, 30)
SESSOES = 50
TICKER = "ZRET3"


@pytest.fixture
def carga(engine: Engine) -> Iterator[list[date]]:
    """50 pregoes de um papel, com metrica e um evento antigo."""
    dias = sessions_before(FIM, SESSOES, inclusive=True)
    with session_scope(engine) as s:
        s.execute(delete(Event).where(Event.ticker == TICKER))
        s.execute(delete(VolumeMetric).where(VolumeMetric.ticker == TICKER))
        s.execute(delete(DailyBar).where(DailyBar.ticker == TICKER))
        s.add_all(
            [
                DailyBar(
                    ticker=TICKER,
                    trade_date=dia,
                    close=10.0,
                    volume_financial=1_000_000 * (1 + 0.1 * math.sin(i)),
                    volume_shares=100_000,
                    trades_count=300,
                    trades_censored=False,
                )
                for i, dia in enumerate(dias)
            ]
        )
        # Um evento no pregao mais antigo, que a poda vai deixar para tras.
        s.add(
            Event(
                ticker=TICKER,
                trade_date=dias[0],
                max_z_log=7.5,
                triggered_windows=[30],
                volume_financial=9_000_000,
                features={"ret_day": 0.1},
            )
        )
    yield dias
    with session_scope(engine) as s:
        s.execute(delete(Event).where(Event.ticker == TICKER))
        s.execute(delete(VolumeMetric).where(VolumeMetric.ticker == TICKER))
        s.execute(delete(DailyBar).where(DailyBar.ticker == TICKER))


pytestmark = pytest.mark.db


def test_retention_cutoff_aponta_o_primeiro_pregao_mantido(
    engine: Engine, carga: list[date]
) -> None:
    assert retention_cutoff(engine, 10) == carga[-10]


def test_sem_pregoes_suficientes_nao_poda(engine: Engine, carga: list[date]) -> None:
    antes = count_bars(engine)
    assert prune_bars(engine, SESSOES + 100) == (0, 0)
    assert count_bars(engine) == antes


def test_poda_deixa_exatamente_a_janela_pedida(engine: Engine, carga: list[date]) -> None:
    prune_bars(engine, 20)
    assert sessions_stored(engine) == 20
    with engine.connect() as conn:
        restantes = set(conn.execute(select(DailyBar.trade_date).distinct()).scalars())
    assert restantes == set(carga[-20:])


def test_poda_leva_as_metricas_junto(engine: Engine, carga: list[date]) -> None:
    import pandas as pd

    metricas = pd.DataFrame(
        {
            "ticker": TICKER,
            "trade_date": carga,
            "window_size": 30,
            "z_log": 1.0,
            "z_raw": 1.0,
            "z_robust": 1.0,
            "rvol": 1.0,
        }
    )
    upsert_metrics(engine, metricas)

    _, removidas = prune_bars(engine, 20)
    assert removidas == SESSOES - 20
    with engine.connect() as conn:
        sobraram = conn.execute(
            select(VolumeMetric.trade_date).where(VolumeMetric.ticker == TICKER)
        ).scalars()
        assert min(sobraram) == carga[-20]


def test_poda_nunca_apaga_evento(engine: Engine, carga: list[date]) -> None:
    # A ficha do papel marca eventos antigos mesmo quando as barras ja sairam.
    prune_bars(engine, 5)
    with engine.connect() as conn:
        eventos = conn.execute(select(Event).where(Event.ticker == TICKER)).all()
    assert len(eventos) == 1


def test_keep_invalido_falha_alto(engine: Engine) -> None:
    with pytest.raises(ValueError, match="ao menos 1"):
        prune_bars(engine, 0)


# --- Workflow diario ---------------------------------------------------------


def _passos_do_job(workflow: dict[Any, Any]) -> list[dict[str, Any]]:
    """Os passos do unico job do workflow, na ordem em que rodam."""
    jobs = workflow["jobs"]
    (job,) = jobs.values()
    return list(job["steps"])


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    if not WORKFLOW.is_file():
        pytest.skip("daily.yml ainda nao esta no repositorio (falta o escopo workflow no gh)")
    return dict(yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")))


def _agenda_externa() -> dict[str, Any]:
    """A agenda que vive no cron-job.org, declarada em `.github/cron-externo.yml`."""
    if not CRON_EXTERNO.is_file():
        pytest.skip("cron-externo.yml ainda nao esta no repositorio")
    return dict(yaml.safe_load(CRON_EXTERNO.read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    "comando",
    [
        "alembic upgrade head",
        # As seis etapas do pregao vivem dentro do `daily`; que ele as execute
        # todas e o que `test_daily_roda_as_seis_etapas_do_pregao` garante.
        "scanner daily",
    ],
)
def test_workflow_roda_o_pipeline_completo(workflow: dict[Any, Any], comando: str) -> None:
    assert comando in WORKFLOW.read_text(encoding="utf-8")


def test_workflow_e_disparado_de_fora_e_nao_pelo_agendador_do_github(
    workflow: dict[Any, Any],
) -> None:
    """Sem `on: schedule`: quem agenda e o cron externo de `cron-externo.yml`.

    O agendador nativo do GitHub nao entrega de forma confiavel em repositorio
    publico gratuito. Deixar os dois ligados faria o `daily` rodar duas vezes
    nos dias em que o nativo funciona, reprocessando o mesmo pregao.
    """
    gatilhos = workflow.get("on") or workflow.get(True)
    assert isinstance(gatilhos, dict)
    assert "workflow_dispatch" in gatilhos
    assert "schedule" not in gatilhos, (
        "o agendador nativo voltou; ou ele sai, ou o job roda duas vezes por dia"
    )


def test_agenda_externa_roda_de_manha_e_processa_o_pregao_anterior() -> None:
    """07:40 em Brasilia, de terca a sabado.

    Rodar na mesma noite nao sobreviveu a B3: as 20:26 BRT o arquivo do dia
    ainda dava 404. De manha o arquivo do dia anterior esta publicado ha horas.

    Tem de terminar antes das 10h, que e quando o pregao abre -- e ai a leitura
    deixa de ser preparacao e vira reacao.

    O horario mudou de arquivo, nao de natureza: continua sendo decisao do
    projeto, so que agora aplicada por um painel de fora. Se este teste sumisse
    junto com o `schedule`, a janela util deixaria de ser verificada por
    qualquer coisa.
    """
    agenda = _agenda_externa()
    # O fuso do job e Brasilia, entao a hora do cron ja e a hora de Brasilia.
    assert agenda["timezone"] == "America/Sao_Paulo"

    minuto, hora, *resto = str(agenda["jobs"]["daily"]["cron"]).split()
    assert 6 <= int(hora) < 10, "fora da janela util: depois das 10h o pregao ja abriu"
    assert minuto != "0", "minuto 0 cai na fila da hora cheia"
    # Terca a sabado: cada sessao e processada na manha seguinte, e a manha
    # seguinte a sexta e o sabado.
    assert resto == ["*", "*", "2-6"]


def test_agenda_externa_cobre_todo_workflow_sem_agendador_proprio() -> None:
    """Nenhum workflow agendado pode ficar sem quem o dispare.

    O modo de falhar aqui e silencioso: um workflow que perde o `schedule` e
    nao entra no painel simplesmente para de rodar, e o sintoma e ausencia de
    mensagem -- indistinguivel de "nao havia nada para avisar".
    """
    agenda = _agenda_externa()
    declarados = {str(j["workflow"]) for j in agenda["jobs"].values()}

    for arquivo in WORKFLOWS:
        conteudo = dict(yaml.safe_load(arquivo.read_text(encoding="utf-8")))
        gatilhos = conteudo.get("on") or conteudo.get(True)
        assert isinstance(gatilhos, dict)
        # `ci.yml` roda por push/PR: nao precisa de agenda nenhuma.
        if {"push", "pull_request"} & set(gatilhos):
            continue
        assert arquivo.name in declarados, (
            f"{arquivo.name} nao tem agendador proprio nem esta em cron-externo.yml"
        )

    for nome in declarados:
        assert (PROJECT_ROOT / ".github" / "workflows" / nome).is_file(), (
            f"cron-externo.yml agenda {nome}, que nao existe"
        )


def test_workflow_pede_o_ultimo_pregao_e_nao_o_dia_de_hoje(
    workflow: dict[Any, Any],
) -> None:
    # De manha "today" seria o pregao que ainda nem abriu.
    (job,) = workflow["jobs"].values()
    assert "'ultimo'" in str(job["env"]["PREGAO"])
    assert "'today'" not in str(job["env"]["PREGAO"])


def test_workflow_le_os_segredos_pelos_nomes_certos(workflow: dict[Any, Any]) -> None:
    texto = WORKFLOW.read_text(encoding="utf-8")
    for nome in (
        "SCANNER_DATABASE_URL",
        "SCANNER_TELEGRAM_BOT_TOKEN",
        "SCANNER_TELEGRAM_CHAT_ID",
    ):
        assert f"secrets.{nome}" in texto, f"{nome} nao vem de secrets"
    # Nenhum valor de segredo pode estar escrito no arquivo. O aviso de falha
    # chama a api.telegram.org, mas monta a URL com a variavel de ambiente: um
    # token de verdade e "bot" seguido de digitos, e isso nao pode aparecer.
    assert "postgresql://" not in texto
    assert re.search(r"bot\d", texto) is None, "token do Telegram escrito no arquivo"


def test_workflow_avisa_no_telegram_quando_falha(workflow: dict[Any, Any]) -> None:
    """Dia quebrado nao pode chegar no celular igual a dia calmo: como silencio.

    O passo tem de ser o ultimo (para alcancar falha em qualquer anterior) e
    nao pode depender do Python, que e justamente o que pode ter quebrado.
    """
    passos = _passos_do_job(workflow)
    ultimo = passos[-1]

    assert "failure()" in str(ultimo.get("if", "")), "o aviso nao dispara em falha"
    assert "api.telegram.org" in str(ultimo.get("run", ""))
    assert "uv run" not in str(ultimo.get("run", "")), "o aviso nao pode depender do Python"


def test_aviso_de_falha_diz_onde_parou(workflow: dict[Any, Any]) -> None:
    """O aviso consulta o resultado de passos que existem de verdade.

    `steps.<id>.outcome` de um id inexistente vira string vazia sem erro: a
    mensagem degradaria para "passo desconhecido" e ninguem perceberia.
    """
    passos = _passos_do_job(workflow)
    ids = {str(p["id"]) for p in passos if "id" in p}
    citados = set(re.findall(r"steps\.([A-Za-z0-9_-]+)\.outcome", WORKFLOW.read_text("utf-8")))

    assert citados, "o aviso nao consulta o resultado de nenhum passo"
    assert citados <= ids, f"o aviso cita ids que nao existem: {sorted(citados - ids)}"


def test_saida_do_pregao_nao_mascara_o_codigo_de_saida(workflow: dict[Any, Any]) -> None:
    # O `tee` que alimenta o aviso troca o codigo de saida pelo dele: sem
    # pipefail, um scanner que morre passaria como sucesso e o dia sumiria.
    (pregao,) = [p for p in _passos_do_job(workflow) if p.get("id") == "pregao"]
    run = str(pregao.get("run", ""))
    assert "tee" in run
    assert "set -o pipefail" in run, "tee sem pipefail esconde a falha"


@pytest.mark.parametrize("arquivo", WORKFLOWS, ids=lambda p: p.name)
def test_nenhum_workflow_tem_segredo_escrito(arquivo: Path) -> None:
    """Vale para todo workflow, nao so o diario.

    O repositorio e publico e o GitHub so mascara `secrets` no log -- um valor
    escrito no arquivo fica a vista de qualquer um, para sempre, inclusive no
    historico do git depois de removido.
    """
    texto = arquivo.read_text(encoding="utf-8")
    assert "postgresql://" not in texto, "connection string no arquivo"
    # Um token do Telegram e "bot" seguido de digitos; a URL montada com a
    # variavel de ambiente vira "bot$" ou "bot${", e passa.
    assert re.search(r"bot\d", texto) is None, "token do Telegram no arquivo"
    assert not re.search(r"hooks?/[A-Za-z0-9]{12,}", texto), "deploy hook no arquivo"


def test_guarda_impede_teste_de_abrir_o_banco_de_trabalho() -> None:
    """A guarda que fecha o buraco que ja apagou metricas de producao duas vezes.

    Se este teste parar de levantar erro, um teste distraido volta a poder
    truncar a tabela de metricas do banco real.
    """
    from scanner.storage.engine import build_engine

    with pytest.raises(RuntimeError, match="banco de trabalho"):
        build_engine()
