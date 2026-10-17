"""O workflow do resumo semanal e a agenda externa que o dispara."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEMANA = PROJECT_ROOT / ".github" / "workflows" / "semana.yml"
CRON_EXTERNO = PROJECT_ROOT / ".github" / "cron-externo.yml"


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    return dict(yaml.safe_load(SEMANA.read_text(encoding="utf-8")))


def _passos(workflow: dict[Any, Any]) -> list[dict[str, Any]]:
    (job,) = workflow["jobs"].values()
    return list(job["steps"])


def _passo(workflow: dict[Any, Any], id_: str) -> dict[str, Any]:
    (passo,) = [p for p in _passos(workflow) if p.get("id") == id_]
    return passo


def test_so_dispara_de_fora(workflow: dict[Any, Any]) -> None:
    gatilhos: Any = workflow.get("on") or workflow.get(True)
    assert set(gatilhos) == {"workflow_dispatch"}
    assert set(gatilhos["workflow_dispatch"]["inputs"]) == {"semana", "reenviar"}
    assert gatilhos["workflow_dispatch"]["inputs"]["semana"]["default"] == "ultima"
    assert gatilhos["workflow_dispatch"]["inputs"]["reenviar"]["default"] is False


def test_permissao_minima_um_por_vez_e_teto_de_tempo(workflow: dict[Any, Any]) -> None:
    assert workflow["permissions"] == {"contents": "read"}
    (job,) = workflow["jobs"].values()
    assert job["concurrency"] == {"group": "semana", "cancel-in-progress": False}
    assert job["timeout-minutes"] == 20


def test_esta_na_agenda_externa_aos_sabados() -> None:
    agenda = yaml.safe_load(CRON_EXTERNO.read_text(encoding="utf-8"))
    jobs = [j for j in agenda["jobs"].values() if j["workflow"] == "semana.yml"]
    assert sorted(j["cron"] for j in jobs) == ["30 10 * * 6", "30 8 * * 6"]
    for job in jobs:
        assert job["porque"].strip()


def test_a_reserva_do_resumo_vem_depois_da_reserva_do_pregao() -> None:
    agenda = yaml.safe_load(CRON_EXTERNO.read_text(encoding="utf-8"))["jobs"]
    minuto, hora, *_ = agenda["daily-manha"]["cron"].split()
    manha_pregao = int(hora) * 60 + int(minuto)
    minuto, hora, *_ = agenda["semana-manha"]["cron"].split()
    assert int(hora) * 60 + int(minuto) >= manha_pregao + 45


def test_guarda_de_rerun_e_o_primeiro_passo(workflow: dict[Any, Any]) -> None:
    primeiro = _passos(workflow)[0]
    assert primeiro["id"] == "guarda"
    run = str(primeiro["run"])
    assert 'gh api "repos/$GITHUB_REPOSITORY/commits/main"' in run
    assert '[ "$COMMIT" != "$atual" ]' in run
    assert primeiro["env"]["TENTATIVA"] == "${{ github.run_attempt }}"


def test_le_os_segredos_pelos_nomes_certos(workflow: dict[Any, Any]) -> None:
    (job,) = workflow["jobs"].values()
    env = job["env"]
    assert env["SCANNER_DATABASE_URL"] == "${{ secrets.SCANNER_DATABASE_URL }}"
    assert env["SCANNER_TELEGRAM_BOT_TOKEN"] == "${{ secrets.SCANNER_TELEGRAM_BOT_TOKEN }}"
    assert env["SCANNER_TELEGRAM_CHAT_ID"] == "${{ secrets.SCANNER_TELEGRAM_CHAT_ID }}"
    assert env["SCANNER_WEB_BASE_URL"] == "${{ vars.SCANNER_WEB_BASE_URL }}"
    assert env["VERCEL_DEPLOY_HOOK"] == "${{ secrets.VERCEL_DEPLOY_HOOK }}"


def test_nenhum_segredo_escrito() -> None:
    texto = SEMANA.read_text(encoding="utf-8")
    assert "postgresql://" not in texto
    assert re.search(r"bot\d", texto) is None, "token do Telegram no arquivo"
    assert not re.search(r"hooks?/[A-Za-z0-9]{12,}", texto), "deploy hook no arquivo"


def test_migrations_sem_ressincronizar(workflow: dict[Any, Any]) -> None:
    assert _passo(workflow, "migrations")["run"].strip() == "uv run --no-sync alembic upgrade head"


def test_codigo_3_e_adiado_e_nao_falha(workflow: dict[Any, Any]) -> None:
    run = str(_passo(workflow, "resumo")["run"])
    assert "set -o pipefail" in run and "set +e" in run
    assert "tee /tmp/semana.log" in run
    assert '"$codigo" -eq 3' in run
    bloco = run[run.index('"$codigo" -eq 3') :]
    assert "adiado=true" in bloco and "::notice::" in bloco and "exit 0" in bloco
    assert 'exit "$codigo"' in run, "erro de verdade tem de derrubar o passo"


def test_passada_das_10h_pede_aviso_de_adiamento(workflow: dict[Any, Any]) -> None:
    run = str(_passo(workflow, "resumo")["run"])
    assert "TZ=America/Sao_Paulo date +%H" in run
    assert "--avisar-se-adiado" in run
    assert '--semana "$SEMANA" $REENVIAR $AVISO' in run


def test_enviado_so_quando_a_linha_de_sucesso_aparece(workflow: dict[Any, Any]) -> None:
    run = str(_passo(workflow, "resumo")["run"])
    assert "grep -q '^\\[enviado\\]' /tmp/semana.log" in run
    assert "enviado=true" in run


def test_rebuild_so_depois_de_enviar(workflow: dict[Any, Any]) -> None:
    condicao = str(_passo(workflow, "vercel")["if"])
    assert "steps.resumo.outputs.enviado == 'true'" in condicao
    assert "VERCEL_DEPLOY_HOOK != ''" in condicao
    assert "adiado" not in condicao


def test_aviso_de_falha_e_o_ultimo_e_nao_dispara_com_a_guarda(
    workflow: dict[Any, Any],
) -> None:
    ultimo = _passos(workflow)[-1]
    condicao = str(ultimo["if"])
    assert "failure()" in condicao
    assert "steps.guarda.outcome != 'failure'" in condicao
    assert "api.telegram.org/bot${SCANNER_TELEGRAM_BOT_TOKEN}" in str(ultimo["run"])
    run = str(ultimo["run"])
    for onde in ("dependencias", "segredos", "migrations", "resumo", "rebuild"):
        assert onde in run, f"o aviso nao diz quando falha {onde}"
