"""Fontes externas de mercado do resumo semanal, uma por modulo.

Cada modulo tem uma funcao de parse PURA (texto ou JSON entra, dados saem) e uma
busca fina por HTTP. Falha de rede, status diferente de 200 ou formato
inesperado levantam `FonteIndisponivelError`: quem monta o resumo transforma
isso em `{"erro": ...}` no bloco, sem derrubar os outros.
"""

from __future__ import annotations

import httpx

TIMEOUT_SEGUNDOS = 20.0
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36"


class FonteIndisponivelError(Exception):
    """A fonte nao respondeu, respondeu erro ou mudou de formato."""

    def __init__(
        self,
        fonte: str,
        motivo: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(f"{fonte}: {motivo}")
        self.fonte = fonte
        self.motivo = motivo
        # Preenchidos so quando a fonte respondeu com erro HTTP: a CoinGecko
        # manda 429 com `Retry-After`, e quem chama decide se espera.
        self.status = status
        self.retry_after = retry_after


def baixar(
    fonte: str,
    url: str,
    *,
    cliente: httpx.Client | None = None,
    metodo: str = "GET",
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Uma requisicao com timeout e User-Agent de navegador; falha vira `FonteIndisponivelError`."""
    cabecalhos = {"User-Agent": USER_AGENT, **(headers or {})}
    proprio = cliente is None
    http = cliente if cliente is not None else httpx.Client(timeout=TIMEOUT_SEGUNDOS)
    try:
        resposta = http.request(metodo, url, data=data, headers=cabecalhos)
    except httpx.HTTPError as exc:
        raise FonteIndisponivelError(
            fonte, f"falha de rede ({exc.__class__.__name__}: {exc})"
        ) from exc
    finally:
        if proprio:
            http.close()
    if resposta.status_code != 200:
        espera = resposta.headers.get("Retry-After", "")
        raise FonteIndisponivelError(
            fonte,
            f"HTTP {resposta.status_code}",
            status=resposta.status_code,
            retry_after=float(espera) if espera.isdigit() else None,
        )
    return resposta
