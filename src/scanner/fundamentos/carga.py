"""Orquestracao com banco: liga empresas e carrega os zips anuais da CVM.

`cvm.py` e `b3.py` so leem e transformam; aqui e onde o resultado vira linha
no banco, e onde as decisoes de "precisa baixar de novo?" moram.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine

from scanner.config import FundamentosConfig
from scanner.fundamentos.b3 import (
    B3IndisponivelError,
    buscar_candidatos,
    codigos_da_empresa,
    novo_cliente,
)
from scanner.fundamentos.cvm import (
    CvmIndisponivelError,
    baixar,
    extrair_documentos,
    ler_cadastro,
    ler_valores_mobiliarios,
)
from scanner.storage import repository

logger = logging.getLogger(__name__)

DEFAULT_CACHE = Path("data/cvm")
CADASTRO_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"

# Pausa entre requisicoes a B3, que e um endpoint nao documentado do site
# deles. So entra em cena para ticker que o FCA nao cobre.
PAUSA_B3 = 0.15


def _url_fca(ano: int) -> str:
    return f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip"


def _url_zip(tipo: str, ano: int) -> str:
    pasta = tipo.upper()
    return (
        f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/{pasta}/DADOS/"
        f"{tipo.lower()}_cia_aberta_{ano}.zip"
    )


def _caminho_zip(cache: Path, tipo: str, ano: int) -> Path:
    return cache / f"{tipo.lower()}_cia_aberta_{ano}.zip"


def _data_bonita(momento: datetime | None) -> str:
    return momento.strftime("%d/%m/%Y") if momento is not None else "data desconhecida"


@dataclass
class RelatorioFundamentos:
    """O que aconteceu numa passada de `atualizar_fundamentos`."""

    empresas_ligadas: int = 0
    tickers_ligados: int = 0
    tickers_sem_empresa: int = 0
    mapeamento: str = ""
    avisos: list[str] = field(default_factory=list)
    arquivos: list[str] = field(default_factory=list)
    falhas: list[str] = field(default_factory=list)

    @property
    def teve_falha(self) -> bool:
        return bool(self.falhas)

    def linhas(self) -> list[str]:
        saida = [
            f"ligacao: {self.tickers_ligados} tickers em {self.empresas_ligadas} empresas, "
            f"{self.tickers_sem_empresa} sem empresa ({self.mapeamento})"
        ]
        saida.extend(self.avisos)
        saida.extend(self.arquivos)
        saida.extend(f"falhou {f}" for f in self.falhas)
        return saida


def _baixar_para_ler(
    engine: Engine, url: str, destino: Path, momento: datetime, *, forcar: bool
) -> Path | None:
    """Baixa um arquivo cujo CONTEUDO vai ser lido agora. `None` se nao deu.

    Diferente dos zips anuais, aqui um 304 sem arquivo em disco nao serve --
    dai o `exigir_conteudo`.
    """
    anterior = repository.buscar_arquivo_externo(engine, url)
    download = baixar(
        url,
        destino,
        etag=anterior["etag"] if anterior else None,
        last_modified=anterior["last_modified"] if anterior else None,
        forcar=forcar,
        exigir_conteudo=True,
    )
    if download.alterado:
        repository.registrar_arquivo_externo(
            engine,
            url,
            etag=download.etag,
            last_modified=download.last_modified,
            modificado_em=download.modificado_em,
            escopo_hash="",
            verificado_em=momento,
        )
    else:
        repository.marcar_arquivo_verificado(engine, url, momento)
    caminho = download.caminho or destino
    return caminho if caminho.is_file() else None


def _mapa_do_fca(
    engine: Engine,
    config: FundamentosConfig,
    momento: datetime,
    *,
    forcar: bool,
    cache: Path,
) -> pd.DataFrame:
    """Ticker -> CNPJ pelo FCA, um arquivo por ano, o registro mais novo vencendo.

    O mesmo codigo pode aparecer em varios anos (a empresa entrega o FCA todo
    ano); vale o de `dt_refer` mais nova, desempate pela `versao` maior. Uma
    empresa que parou de entregar continua valendo pelo ano em que entregou --
    e por isso a uniao dos anos, e nao so o arquivo do ano corrente (a Embraer
    so aparece no de 2024).
    """
    partes: list[pd.DataFrame] = []
    for ano in range(config.ano_inicial, momento.year + 1):
        url = _url_fca(ano)
        destino = cache / f"fca_cia_aberta_{ano}.zip"
        try:
            caminho = _baixar_para_ler(engine, url, destino, momento, forcar=forcar)
        except CvmIndisponivelError as exc:
            logger.warning("[fundamentos] FCA %d indisponivel: %s", ano, exc)
            continue
        if caminho is None:
            continue
        partes.append(ler_valores_mobiliarios(caminho))

    if not partes:
        return pd.DataFrame(columns=["ticker", "cnpj", "dt_refer", "versao"])

    todos = pd.concat(partes, ignore_index=True).sort_values(["dt_refer", "versao"])
    return todos.groupby("ticker", as_index=False).tail(1).reset_index(drop=True)


def _resolver_na_b3(
    tickers: list[str], cd_cvms_validos: set[int], *, pausa: float
) -> tuple[dict[str, int], list[str], str | None]:
    """Procura na B3 os tickers que o FCA nao declarou, conferindo cada candidato.

    So aceita quando o `codeCVM` existe no cadastro da CVM E o ticker esta
    entre os codigos que a B3 lista para aquela empresa. As duas guardas
    juntas sao o que impede ligar EMBR3 a EMBRAST (ver `b3.py`).

    Devolve o que resolveu, QUAIS tickers foram de fato procurados ate o fim
    e, se a B3 cair no meio, o aviso. So quem foi procurado ate o fim pode
    virar cache negativo: o que ficou para tras tem de ser tentado de novo na
    proxima passada, senao uma queda de minutos esconderia a empresa por uma
    semana.
    """
    achados: dict[str, int] = {}
    procurados: list[str] = []
    if not tickers:
        return achados, procurados, None

    cliente = novo_cliente()
    try:
        for ticker in tickers:
            try:
                candidatos = buscar_candidatos(cliente, ticker)
                for candidato in candidatos:
                    if candidato.cd_cvm not in cd_cvms_validos:
                        continue
                    if ticker in codigos_da_empresa(cliente, candidato.cd_cvm):
                        achados[ticker] = candidato.cd_cvm
                        break
                    time.sleep(pausa)
            except B3IndisponivelError as exc:
                return achados, procurados, f"B3 fora do ar ao procurar {ticker}: {exc}"
            procurados.append(ticker)
            time.sleep(pausa)
    finally:
        cliente.close()
    return achados, procurados, None


def _indice_por_cnpj(cadastro: pd.DataFrame) -> pd.Series:
    """CNPJ -> CD_CVM, resolvendo os CNPJs com mais de um registro na CVM.

    Acontece em 34 empresas no cadastro real: a mesma companhia aparece duas
    vezes, uma CANCELADA e outra ATIVO (a LWSA, por exemplo, com os codigos
    21407 e 24910). Vale o registro ativo -- e nele que os documentos de hoje
    sao entregues; havendo empate, o codigo mais novo.
    """
    ordenado = cadastro.assign(_ativo=(cadastro["situacao"] == "ATIVO")).sort_values(
        ["_ativo", "cd_cvm"], ascending=[True, True]
    )
    unico = ordenado.groupby("cnpj", as_index=False).tail(1)
    indice: pd.Series = unico.set_index("cnpj")["cd_cvm"]
    return indice


def _mapear_tickers(
    engine: Engine,
    config: FundamentosConfig,
    momento: datetime,
    *,
    forcar: bool,
    cache: Path,
    pausa_b3: float,
    relatorio: RelatorioFundamentos,
) -> None:
    """Liga cada ticker do banco a uma empresa da CVM (FCA primeiro, B3 depois)."""
    tickers = repository.tickers_do_banco(engine)
    if not tickers:
        relatorio.mapeamento = "nenhum ticker em daily_bars"
        return

    corte = momento - timedelta(days=config.dias_para_rechecar_ticker)
    pendentes = repository.tickers_pendentes(engine, tickers, corte)
    if not pendentes and not forcar:
        relatorio.mapeamento = "sem ticker novo para ligar"
        _contar_mapeamento(engine, relatorio)
        return

    try:
        caminho_cadastro = _baixar_para_ler(
            engine, CADASTRO_URL, cache / "cad_cia_aberta.csv", momento, forcar=forcar
        )
    except CvmIndisponivelError as exc:
        caminho_cadastro = None
        relatorio.avisos.append(f"cadastro da CVM indisponivel ({exc}); ligacao nao atualizada")
    if caminho_cadastro is None:
        relatorio.mapeamento = "cadastro da CVM ausente"
        _contar_mapeamento(engine, relatorio)
        return

    cadastro = ler_cadastro(caminho_cadastro)
    fca = _mapa_do_fca(engine, config, momento, forcar=forcar, cache=cache)

    alvo = sorted(tickers) if forcar else sorted(pendentes)
    por_cnpj = _indice_por_cnpj(cadastro)
    do_fca = fca[fca["ticker"].isin(alvo)].copy()
    do_fca["cd_cvm"] = do_fca["cnpj"].map(por_cnpj)
    do_fca = do_fca.dropna(subset=["cd_cvm"])
    ligacoes = {str(t): int(c) for t, c in zip(do_fca["ticker"], do_fca["cd_cvm"], strict=True)}
    pelo_fca = len(ligacoes)

    faltam = [t for t in alvo if t not in ligacoes]
    pela_b3, procurados, aviso = _resolver_na_b3(faltam, set(cadastro["cd_cvm"]), pausa=pausa_b3)
    if aviso:
        relatorio.avisos.append(aviso)
    ligacoes.update(pela_b3)

    # Cache negativo so para quem a B3 procurou ate o fim e nao achou.
    sem_empresa = sorted(t for t in procurados if t not in ligacoes)

    usados = sorted(set(ligacoes.values()))
    repository.upsert_empresas(engine, cadastro[cadastro["cd_cvm"].isin(usados)])
    repository.upsert_empresa_tickers(engine, ligacoes, pela_b3.keys(), sem_empresa, momento)

    relatorio.mapeamento = (
        f"{pelo_fca} ligados pelo FCA, {len(pela_b3)} pela busca na B3"
        if pela_b3
        else f"{pelo_fca} ligados pelo FCA"
    )
    _contar_mapeamento(engine, relatorio)


def _contar_mapeamento(engine: Engine, relatorio: RelatorioFundamentos) -> None:
    relatorio.tickers_ligados, relatorio.tickers_sem_empresa = repository.contagem_do_mapeamento(
        engine
    )
    relatorio.empresas_ligadas = repository.contar_empresas(engine)


def _atualizar_arquivo(
    engine: Engine,
    tipo: str,
    ano: int,
    cd_cvms: set[int],
    escopo_hash: str,
    momento: datetime,
    *,
    forcar: bool,
    cache: Path,
    relatorio: RelatorioFundamentos,
) -> None:
    url = _url_zip(tipo, ano)
    anterior = repository.buscar_arquivo_externo(engine, url)

    condicional = (
        anterior is not None
        and anterior["processado_em"] is not None
        and anterior["escopo_hash"] == escopo_hash
        and not forcar
    )
    etag = anterior["etag"] if condicional and anterior else None
    last_modified = anterior["last_modified"] if condicional and anterior else None

    try:
        download = baixar(
            url,
            _caminho_zip(cache, tipo, ano),
            etag=etag,
            last_modified=last_modified,
            forcar=forcar,
        )
    except CvmIndisponivelError as exc:
        relatorio.falhas.append(f"{tipo} {ano}: download falhou: {exc}")
        return

    if not download.alterado:
        if etag is not None or last_modified is not None:
            repository.marcar_arquivo_verificado(engine, url, momento)
            data_txt = _data_bonita(anterior["modificado_em"] if anterior else None)
            relatorio.arquivos.append(f"{tipo} {ano}: sem mudanca (dados da CVM de {data_txt})")
        else:
            relatorio.arquivos.append(f"{tipo} {ano}: ainda nao publicado pela CVM")
        return

    if download.caminho is None:  # pragma: no cover - alterado=True sempre tem caminho
        relatorio.falhas.append(f"{tipo} {ano}: download sem arquivo")
        return

    try:
        extracao = extrair_documentos(download.caminho, tipo, cd_cvms)
        gravado = repository.gravar_arquivo_cvm(
            engine,
            extracao,
            url=url,
            etag=download.etag,
            last_modified=download.last_modified,
            modificado_em=download.modificado_em,
            escopo_hash=escopo_hash,
            verificado_em=momento,
        )
    except Exception as exc:
        relatorio.falhas.append(f"{tipo} {ano}: {exc}")
        return

    # `com_nova_versao` conta os novos tambem; o que interessa ler no log e
    # quantos ja existiam e vieram reapresentados.
    reapresentados = gravado.com_nova_versao - gravado.novos
    data_txt = _data_bonita(download.modificado_em)
    relatorio.arquivos.append(
        f"{tipo} {ano}: atualizado (dados da CVM de {data_txt}): "
        f"{gravado.documentos} documentos, {gravado.novos} novos, "
        f"{reapresentados} reapresentados"
    )


def atualizar_fundamentos(
    engine: Engine,
    config: FundamentosConfig,
    *,
    agora: datetime | None = None,
    forcar: bool = False,
    cache: Path = DEFAULT_CACHE,
    pausa_b3: float = PAUSA_B3,
) -> RelatorioFundamentos:
    """Liga cada ticker a sua empresa e carrega os zips anuais da CVM.

    Falha num arquivo nao impede os outros: cada (tipo, ano) roda isolado e as
    falhas ficam no relatorio -- quem decide se isso e motivo de sair com erro
    e o chamador (o CLI sai 1 se `relatorio.teve_falha`).
    """
    momento = agora if agora is not None else datetime.now(UTC)
    relatorio = RelatorioFundamentos()

    _mapear_tickers(
        engine,
        config,
        momento,
        forcar=forcar,
        cache=cache,
        pausa_b3=pausa_b3,
        relatorio=relatorio,
    )

    cd_cvms = repository.cd_cvms_mapeados(engine)
    if not cd_cvms:
        relatorio.avisos.append("arquivos: nenhuma empresa ligada, nada para baixar da CVM")
        return relatorio

    escopo_hash = hashlib.sha256(
        ",".join(str(c) for c in sorted(cd_cvms)).encode("utf-8")
    ).hexdigest()

    ano_corrente = momento.year
    for ano in range(config.ano_inicial, ano_corrente + 1):
        for tipo in ("ITR", "DFP"):
            _atualizar_arquivo(
                engine,
                tipo,
                ano,
                cd_cvms,
                escopo_hash,
                momento,
                forcar=forcar,
                cache=cache,
                relatorio=relatorio,
            )

    return relatorio
