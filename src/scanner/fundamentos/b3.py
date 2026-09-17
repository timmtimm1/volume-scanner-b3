"""Busca na B3 de qual empresa e um ticker -- o plano B do FCA da CVM.

Usado so para os tickers que o FCA nao declara (medido em 17/09/2026: 30 de
368). Sao dois endpoints nao documentados, os mesmos que o site da B3 usa por
baixo, com o payload em JSON codificado em base64 no caminho da URL.

O resultado da busca NUNCA e aceito de cara. O campo `issuingCompany` da B3
parece o prefixo do ticker, mas nem sempre e: procurar "EMBR3" devolve a
EMBRAST INDSTRIA E COMERCIO (codeCVM 917848, que nem registro na CVM tem), e
nao a Embraer (codeCVM 20087, que la aparece como "EMBJ"). Por isso todo
candidato passa por duas guardas antes de virar ligacao:

1. o `codeCVM` dele precisa existir no cadastro da CVM (quem confere e
   `carga.py`, que tem o cadastro em maos);
2. o ticker procurado precisa estar entre os codigos que a propria B3 lista
   para aquela empresa (`code` e `otherCodes` do detalhe) -- e o que esta
   funcao aqui confere.

Aceitar por semelhanca de nome ou por prefixo colaria o balanco de uma
empresa no papel de outra, que e o pior erro possivel nesta feature.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall"
TIMEOUT_SECONDS = 30.0
USER_AGENT = "Mozilla/5.0 (compatible; volume-scanner-b3/1.0)"

# Quantos candidatos da busca valem a pena conferir. A B3 devolve os mais
# parecidos primeiro; abrir a lista inteira so gastaria requisicao.
MAX_CANDIDATOS = 3

TENTATIVAS_PADRAO = 3
ESPERA_PADRAO = 5.0

# Status que valem retry: a B3 muitas vezes se recupera sozinha.
_STATUS_TEMPORARIOS = frozenset({429})


class B3IndisponivelError(Exception):
    """A B3 nao respondeu apos todas as tentativas."""


class _FalhaTemporariaError(Exception):
    """Marca uma falha que vale a pena tentar de novo. Nao escapa do modulo."""


@dataclass(frozen=True)
class Candidato:
    """Uma empresa que a busca da B3 devolveu para um ticker."""

    cd_cvm: int
    nome: str


def novo_cliente() -> httpx.Client:
    """Cliente com o `User-Agent` que o endpoint exige."""
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)


def _url(endpoint: str, payload: dict[str, Any]) -> str:
    codificado = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return f"{BASE_URL}/{endpoint}/{codificado}"


def _buscar(cliente: httpx.Client, endpoint: str, payload: dict[str, Any]) -> Any:
    """Uma chamada, sem retry -- quem repete e `_buscar_com_retry`."""
    url = _url(endpoint, payload)
    try:
        resposta = cliente.get(url)
    except httpx.TimeoutException as exc:
        raise _FalhaTemporariaError(f"timeout em {endpoint}") from exc
    except httpx.HTTPError as exc:
        raise B3IndisponivelError(f"falha de rede em {endpoint}: {exc}") from exc

    if resposta.status_code in _STATUS_TEMPORARIOS or resposta.status_code >= 500:
        raise _FalhaTemporariaError(f"{endpoint}: HTTP {resposta.status_code}")
    resposta.raise_for_status()

    try:
        return resposta.json()
    except ValueError:
        # Resposta vazia acontece de verdade: `GetDetail` sem `codeCVM` valido
        # devolve corpo vazio em vez de 404. Isso e "nao achei", nao falha.
        return None


def _buscar_com_retry(
    cliente: httpx.Client, endpoint: str, payload: dict[str, Any], *, tentativas: int, espera: float
) -> Any:
    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            return _buscar(cliente, endpoint, payload)
        except _FalhaTemporariaError as exc:
            ultimo_erro = exc
            logger.warning("[b3] tentativa %d/%d falhou: %s", tentativa, tentativas, exc)
            if tentativa < tentativas:
                time.sleep(espera)
    raise B3IndisponivelError(
        f"{endpoint}: a B3 nao respondeu apos {tentativas} tentativas"
    ) from ultimo_erro


def buscar_candidatos(
    cliente: httpx.Client,
    ticker: str,
    *,
    tentativas: int = TENTATIVAS_PADRAO,
    espera: float = ESPERA_PADRAO,
) -> list[Candidato]:
    """Empresas que a B3 devolve ao procurar por `ticker`, em ordem de relevancia.

    Leitura defensiva: candidato sem `codeCVM` numerico e descartado, sem
    derrubar os outros.
    """
    payload = {"language": "pt-br", "pageNumber": 1, "pageSize": 20, "company": ticker.upper()}
    dados = _buscar_com_retry(
        cliente, "GetInitialCompanies", payload, tentativas=tentativas, espera=espera
    )
    if not isinstance(dados, dict):
        return []
    resultados = dados.get("results")
    if not isinstance(resultados, list):
        return []

    candidatos: list[Candidato] = []
    for item in resultados[:MAX_CANDIDATOS]:
        if not isinstance(item, dict):
            continue
        codigo = item.get("codeCVM")
        if not isinstance(codigo, str) or not codigo.strip().isdigit():
            continue
        nome = item.get("companyName")
        candidatos.append(Candidato(cd_cvm=int(codigo), nome=nome if isinstance(nome, str) else ""))
    return candidatos


def codigos_da_empresa(
    cliente: httpx.Client,
    cd_cvm: int,
    *,
    tentativas: int = TENTATIVAS_PADRAO,
    espera: float = ESPERA_PADRAO,
) -> set[str]:
    """Todos os codigos de papel que a B3 lista para uma empresa.

    E a guarda que separa a Embraer da EMBRAST: so vale a ligacao se o ticker
    procurado estiver aqui dentro.
    """
    payload = {"codeCVM": str(cd_cvm), "language": "pt-br"}
    dados = _buscar_com_retry(cliente, "GetDetail", payload, tentativas=tentativas, espera=espera)
    if not isinstance(dados, dict):
        return set()

    codigos: set[str] = set()
    principal = dados.get("code")
    if isinstance(principal, str) and principal.strip():
        codigos.add(principal.strip().upper())
    outros = dados.get("otherCodes")
    if isinstance(outros, list):
        for item in outros:
            if isinstance(item, dict):
                codigo = item.get("code")
                if isinstance(codigo, str) and codigo.strip():
                    codigos.add(codigo.strip().upper())
    return codigos
