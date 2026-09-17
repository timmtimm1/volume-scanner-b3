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
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
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


@dataclass(frozen=True)
class Papel:
    """Um papel de uma empresa, com o ISIN que a B3 declara para ele."""

    ticker: str
    isin: str


@dataclass(frozen=True)
class Detalhe:
    """O cadastro da empresa na B3: como chama-la nos outros endpoints.

    `emissor` e `nome_pregao` sao as chaves que a B3 exige para consultar
    proventos -- nao sao deduzidos do ticker, vem daqui.
    """

    cd_cvm: int
    emissor: str | None
    nome_pregao: str | None
    papeis: tuple[Papel, ...]


@dataclass(frozen=True)
class Provento:
    """Um provento em dinheiro, como a B3 publica.

    `isin` so vem da consulta dos recentes; a do historico identifica a acao
    pela classe (`ON`, `PN`, `PNA`, `UNT`...). Por isso as duas existem: o ISIN
    diz exatamente de que papel e o provento, e o historico so alcanca datas
    que a consulta recente ja nao cobre.
    """

    classe: str | None
    isin: str | None
    tipo: str
    valor: Decimal
    data_com: date
    data_aprovacao: date | None
    data_pagamento: date | None
    # Fechamento do papel na data com, como a B3 publica. So vem no historico,
    # e e o que permite conferir contra o COTAHIST se o historico e mesmo da
    # empresa que pedimos (ver `proventos.py`).
    preco_data_com: Decimal | None = None


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


def _texto(valor: object) -> str | None:
    """Campo de texto da B3, ou None quando vem vazio ou com tipo errado."""
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def _data_br(valor: object) -> date | None:
    """Data no formato DD/MM/AAAA que a B3 usa. Campo torto vira None."""
    texto = _texto(valor)
    if texto is None:
        return None
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        return None


def _decimal_br(valor: object) -> Decimal | None:
    """Numero com virgula decimal, como "5,48220258487"."""
    texto = _texto(valor)
    if texto is None:
        return None
    try:
        return Decimal(texto.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def detalhe_da_empresa(
    cliente: httpx.Client,
    cd_cvm: int,
    *,
    tentativas: int = TENTATIVAS_PADRAO,
    espera: float = ESPERA_PADRAO,
) -> Detalhe | None:
    """Cadastro da empresa na B3, pelo codigo CVM. `None` se ela nao esta la."""
    payload = {"codeCVM": str(cd_cvm), "language": "pt-br"}
    dados = _buscar_com_retry(cliente, "GetDetail", payload, tentativas=tentativas, espera=espera)
    if not isinstance(dados, dict):
        return None

    papeis: list[Papel] = []
    outros = dados.get("otherCodes")
    if isinstance(outros, list):
        for item in outros:
            if not isinstance(item, dict):
                continue
            ticker = _texto(item.get("code"))
            isin = _texto(item.get("isin"))
            if ticker and isin:
                papeis.append(Papel(ticker.upper(), isin.upper()))
    return Detalhe(
        cd_cvm=cd_cvm,
        emissor=(_texto(dados.get("issuingCompany")) or "").upper() or None,
        nome_pregao=_texto(dados.get("tradingName")),
        papeis=tuple(papeis),
    )


def proventos_recentes(
    cliente: httpx.Client,
    emissor: str,
    *,
    tentativas: int = TENTATIVAS_PADRAO,
    espera: float = ESPERA_PADRAO,
) -> list[Provento]:
    """Proventos em dinheiro dos ultimos ~12 meses, com o ISIN de cada um.

    A consulta so aceita o codigo do emissor, entao quem chama precisa conferir
    que os ISINs que voltam sao mesmo da empresa esperada -- ver `carga.py`.
    """
    payload = {"language": "pt-br", "issuingCompany": emissor}
    dados = _buscar_com_retry(
        cliente, "GetListedSupplementCompany", payload, tentativas=tentativas, espera=espera
    )
    if isinstance(dados, list):
        dados = dados[0] if dados else None
    if not isinstance(dados, dict):
        return []

    linhas = dados.get("cashDividends")
    if not isinstance(linhas, list):
        return []

    proventos: list[Provento] = []
    for item in linhas:
        if not isinstance(item, dict):
            continue
        valor = _decimal_br(item.get("rate"))
        data_com = _data_br(item.get("lastDatePrior"))
        isin = _texto(item.get("isinCode")) or _texto(item.get("assetIssued"))
        tipo = _texto(item.get("label"))
        if valor is None or valor <= 0 or data_com is None or isin is None or tipo is None:
            continue
        proventos.append(
            Provento(
                classe=None,
                isin=isin.upper(),
                tipo=tipo.upper(),
                valor=valor,
                data_com=data_com,
                data_aprovacao=_data_br(item.get("approvedOn")),
                data_pagamento=_data_br(item.get("paymentDate")),
                preco_data_com=None,
            )
        )
    return proventos


def proventos_historicos(
    cliente: httpx.Client,
    nome_pregao: str,
    *,
    tentativas: int = TENTATIVAS_PADRAO,
    espera: float = ESPERA_PADRAO,
) -> list[Provento]:
    """Historico completo de proventos em dinheiro, pagina a pagina.

    A B3 ordena por classe e depois por data, entao nao da para parar na
    primeira pagina: os papeis PN de uma empresa com muito historico so
    aparecem paginas adiante. Linhas identicas nao sao descartadas -- um
    provento pago em parcelas aparece uma vez por parcela.
    """
    proventos: list[Provento] = []
    pagina = 1
    total_paginas = 1
    while pagina <= total_paginas:
        payload = {
            "language": "pt-br",
            "pageNumber": pagina,
            "pageSize": 120,
            "tradingName": nome_pregao,
        }
        dados = _buscar_com_retry(
            cliente, "GetListedCashDividends", payload, tentativas=tentativas, espera=espera
        )
        if not isinstance(dados, dict):
            break
        info = dados.get("page")
        if isinstance(info, dict):
            try:
                total_paginas = int(info["totalPages"])
            except (KeyError, TypeError, ValueError):
                total_paginas = pagina

        linhas = dados.get("results")
        if isinstance(linhas, list):
            for item in linhas:
                if not isinstance(item, dict):
                    continue
                valor = _decimal_br(item.get("valueCash"))
                data_com = _data_br(item.get("lastDatePriorEx"))
                classe = _texto(item.get("typeStock"))
                tipo = _texto(item.get("corporateAction"))
                if (
                    valor is None
                    or valor <= 0
                    or data_com is None
                    or classe is None
                    or tipo is None
                ):
                    continue
                proventos.append(
                    Provento(
                        classe=classe.upper(),
                        isin=None,
                        tipo=tipo.upper(),
                        valor=valor,
                        data_com=data_com,
                        data_aprovacao=_data_br(item.get("dateApproval")),
                        data_pagamento=None,
                        preco_data_com=_decimal_br(item.get("closingPricePriorExDate")),
                    )
                )
        pagina += 1
    return proventos
