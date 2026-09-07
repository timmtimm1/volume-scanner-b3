"""Configuracao: o config.yaml do repo carrega e os limites sao validados."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from scanner.config import AlertConfig, ScannerConfig, Settings, load_config


def test_repo_config_carrega(repo_config_path: Path) -> None:
    cfg = load_config(repo_config_path)
    assert cfg.alert.metric == "z_log"
    assert cfg.alert.threshold == 6.0
    assert cfg.alert.windows == [30, 45, 60]
    assert cfg.alert.require_all_windows is False
    assert cfg.alert.min_volume_brl == 500_000


def test_config_ausente_falha_alto(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nao_existe.yaml")


def test_yaml_vazio_usa_defaults(tmp_path: Path) -> None:
    empty = tmp_path / "config.yaml"
    empty.write_text("", encoding="utf-8")
    assert load_config(empty) == ScannerConfig()


def test_metrica_desconhecida_e_rejeitada() -> None:
    with pytest.raises(ValidationError):
        AlertConfig(metric="z_qualquer")  # type: ignore[arg-type]


@pytest.mark.parametrize("windows", [[], [1, 30], [30, 30]])
def test_janelas_invalidas(windows: list[int]) -> None:
    with pytest.raises(ValidationError):
        AlertConfig(windows=windows)


def test_janelas_saem_ordenadas() -> None:
    assert AlertConfig(windows=[60, 30, 45]).windows == [30, 45, 60]


def test_threshold_precisa_ser_positivo() -> None:
    with pytest.raises(ValidationError):
        AlertConfig(threshold=0)


def test_segredos_nao_vazam_no_repr() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://u:senha_secreta@host/db",  # type: ignore[arg-type]
        telegram_bot_token="token_secreto",  # type: ignore[arg-type]
    )
    texto = repr(settings) + str(settings.database_url) + str(settings.telegram_bot_token)
    assert "senha_secreta" not in texto
    assert "token_secreto" not in texto
    assert settings.database_url.get_secret_value().endswith("@host/db")
