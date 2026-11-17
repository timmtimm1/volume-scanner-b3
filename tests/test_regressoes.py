"""Regressoes de erros que ja aconteceram e nao tinham outro teste a travar.

O catalogo completo (incidente -> teste) esta no README, secao "Testes de
regressao". Os incidentes que ja tinham teste ficam nos arquivos deles; aqui
so os que estavam soltos. Sem rede, sem banco.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scanner.cotacoes import yahoo as yahoo_cotacoes
from scanner.semana.fontes import yahoo as yahoo_semana

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = PROJECT_ROOT / "src" / "scanner" / "storage" / "migrations" / "versions"
WORKFLOWS = sorted((PROJECT_ROOT / ".github" / "workflows").glob("*.yml"))


def _variavel(texto: str, nome: str) -> str | None:
    achou = re.search(rf'^{nome}\s*(?::[^=\n]+)?=\s*(?:"([^"]*)"|None)', texto, re.MULTILINE)
    return achou.group(1) if achou else None


def test_migrations_tem_numero_unico_e_cadeia_linear() -> None:
    """17/10/2026: dois branches criaram a migration 0010 e colidiram no banco.

    Falha se dois arquivos repetem o numero, se o prefixo do nome difere da
    `revision`, se o docstring mente, ou se a cadeia bifurca (duas cabecas).
    """
    arquivos = sorted(VERSIONS.glob("[0-9]*.py"))
    assert arquivos, "nenhuma migration encontrada"
    revisoes: dict[str, str | None] = {}
    for arquivo in arquivos:
        texto = arquivo.read_text(encoding="utf-8")
        revision = _variavel(texto, "revision")
        down = _variavel(texto, "down_revision")
        prefixo = arquivo.name.split("_")[0]
        assert revision == prefixo, f"{arquivo.name}: revision {revision!r} != prefixo {prefixo!r}"
        assert revision not in revisoes, f"{arquivo.name}: numero {revision} repetido"
        assert f"Revision ID: {revision}\n" in texto, f"{arquivo.name}: docstring Revision ID"
        assert f"Revises: {down or ''}".rstrip() in texto, f"{arquivo.name}: docstring Revises"
        revisoes[revision] = down

    assert sum(1 for d in revisoes.values() if d is None) == 1, "deve haver uma raiz so"
    pais = [d for d in revisoes.values() if d is not None]
    assert len(pais) == len(set(pais)), "duas migrations partem da mesma (bifurcacao)"
    assert set(pais) <= set(revisoes), "down_revision aponta para migration que nao existe"
    cabecas = set(revisoes) - set(pais)
    assert cabecas == {max(revisoes)}, f"cabecas {sorted(cabecas)}; a unica deve ser a maior"


@pytest.mark.parametrize(
    "agente",
    [yahoo_cotacoes.CABECALHOS["User-Agent"], yahoo_semana.USER_AGENT],
    ids=["cotacoes", "semana"],
)
def test_yahoo_usa_o_user_agent_do_projeto_e_nao_o_de_navegador(agente: str) -> None:
    """17/10/2026: com o UA de navegador (Chrome/130) o Yahoo responde 429 sempre.

    Medido: o UA do projeto da 200. Falha se qualquer cliente Yahoo voltar a
    se passar por navegador.
    """
    assert "volume-scanner-b3" in agente
    for navegador in ("Chrome", "Safari", "Firefox", "AppleWebKit"):
        assert navegador not in agente


def test_env_example_aponta_o_desenvolvimento_para_o_postgres_local() -> None:
    """08/09/2026 (#12): o .env de dev apontava para o Neon e a suite criava banco la.

    Falha se a linha ATIVA de SCANNER_DATABASE_URL do exemplo deixar de ser local.
    """
    linhas = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    ativas = [x for x in linhas if x.startswith("SCANNER_DATABASE_URL=")]
    assert len(ativas) == 1
    assert "localhost" in ativas[0] and "neon" not in ativas[0].lower()


@pytest.mark.parametrize("arquivo", WORKFLOWS, ids=lambda p: p.name)
def test_nenhum_workflow_tem_agendador_nativo_do_github(arquivo: Path) -> None:
    """14/09/2026 (#29): o `schedule` nativo falhava em silencio e duplicava o cron externo.

    Todo workflow que nao e de CI roda so por `workflow_dispatch`/`workflow_call`;
    quem agenda e `.github/cron-externo.yml`.
    """
    dados: dict[Any, Any] = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
    gatilhos: Any = dados.get("on") or dados.get(True)
    nomes: set[str] = {gatilhos} if isinstance(gatilhos, str) else set(gatilhos)
    assert "schedule" not in nomes, f"{arquivo.name} voltou a ter schedule nativo"
    if arquivo.name != "ci.yml":
        assert nomes & {"workflow_dispatch", "workflow_call"}, f"{arquivo.name} sem como disparar"


@pytest.mark.parametrize("nome", ["pregao.yml", "fundamentos-b3.yml"])
def test_toda_carga_de_fundamentos_e_seguida_da_conferencia(nome: str) -> None:
    """15/11/2026: a carga ouviu "sem mudanca" de um cache e o site ficou sem o 3T26.

    A carga confia na resposta da CVM; quem pega o erro e a conferencia, que
    pergunta a origem por conta propria. Falha se um workflow carregar os
    fundamentos e nao conferir depois, ou se a conferencia puder derrubar o job
    (ela so avisa: o pregao nao depende dos fundamentos).
    """
    arquivo = PROJECT_ROOT / ".github" / "workflows" / nome
    dados: dict[Any, Any] = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
    passos = next(iter(dados["jobs"].values()))["steps"]
    comandos = [str(p.get("run", "")) for p in passos]
    carga = next(i for i, c in enumerate(comandos) if "fundamentos atualizar" in c)
    conferencia = next((i for i, c in enumerate(comandos) if "fundamentos conferir" in c), None)
    assert conferencia is not None, f"{nome} carrega os fundamentos e nao confere"
    assert conferencia > carga, f"{nome} confere antes de carregar"
    assert passos[conferencia].get("continue-on-error") is True
    aviso = [p for p in passos if "steps.conferencia.outcome == 'failure'" in str(p.get("if", ""))]
    assert aviso, f"{nome}: a conferencia falha e ninguem e avisado"


@pytest.mark.parametrize("arquivo", WORKFLOWS, ids=lambda p: p.name)
def test_nenhuma_expressao_devolve_texto_vazio_no_meio_do_e_ou(arquivo: Path) -> None:
    """17/11/2026: `inputs.refazer && '' || '--so-se-faltar'` ignorava o refazer.

    No GitHub Actions o texto vazio e falso: `x && '' || y` vale sempre `y`.
    O jeito certo e negar antes (`!x && y || ''`), com o texto vazio no fim.
    """
    for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
        codigo = linha.split("#", 1)[0]
        assert not re.search(r"&&\s*''\s*\|\|", codigo), (
            f"{arquivo.name}:{numero}: `&& '' ||` sempre cai no lado do ||"
        )


def _passos_que_rodam_sem_dependencias() -> list[tuple[str, str]]:
    """(workflow, comando) de todo passo que chama o Python do runner com `PYTHONPATH=src`.

    Esses passos rodam ANTES do `uv sync`: so a biblioteca padrao existe ali.
    """
    achados: list[tuple[str, str]] = []
    for arquivo in WORKFLOWS:
        dados = yaml.safe_load(arquivo.read_text(encoding="utf-8")) or {}
        for job in (dados.get("jobs") or {}).values():
            for passo in job.get("steps") or []:
                for linha in str(passo.get("run") or "").splitlines():
                    achou = re.search(r'PYTHONPATH=src python3 -c "(.+)"\s*$', linha.strip())
                    if achou:
                        achados.append((arquivo.name, achou.group(1)))
    return achados


def test_passo_sem_dependencias_roda_so_com_a_biblioteca_padrao() -> None:
    """17/11/2026: o `import numpy` no topo de `scanner.mercado` derrubou o `rompimentos`.

    O passo "Hoje e pregao?" chama `scanner.calendar` com o Python do runner,
    antes de instalar as dependencias. Desde a aba Cripto o `calendar` importa
    o `mercado`, que importava o numpy: `ModuleNotFoundError` em toda passada do
    pregao. Aqui o mesmo comando, tirado do proprio workflow, roda num Python
    sem site-packages (`-S`): sai 0 (pregao) ou 10 (nao e pregao), nunca erro.
    """
    import subprocess
    import sys

    passos = _passos_que_rodam_sem_dependencias()
    assert passos, "nenhum passo com PYTHONPATH=src achado nos workflows"
    for workflow, comando in passos:
        resultado = subprocess.run(
            [sys.executable, "-S", "-c", comando.replace('\\"', '"')],
            cwd=PROJECT_ROOT,
            env={"PYTHONPATH": "src", "PATH": ""},
            capture_output=True,
            text=True,
            check=False,
        )
        assert resultado.returncode in (0, 10), f"{workflow}: {resultado.stderr[-600:]}"
