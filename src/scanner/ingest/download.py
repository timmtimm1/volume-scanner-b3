"""Download dos arquivos COTAHIST da B3.

Padrao de URL verificado contra o servidor da B3:

    anual:  {BASE_URL}/COTAHIST_A{AAAA}.ZIP     ~80 MB
    diario: {BASE_URL}/COTAHIST_D{DDMMAAAA}.ZIP ~0,5 MB

Nao ha token nem autenticacao. O arquivo baixado fica em cache no disco; uma
segunda chamada nao rebaixa, salvo `force=True`.
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import httpx

BASE_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist"
DEFAULT_CACHE = Path("data/raw")
TIMEOUT_SECONDS = 900.0
CHUNK_BYTES = 1 << 20

# O arquivo do pregao sai algumas horas depois do fechamento, com atraso
# variavel. Quatro tentativas espacadas de 5 minutos cobrem 15 minutos de
# espera, o que cabe no timeout de 30 do job diario.
TENTATIVAS_DIARIAS = 4
ESPERA_ENTRE_TENTATIVAS = 300.0


class DownloadError(Exception):
    """A B3 nao entregou o arquivo pedido."""


class DownloadTemporarioError(DownloadError):
    """Falha que esperar costuma resolver: arquivo nao publicado ou B3 fora do ar."""


class AindaNaoPublicadoError(DownloadTemporarioError):
    """O arquivo do pregao ainda nao existe na B3 (404).

    Separado do erro generico porque tem tratamento proprio: no dia do pregao a
    B3 leva horas para publicar, e um 404 logo apos o fechamento significa
    "espere", nao "deu errado".
    """


class B3IndisponivelError(DownloadTemporarioError):
    """A B3 recusou ou falhou do lado dela (403, 429 ou 5xx).

    Medido em 12/09/2026: as 02:42 de Brasilia a B3 respondeu 403 para o arquivo
    de sexta, que as 08:57 baixou normalmente. Nao era permissao, era a B3 fora
    do ar para aquele pedido -- e o retry, que so cobria 404, desistia na hora.
    """


# Status que a B3 devolve quando o problema e dela e passa sozinho.
STATUS_TEMPORARIOS = frozenset({403, 429})


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
                raise AindaNaoPublicadoError(f"{filename} ainda nao esta na B3 (404)")
            if response.status_code in STATUS_TEMPORARIOS or response.status_code >= 500:
                raise B3IndisponivelError(f"{filename}: a B3 respondeu {response.status_code}")
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


def download_daily(
    day: date,
    cache: Path = DEFAULT_CACHE,
    *,
    force: bool = False,
    tentativas: int = TENTATIVAS_DIARIAS,
    espera: float = ESPERA_ENTRE_TENTATIVAS,
) -> Path:
    """Arquivo de um pregao, usado na carga incremental.

    A B3 leva horas depois do fechamento para publicar o arquivo do dia, e o
    atraso varia. Um 404 quer dizer "ainda nao saiu"; 403, 429 e 5xx, "a B3
    esta com problema agora". Nos dois casos vale esperar e tentar de novo.
    Erro de rede do lado do runner continua subindo na hora.
    """
    name = daily_filename(day)
    destino = cache / name

    for tentativa in range(1, tentativas + 1):
        try:
            return _fetch(name, destino, force=force)
        except DownloadTemporarioError:
            if tentativa == tentativas:
                raise
            time.sleep(espera)

    raise AindaNaoPublicadoError(f"{name} nao apareceu em {tentativas} tentativas")
