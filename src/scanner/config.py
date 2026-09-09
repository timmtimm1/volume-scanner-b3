"""Configuracao do scanner.

Parametros operacionais vem de `config.yaml` (versionado).
Segredos vem exclusivamente do ambiente, com prefixo `SCANNER_`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"

Metric = Literal["z_log", "z_raw", "z_robust"]


class AlertConfig(BaseModel):
    """Regra de disparo (secao 4 do plano)."""

    metric: Metric = "z_log"
    threshold: float = 6.0
    windows: list[int] = Field(default_factory=lambda: [30, 45, 60])
    require_all_windows: bool = False
    min_volume_brl: float = 500_000.0

    @field_validator("windows")
    @classmethod
    def _validate_windows(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("alert.windows nao pode ser vazio")
        if any(w < 2 for w in value):
            raise ValueError("alert.windows: janela minima e 2 pregoes")
        if len(set(value)) != len(value):
            raise ValueError("alert.windows tem janelas repetidas")
        return sorted(value)

    @field_validator("threshold")
    @classmethod
    def _validate_threshold(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("alert.threshold deve ser positivo")
        return value


class DigestConfig(BaseModel):
    """Resumo diario enviado depois do scan (fora do plano original).

    Ordena pelo mesmo z-score que dispara o alerta, so que sem o corte: mostra
    os papeis que mais fugiram do proprio normal no pregao, tenham cruzado o
    limiar ou nao. Nao filtra por merito nem preve nada -- e o mesmo numero da
    regra da secao 4, ordenado.
    """

    enabled: bool = True
    top_n: int = 10
    # Janela do z usada no ranking. A menor e a mais sensivel.
    window: int = 30

    @field_validator("top_n")
    @classmethod
    def _validate_top_n(cls, value: int) -> int:
        if not 1 <= value <= 50:
            raise ValueError("digest.top_n precisa ficar entre 1 e 50")
        return value


class IngestConfig(BaseModel):
    """Filtros posicionais e validacao do COTAHIST (secao 2 do plano)."""

    tipreg: str = "01"
    codbdi: str = "02"
    tpmerc: str = "010"
    price_check_tolerance: float = 0.01
    price_check_max_failure: float = 0.005
    # Como validar VOLTOT contra PREMED x QUATOT / FATCOT:
    #   "relative"   - desvio relativo <= price_check_tolerance (a regra do plano)
    #   "truncation" - VOLTOT dentro de [PREMED, PREMED+0,01) x QUATOT / FATCOT
    # PREMED e truncado a 2 casas, entao para papel abaixo de R$ 1,00 o erro de
    # quantizacao sozinho passa de 1% e "relative" e inalcancavel. Ver README.
    price_check_mode: Literal["relative", "truncation"] = "truncation"


class UniverseConfig(BaseModel):
    """Filtro de liquidez do universo (F1)."""

    min_median_volume_brl: float = 500_000.0
    lookback_sessions: int = 60
    # Fracao minima dos pregoes da janela em que o papel negociou. E o que
    # torna "ticker ativo" verificavel: sem isso, um papel que negociou 2 de 60
    # pregoes com volume alto teria mediana alta e entraria no universo.
    min_session_coverage: float = 0.8


class RetentionConfig(BaseModel):
    """Janela de barras mantida no banco hospedado (secao 5 do plano)."""

    keep_sessions: int = 400


class ScannerConfig(BaseModel):
    """Conteudo completo de `config.yaml`."""

    alert: AlertConfig = Field(default_factory=AlertConfig)
    digest: DigestConfig = Field(default_factory=DigestConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)


class Settings(BaseSettings):
    """Segredos e enderecos, sempre vindos do ambiente."""

    model_config = SettingsConfigDict(
        env_prefix="SCANNER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://scanner:scanner@localhost:5432/scanner"
    )
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    # Opcional: sem ele a brapi aceita lotes de ate 3 papeis e o Yahoo cobre o
    # resto. Com ele, lotes de 10 e menos chamadas.
    brapi_token: SecretStr | None = None
    web_base_url: str = "http://localhost:3000"
    config_path: Path = DEFAULT_CONFIG_PATH


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings do ambiente, resolvidas uma vez por processo."""
    return Settings()


def load_config(path: Path | None = None) -> ScannerConfig:
    """Le e valida `config.yaml`."""
    resolved = path if path is not None else get_settings().config_path
    if not resolved.is_file():
        raise FileNotFoundError(f"config.yaml nao encontrado em {resolved}")

    raw: Any = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"{resolved} deve conter um mapeamento no topo")
    return ScannerConfig.model_validate(raw)
