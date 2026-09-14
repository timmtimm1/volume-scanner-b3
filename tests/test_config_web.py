"""O site repete alguns numeros do config.yaml; este teste impede que divirjam.

O site nao le o `config.yaml`: as fichas podem ser geradas sob demanda na
Vercel, onde o arquivo da raiz nao existe. Os valores ficam em
`web/src/lib/config.ts`, e mudar o `config.yaml` sem mudar la quebra aqui.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scanner.config import load_config

CONFIG_TS = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "config.ts"


def _numero(nome: str) -> float:
    """Valor numerico de `nome: 123` ou `const NOME = 123` no config.ts."""
    texto = CONFIG_TS.read_text(encoding="utf-8")
    achado = re.search(rf"\b{nome}\s*[:=]\s*([\d_]+(?:\.\d+)?)", texto)
    assert achado, f"{nome} nao encontrado em {CONFIG_TS.name}"
    return float(achado.group(1).replace("_", ""))


@pytest.mark.parametrize(
    ("nome_no_site", "valor_no_yaml"),
    [
        ("LIMIAR_DO_ALERTA", lambda c: c.alert.threshold),
        ("PISO_DE_VOLUME", lambda c: c.alert.min_volume_brl),
        ("janela", lambda c: c.universe.lookback_sessions),
        ("pisoMediana", lambda c: c.universe.min_median_volume_brl),
        ("coberturaMinima", lambda c: c.universe.min_session_coverage),
    ],
)
def test_site_usa_os_mesmos_numeros_do_config(
    repo_config_path: Path, nome_no_site: str, valor_no_yaml: object
) -> None:
    config = load_config(repo_config_path)
    esperado = float(valor_no_yaml(config))  # type: ignore[operator]
    assert _numero(nome_no_site) == esperado, (
        f"{nome_no_site} em web/src/lib/config.ts difere do config.yaml ({esperado})"
    )
