"""Download dos arquivos COTAHIST da B3.

Padrao de URL verificado contra o servidor da B3:

    anual:  {BASE_URL}/COTAHIST_A{AAAA}.ZIP     ~80 MB
    diario: {BASE_URL}/COTAHIST_D{DDMMAAAA}.ZIP ~0,5 MB

Nao ha token nem autenticacao. O arquivo baixado fica em cache no disco; uma
segunda chamada nao rebaixa, salvo `force=True`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx

BASE_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist"
DEFAULT_CACHE = Path("data/raw")
TIMEOUT_SECONDS = 900.0
CHUNK_BYTES = 1 << 20


class DownloadError(Exception):
    """A B3 nao entregou o arquivo pedido."""


def annual_filename(year: int) -> str:
    """Nome do arquivo anual, como a B3 publica."""
    return f"COTAHIST_A{year}.ZIP"


def daily_filename(day: date) -> str:
    """Nome do arquivo diario: DDMMAAAA, nao AAAAMMDD."""
    return f"COTAHIST_D{day:%d%m%Y}.ZIP"


def _fetch(filename: str, destination: Path, *, force: bool) -> Path:
    """Baixa `filename` para `destination`, em streaming, se ainda nao existir."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 0 and not force:
        return destination

    url = f"{BASE_URL}/{filename}"
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        with httpx.stream("GET", url, timeout=TIMEOUT_SECONDS, follow_redirects=True) as response:
            if response.status_code == httpx.codes.NOT_FOUND:
                raise DownloadError(f"{filename} nao existe na B3 (404)")
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(CHUNK_BYTES):
                    handle.write(chunk)
    except httpx.HTTPError as exc:
        partial.unlink(missing_ok=True)
        raise DownloadError(f"falha ao baixar {filename}: {exc}") from exc

    # So promove o arquivo depois de completo, para o cache nunca guardar truncado.
    partial.replace(destination)
    return destination


def download_annual(year: int, cache: Path = DEFAULT_CACHE, *, force: bool = False) -> Path:
    """Arquivo anual do COTAHIST, usado na carga historica."""
    name = annual_filename(year)
    return _fetch(name, cache / name, force=force)


def download_daily(day: date, cache: Path = DEFAULT_CACHE, *, force: bool = False) -> Path:
    """Arquivo de um pregao, usado na carga incremental."""
    name = daily_filename(day)
    return _fetch(name, cache / name, force=force)
