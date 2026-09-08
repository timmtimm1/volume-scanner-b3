"""Fixtures compartilhadas.

Os testes marcados `db` NAO usam o banco de trabalho. Eles rodam num banco
separado, criado na hora e migrado por Alembic. Isso existe porque
`metrics compute --mode full` faz TRUNCATE em `volume_metrics`: sem isolamento,
rodar a suite apagava as metricas da carga real.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_SUFFIX = "_pytest"


@pytest.fixture
def repo_config_path() -> Path:
    """O `config.yaml` versionado do repositorio."""
    return PROJECT_ROOT / "config.yaml"


def _base_url() -> str:
    from scanner.config import get_settings

    return get_settings().database_url.get_secret_value()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Banco isolado para os testes. Pula se o Postgres nao estiver de pe."""
    url = make_url(_base_url())
    nome_teste = f"{url.database}{TEST_DB_SUFFIX}"

    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            existe = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :nome"), {"nome": nome_teste}
            ).scalar()
            if not existe:
                conn.execute(text(f'CREATE DATABASE "{nome_teste}"'))
    except SQLAlchemyError as exc:
        pytest.skip(f"Postgres indisponivel ({exc.__class__.__name__}); rode docker compose up -d")
    finally:
        admin.dispose()

    destino = url.set(database=nome_teste)
    alembic = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic.set_main_option("script_location", str(PROJECT_ROOT / "src/scanner/storage/migrations"))
    alembic.set_main_option("sqlalchemy.url", destino.render_as_string(hide_password=False))
    command.upgrade(alembic, "head")

    eng = create_engine(destino, pool_pre_ping=True, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def working_engine() -> Iterator[Engine]:
    """O banco de trabalho, so para leitura.

    Usado pela validacao do calendario contra os pregoes que a B3 publicou de
    verdade: essa checagem so tem valor com a carga real presente.
    """
    from scanner.storage.engine import build_engine

    eng = build_engine()
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        pytest.skip(f"Postgres indisponivel ({exc.__class__.__name__})")
    yield eng
    eng.dispose()
