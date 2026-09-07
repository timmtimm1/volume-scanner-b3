"""Fixtures compartilhadas."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_config_path() -> Path:
    """O `config.yaml` versionado do repositorio."""
    return PROJECT_ROOT / "config.yaml"
