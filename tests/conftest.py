"""Fixtures compartilhadas."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_config_path() -> Path:
    """O `config.yaml` versionado do repositorio."""
    return PROJECT_ROOT / "config.yaml"


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Postgres local do docker-compose. Pula o teste se nao estiver de pe."""
    from sqlalchemy.exc import SQLAlchemyError

    from scanner.storage.engine import build_engine

    eng = build_engine()
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        pytest.skip(f"Postgres indisponivel ({exc.__class__.__name__}); rode docker compose up -d")
    yield eng
    eng.dispose()
