"""Migrations aplicadas so quando ha pendencia: `scanner.storage.migracao`."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from scanner.storage import migracao
from scanner.storage.models import SCHEMA

pytestmark = pytest.mark.db


@pytest.fixture
def upgrades(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Troca o `upgrade` do Alembic por um anotador: nenhum teste migra de fato."""
    chamadas: list[str] = []
    monkeypatch.setattr(
        migracao.command, "upgrade", lambda _config, alvo: chamadas.append(str(alvo))
    )
    return chamadas


@pytest.fixture
def banco_atrasado(engine: Engine) -> Iterator[str]:
    """Regrava `alembic_version` com uma revisao antiga e devolve a verdadeira."""
    atual = migracao.revisao_do_banco(engine)
    assert atual is not None
    tabela = f'"{SCHEMA}".alembic_version'
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {tabela} SET version_num = '0001'"))
    try:
        yield atual
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"UPDATE {tabela} SET version_num = :v"), {"v": atual})


def test_banco_em_dia_nao_chama_o_alembic(engine: Engine, upgrades: list[str]) -> None:
    # O caso de todas as passadas menos uma: o fixture `engine` ja migrou ate
    # o head, entao nao ha o que aplicar.
    assert migracao.migrar_se_preciso(engine) is None
    assert upgrades == []


def test_banco_atrasado_e_migrado_ate_o_head(
    engine: Engine, upgrades: list[str], banco_atrasado: str
) -> None:
    assert migracao.revisao_do_banco(engine) == "0001"
    assert migracao.migrar_se_preciso(engine) == banco_atrasado
    assert upgrades == ["head"]


def test_a_migracao_vai_para_o_banco_consultado_e_nao_para_o_do_ambiente(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, banco_atrasado: str
) -> None:
    """O `env.py` so le SCANNER_DATABASE_URL se ninguem definiu a URL.

    Sem a URL explicita, a pergunta iria a um banco e a migration a outro.
    """
    urls: list[str | None] = []
    monkeypatch.setattr(
        migracao.command,
        "upgrade",
        lambda config, _alvo: urls.append(config.get_main_option("sqlalchemy.url")),
    )

    migracao.migrar_se_preciso(engine)

    assert urls == [engine.url.render_as_string(hide_password=False)]


def test_sem_alembic_ini_falha_alto(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    # Seguir em frente calado seria checar alertas num schema possivelmente velho.
    monkeypatch.setattr(migracao, "ALEMBIC_INI", migracao.RAIZ / "nao-existe.ini")
    with pytest.raises(FileNotFoundError, match=r"alembic\.ini"):
        migracao.migrar_se_preciso(engine)
