"""Download condicional e extracao dos dados abertos da CVM (sem banco).

Os arquivos sao os zips anuais de ITR e DFP (`dados.cvm.gov.br`) e o cadastro
de companhias abertas. Este modulo so le e transforma; quem grava no banco e
`carga.py`.

O codigo da conta muda conforme o layout do documento (industria/comercio vs.
banco/seguradora): a extracao por isso sempre confere a DESCRICAO da conta,
normalizada (sem acento, minusculo, espacos colapsados), nunca so o codigo.
"""

from __future__ import annotations

import io
import re
import time
import unicodedata
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
import pandas as pd

CHUNK_BYTES = 1 << 20
TIMEOUT_SECONDS = 300.0
LEITURA_CHUNKSIZE = 200_000

TENTATIVAS_PADRAO = 3
ESPERA_PADRAO = 5.0
_STATUS_TEMPORARIOS = frozenset({429})

# Colunas do indice ({doc}_cia_aberta_{ANO}.csv).
_COLS_INDICE = ["CNPJ_CIA", "DT_REFER", "VERSAO", "CD_CVM", "ID_DOC", "DT_RECEB"]

# A linha final do resultado, em todas as redacoes vistas no dado real.
_PADRAO_LUCRO = re.compile(r"^lucro\s*(?:ou\s+|/|\(|-\s*)?\s*prejuizo")

# Colunas do FCA (formulario cadastral) que declaram o codigo de negociacao.
_COLS_FCA = ["CNPJ_Companhia", "Data_Referencia", "Versao", "Codigo_Negociacao"]

# Colunas dos arquivos de contas. BPA/BPP nao tem DT_INI_EXERC.
_COLS_CONTAS_COM_INICIO = [
    "CNPJ_CIA",
    "DT_REFER",
    "CD_CVM",
    "ORDEM_EXERC",
    "ESCALA_MOEDA",
    "DT_INI_EXERC",
    "DT_FIM_EXERC",
    "CD_CONTA",
    "DS_CONTA",
    "VL_CONTA",
]
_COLS_CONTAS_SEM_INICIO = [
    "CNPJ_CIA",
    "DT_REFER",
    "CD_CVM",
    "ORDEM_EXERC",
    "ESCALA_MOEDA",
    "DT_FIM_EXERC",
    "CD_CONTA",
    "DS_CONTA",
    "VL_CONTA",
]

_COLS_CAPITAL = [
    "CNPJ_CIA",
    "DT_REFER",
    "VERSAO",
    "QT_ACAO_ORDIN_CAP_INTEGR",
    "QT_ACAO_PREF_CAP_INTEGR",
    "QT_ACAO_ORDIN_TESOURO",
    "QT_ACAO_PREF_TESOURO",
]

_ARQUIVOS_CONTAS = (
    # (origem, tem_periodo)
    ("DRE", True),
    ("DVA", True),
    ("BPA", False),
    ("BPP", False),
)

COLUNAS_DOCUMENTOS = [
    "cd_cvm",
    "tipo",
    "dt_refer",
    "versao",
    "recebido_original",
    "recebido_ultima",
    "escopo",
    "layout",
    "id_doc",
]
COLUNAS_RESULTADOS = [
    "cd_cvm",
    "tipo",
    "dt_refer",
    "dt_ini",
    "dt_fim",
    "receita",
    "resultado_bruto",
    "ebit",
    "lucro_liquido",
    "lucro_controladores",
    "depreciacao_amortizacao",
]
COLUNAS_BALANCOS = [
    "cd_cvm",
    "tipo",
    "dt_refer",
    "ativo_total",
    "ativo_circulante",
    "caixa",
    "aplicacoes_financeiras",
    "passivo_circulante",
    "emprestimos_cp",
    "arrendamento_cp",
    "emprestimos_lp",
    "arrendamento_lp",
    "patrimonio_liquido",
    "pl_nao_controladores",
    "acoes_on",
    "acoes_pn",
    "tesouraria_on",
    "tesouraria_pn",
]


class CvmIndisponivelError(Exception):
    """A CVM nao respondeu apos todas as tentativas."""


class _FalhaTemporariaError(Exception):
    """Falha que vale tentar de novo. Nao escapa deste modulo."""


@dataclass(frozen=True)
class Download:
    """Resultado de uma tentativa de baixar um arquivo da CVM."""

    alterado: bool
    caminho: Path | None
    etag: str | None
    last_modified: str | None
    modificado_em: datetime | None


def _parse_http_date(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        return None


def baixar(
    url: str,
    destino: Path,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    forcar: bool = False,
    exigir_conteudo: bool = False,
    tentativas: int = TENTATIVAS_PADRAO,
    espera: float = ESPERA_PADRAO,
) -> Download:
    """Baixa `url` para `destino` se mudou desde a ultima vez.

    Envia `If-None-Match`/`If-Modified-Since` quando ha valores e `forcar` e
    falso; 304 vira `alterado=False`. 404 (DFP do ano corrente pode nao
    existir ainda) tambem vira `alterado=False`, mas sem erro -- e "o arquivo
    nao existe", nao uma falha. Streaming para `.part`, promovido so no fim,
    como `ingest/download.py`.

    `exigir_conteudo` e para quem precisa LER o arquivo nesta passada, e nao
    so saber se mudou. Nesse caso a checagem condicional so vale quando o
    arquivo esta mesmo em disco: no runner do GitHub o cache comeca vazio a
    cada execucao, e um 304 sem arquivo nenhum deixaria o chamador sem o que
    ler. Os zips anuais nao precisam disso -- 304 neles significa "o que ja
    esta no banco continua valendo".
    """
    cabecalhos: dict[str, str] = {}
    tem_arquivo = destino.is_file() and destino.stat().st_size > 0
    if not forcar and (tem_arquivo or not exigir_conteudo):
        if etag:
            cabecalhos["If-None-Match"] = etag
        if last_modified:
            cabecalhos["If-Modified-Since"] = last_modified

    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(destino.suffix + ".part")

    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            return _tentar_baixar(url, destino, parcial, cabecalhos)
        except _FalhaTemporariaError as exc:
            ultimo_erro = exc
            if tentativa < tentativas:
                time.sleep(espera)
                continue
            raise CvmIndisponivelError(
                f"{url}: a CVM nao respondeu apos {tentativas} tentativas"
            ) from ultimo_erro

    raise AssertionError("inalcancavel: o loop acima sempre retorna ou levanta")


def _tentar_baixar(url: str, destino: Path, parcial: Path, cabecalhos: dict[str, str]) -> Download:
    try:
        with httpx.stream(
            "GET", url, headers=cabecalhos, timeout=TIMEOUT_SECONDS, follow_redirects=True
        ) as resposta:
            if resposta.status_code == httpx.codes.NOT_MODIFIED:
                return Download(
                    alterado=False,
                    caminho=None,
                    etag=cabecalhos.get("If-None-Match"),
                    last_modified=cabecalhos.get("If-Modified-Since"),
                    modificado_em=_parse_http_date(cabecalhos.get("If-Modified-Since")),
                )
            if resposta.status_code == httpx.codes.NOT_FOUND:
                return Download(
                    alterado=False, caminho=None, etag=None, last_modified=None, modificado_em=None
                )
            if resposta.status_code in _STATUS_TEMPORARIOS or resposta.status_code >= 500:
                raise _FalhaTemporariaError(f"{url}: HTTP {resposta.status_code}")
            resposta.raise_for_status()

            novo_etag = resposta.headers.get("ETag")
            novo_last_modified = resposta.headers.get("Last-Modified")
            with parcial.open("wb") as arquivo:
                for pedaco in resposta.iter_bytes(CHUNK_BYTES):
                    arquivo.write(pedaco)
    except httpx.TimeoutException as exc:
        parcial.unlink(missing_ok=True)
        raise _FalhaTemporariaError(f"{url}: timeout") from exc
    except httpx.HTTPError as exc:
        parcial.unlink(missing_ok=True)
        raise CvmIndisponivelError(f"{url}: falha ao baixar: {exc}") from exc

    parcial.replace(destino)
    return Download(
        alterado=True,
        caminho=destino,
        etag=novo_etag,
        last_modified=novo_last_modified,
        modificado_em=_parse_http_date(novo_last_modified),
    )


def ler_cadastro(caminho: Path) -> pd.DataFrame:
    """Le `cad_cia_aberta.csv`: quem e cada empresa, pelo cadastro oficial.

    Devolve `cd_cvm`, `cnpj` (14 digitos), `nome`, `nome_comercial`,
    `setor_cvm` e `situacao`.

    NAO filtra por `SIT`: papel de empresa fora de ATIVO (em recuperacao, ou
    saindo da bolsa) continua negociando e aparecendo no scanner, entao
    precisa de empresa ligada como qualquer outro. A situacao vai numa coluna.

    O cadastro tem linhas duplicadas para algumas empresas (visto no dado
    real): `drop_duplicates` por `cd_cvm` fica so com a primeira.
    """
    bruto = pd.read_csv(
        caminho,
        sep=";",
        encoding="latin-1",
        dtype=str,
        usecols=["CNPJ_CIA", "CD_CVM", "DENOM_SOCIAL", "DENOM_COMERC", "SETOR_ATIV", "SIT"],
    )
    cd_cvm = pd.to_numeric(bruto["CD_CVM"], errors="coerce")
    valido = cd_cvm.notna()
    resultado = pd.DataFrame(
        {
            "cd_cvm": cd_cvm[valido].astype("int64"),
            "cnpj": bruto.loc[valido, "CNPJ_CIA"].str.replace(r"\D", "", regex=True),
            "nome": bruto.loc[valido, "DENOM_SOCIAL"],
            "nome_comercial": bruto.loc[valido, "DENOM_COMERC"],
            "setor_cvm": bruto.loc[valido, "SETOR_ATIV"],
            "situacao": bruto.loc[valido, "SIT"],
        }
    )
    return resultado.drop_duplicates(subset=["cd_cvm"], keep="first").reset_index(drop=True)


def ler_valores_mobiliarios(zip_path: Path) -> pd.DataFrame:
    """Le o FCA anual: que codigo de negociacao pertence a que CNPJ.

    E a fonte oficial da ligacao ticker -> empresa. O FCA e o formulario
    cadastral que cada companhia entrega por ano, e nele a propria empresa
    declara os codigos com que seus papeis sao negociados -- diferente de
    deduzir a empresa pelo prefixo do ticker, que erra (ver `b3.py`).

    Devolve `ticker`, `cnpj` (14 digitos), `dt_refer` e `versao`. Uma empresa
    pode aparecer em varios anos; quem escolhe qual vale e `carga.py`, pela
    data de referencia mais nova.
    """
    colunas_saida = ["ticker", "cnpj", "dt_refer", "versao"]
    with zipfile.ZipFile(zip_path) as zf:
        ano = _localizar_ano_fca(zf.namelist())
        bruto = _ler_csv_completo(zf, _nome_valores_mobiliarios(ano), _COLS_FCA)
    if bruto is None:  # pragma: no cover - o zip do FCA sempre traz este arquivo
        return pd.DataFrame(columns=colunas_saida)

    preparado = pd.DataFrame(
        {
            "ticker": bruto["Codigo_Negociacao"].fillna("").str.strip().str.upper(),
            "cnpj": bruto["CNPJ_Companhia"].str.replace(r"\D", "", regex=True),
            "dt_refer": pd.to_datetime(bruto["Data_Referencia"], errors="coerce").dt.date,
            "versao": pd.to_numeric(bruto["Versao"], errors="coerce"),
        }
    )
    # Linha sem codigo de negociacao e valor mobiliario que nao e acao (nota
    # promissoria, debenture): nao liga ticker nenhum.
    com_codigo = preparado[preparado["ticker"] != ""]
    return com_codigo.dropna(subset=["dt_refer"])[colunas_saida].reset_index(drop=True)


@dataclass(frozen=True)
class Extracao:
    """As tres tabelas extraidas de um zip anual da CVM, prontas para o banco."""

    documentos: pd.DataFrame
    resultados: pd.DataFrame
    balancos: pd.DataFrame


def _normalizar_serie(valores: pd.Series) -> pd.Series:
    """Sem acento, minusculo, espacos colapsados -- para comparar descricao de conta."""

    def normalizar_um(valor: object) -> str:
        if not isinstance(valor, str):
            return ""
        sem_acento = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", " ", sem_acento).strip().lower()

    return valores.map(normalizar_um)


def _nome_indice(tipo: str, ano: int) -> str:
    return f"{tipo.lower()}_cia_aberta_{ano}.csv"


def _nome_contas(tipo: str, origem: str, escopo: str, ano: int) -> str:
    return f"{tipo.lower()}_cia_aberta_{origem}_{escopo}_{ano}.csv"


def _nome_capital(tipo: str, ano: int) -> str:
    return f"{tipo.lower()}_cia_aberta_composicao_capital_{ano}.csv"


def _nome_valores_mobiliarios(ano: int) -> str:
    return f"fca_cia_aberta_valor_mobiliario_{ano}.csv"


def _localizar_ano_fca(nomes: Iterable[str]) -> int:
    padrao = re.compile(r"^fca_cia_aberta_valor_mobiliario_(\d{4})\.csv$")
    for nome in nomes:
        casamento = padrao.match(nome)
        if casamento:
            return int(casamento.group(1))
    raise ValueError("arquivo de valores mobiliarios nao encontrado no zip do FCA")


def _localizar_ano(nomes: Iterable[str], tipo: str) -> int:
    padrao = re.compile(rf"^{re.escape(tipo.lower())}_cia_aberta_(\d{{4}})\.csv$")
    for nome in nomes:
        casamento = padrao.match(nome)
        if casamento:
            return int(casamento.group(1))
    raise ValueError(f"indice do {tipo} nao encontrado no zip")


def _ler_csv_completo(zf: zipfile.ZipFile, nome: str, usecols: list[str]) -> pd.DataFrame | None:
    """`pandas.read_csv` sobre um membro do zip, inteiro. `None` se nao existir."""
    if nome not in zf.namelist():
        return None
    with zf.open(nome) as bruto:
        texto = io.TextIOWrapper(bruto, encoding="latin-1", newline="")
        return pd.read_csv(texto, sep=";", dtype=str, usecols=usecols, engine="c")


def _ler_csv_em_pedacos(
    zf: zipfile.ZipFile, nome: str, usecols: list[str], chunksize: int
) -> Iterable[pd.DataFrame]:
    """Os pedacos de `pandas.read_csv` sobre um membro do zip. Vazio se nao existir.

    Le direto do stream do zip (sem carregar o membro inteiro na memoria): os
    arquivos de contas reais chegam a centenas de MB descompactados.
    Ausencia de arquivo so acontece em zip de teste recortado; os zips reais
    da CVM sempre trazem os oito arquivos de contas.
    """
    if nome not in zf.namelist():
        return []
    bruto = zf.open(nome)
    texto = io.TextIOWrapper(bruto, encoding="latin-1", newline="")
    return pd.read_csv(texto, sep=";", dtype=str, usecols=usecols, chunksize=chunksize, engine="c")


def _ler_indice(zf: zipfile.ZipFile, tipo: str, ano: int) -> pd.DataFrame:
    bruto = _ler_csv_completo(zf, _nome_indice(tipo, ano), _COLS_INDICE)
    if bruto is None:
        raise ValueError(f"indice do {tipo} {ano} nao encontrado no zip")
    cd_cvm = pd.to_numeric(bruto["CD_CVM"], errors="coerce")
    valido = cd_cvm.notna()
    return pd.DataFrame(
        {
            "cnpj_cia": bruto.loc[valido, "CNPJ_CIA"],
            "cd_cvm": cd_cvm[valido].astype("int64"),
            "dt_refer": pd.to_datetime(bruto.loc[valido, "DT_REFER"]).dt.date,
            "versao": pd.to_numeric(bruto.loc[valido, "VERSAO"], errors="coerce").astype("Int64"),
            "id_doc": pd.to_numeric(bruto.loc[valido, "ID_DOC"], errors="coerce").astype("Int64"),
            "dt_recebido": pd.to_datetime(bruto.loc[valido, "DT_RECEB"]).dt.date,
        }
    )


def _ler_contas(
    zf: zipfile.ZipFile,
    tipo: str,
    origem: str,
    escopo: str,
    ano: int,
    cd_cvms: set[int],
    *,
    tem_periodo: bool,
) -> pd.DataFrame:
    """Le um arquivo de contas do zip, ja filtrado por empresa e ORDEM_EXERC.

    Filtra cada chunk antes de acumular, como a spec pede: com centenas de
    milhares de linhas por arquivo, acumular tudo para filtrar depois gastaria
    memoria a toa.
    """
    colunas = _COLS_CONTAS_COM_INICIO if tem_periodo else _COLS_CONTAS_SEM_INICIO
    leitor = _ler_csv_em_pedacos(
        zf, _nome_contas(tipo, origem, escopo, ano), colunas, LEITURA_CHUNKSIZE
    )

    partes: list[pd.DataFrame] = []
    for pedaco in leitor:
        cd_cvm_num = pd.to_numeric(pedaco["CD_CVM"], errors="coerce")
        filtrado = pedaco[cd_cvm_num.isin(cd_cvms) & (pedaco["ORDEM_EXERC"] == "ÚLTIMO")]
        if filtrado.empty:
            continue
        preparado = pd.DataFrame(
            {
                "cd_cvm": pd.to_numeric(filtrado["CD_CVM"], errors="coerce").astype("int64"),
                "dt_refer": pd.to_datetime(filtrado["DT_REFER"]).dt.date,
                "cd_conta": filtrado["CD_CONTA"],
                "ds_conta": _normalizar_serie(filtrado["DS_CONTA"]),
                "valor": pd.to_numeric(filtrado["VL_CONTA"], errors="coerce")
                * filtrado["ESCALA_MOEDA"].map({"MIL": 1000.0}).fillna(1.0),
            }
        )
        if tem_periodo:
            preparado["dt_ini"] = pd.to_datetime(filtrado["DT_INI_EXERC"]).dt.date
            preparado["dt_fim"] = pd.to_datetime(filtrado["DT_FIM_EXERC"]).dt.date
        else:
            preparado["dt_ini"] = pd.NaT
            preparado["dt_fim"] = pd.to_datetime(filtrado["DT_FIM_EXERC"]).dt.date
        preparado["origem"] = origem
        preparado["escopo_arquivo"] = escopo
        partes.append(preparado)

    if not partes:
        return _contas_vazias(tem_periodo)
    return pd.concat(partes, ignore_index=True)


def _contas_vazias(tem_periodo: bool) -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "cd_cvm",
            "dt_refer",
            "cd_conta",
            "ds_conta",
            "valor",
            "dt_ini",
            "dt_fim",
            "origem",
            "escopo_arquivo",
        ]
    )


def _ler_capital(zf: zipfile.ZipFile, tipo: str, ano: int) -> pd.DataFrame:
    colunas_saida = [
        "cnpj_cia",
        "dt_refer",
        "acoes_on",
        "acoes_pn",
        "tesouraria_on",
        "tesouraria_pn",
    ]
    bruto = _ler_csv_completo(zf, _nome_capital(tipo, ano), _COLS_CAPITAL)
    if bruto is None:
        return pd.DataFrame(columns=colunas_saida)

    preparado = pd.DataFrame(
        {
            "cnpj_cia": bruto["CNPJ_CIA"],
            "dt_refer": pd.to_datetime(bruto["DT_REFER"]).dt.date,
            "versao": pd.to_numeric(bruto["VERSAO"], errors="coerce"),
            "acoes_on": pd.to_numeric(bruto["QT_ACAO_ORDIN_CAP_INTEGR"], errors="coerce"),
            "acoes_pn": pd.to_numeric(bruto["QT_ACAO_PREF_CAP_INTEGR"], errors="coerce"),
            "tesouraria_on": pd.to_numeric(bruto["QT_ACAO_ORDIN_TESOURO"], errors="coerce"),
            "tesouraria_pn": pd.to_numeric(bruto["QT_ACAO_PREF_TESOURO"], errors="coerce"),
        }
    )
    # So a maior VERSAO por (empresa, data): groupby+tail depois de ordenar,
    # sem loop Python.
    ordenado = preparado.sort_values("versao")
    ultima = ordenado.groupby(["cnpj_cia", "dt_refer"], as_index=False).tail(1)
    return ultima[colunas_saida].reset_index(drop=True)


def extrair_documentos(zip_path: Path, tipo: str, cd_cvms: set[int]) -> Extracao:
    """Le um zip anual (ITR ou DFP) da CVM e devolve as tres tabelas do banco.

    So processa empresas em `cd_cvms`. Documentos cujo indice existe mas ainda
    nao tem linha de conta no zip (a CVM ainda nao processou) sao ignorados --
    nao ha o que extrair deles.
    """
    if tipo not in ("ITR", "DFP"):
        raise ValueError(f"tipo invalido: {tipo!r}")
    if not cd_cvms:
        return Extracao(
            pd.DataFrame(columns=COLUNAS_DOCUMENTOS),
            pd.DataFrame(columns=COLUNAS_RESULTADOS),
            pd.DataFrame(columns=COLUNAS_BALANCOS),
        )

    with zipfile.ZipFile(zip_path) as zf:
        ano = _localizar_ano(zf.namelist(), tipo)
        indice = _ler_indice(zf, tipo, ano)
        indice = indice[indice["cd_cvm"].isin(cd_cvms)]

        contas = pd.concat(
            [
                _ler_contas(zf, tipo, origem, escopo, ano, cd_cvms, tem_periodo=tem_periodo)
                for origem, tem_periodo in _ARQUIVOS_CONTAS
                for escopo in ("con", "ind")
            ],
            ignore_index=True,
        )
        capital = _ler_capital(zf, tipo, ano)

    if contas.empty or indice.empty:
        return Extracao(
            pd.DataFrame(columns=COLUNAS_DOCUMENTOS),
            pd.DataFrame(columns=COLUNAS_RESULTADOS),
            pd.DataFrame(columns=COLUNAS_BALANCOS),
        )

    # --- Escopo do documento: 'con' se tem QUALQUER linha em arquivo _con_. ---
    com_con = (
        contas.loc[contas["escopo_arquivo"] == "con", ["cd_cvm", "dt_refer"]]
        .drop_duplicates()
        .assign(_tem_con=True)
    )
    doc_chaves = contas[["cd_cvm", "dt_refer"]].drop_duplicates().reset_index(drop=True)
    doc_chaves = doc_chaves.merge(com_con, on=["cd_cvm", "dt_refer"], how="left")
    doc_chaves["escopo"] = doc_chaves.pop("_tem_con").fillna(False).map({True: "con", False: "ind"})

    # So as linhas do arquivo cujo escopo e o escolhido para o documento --
    # nunca mistura con e ind do mesmo documento.
    contas_escolhidas = contas.merge(doc_chaves, on=["cd_cvm", "dt_refer"], how="inner")
    contas_escolhidas = contas_escolhidas[
        contas_escolhidas["escopo_arquivo"] == contas_escolhidas["escopo"]
    ].reset_index(drop=True)

    # --- Layout: financeiro se a DRE 3.01 falar de intermediacao financeira. ---
    linha_3_01 = contas_escolhidas[
        (contas_escolhidas["origem"] == "DRE") & (contas_escolhidas["cd_conta"] == "3.01")
    ]
    financeiro = (
        linha_3_01[linha_3_01["ds_conta"].str.contains("intermediacao financeira", na=False)][
            ["cd_cvm", "dt_refer"]
        ]
        .drop_duplicates()
        .assign(_financeiro=True)
    )
    layout_por_doc = doc_chaves[["cd_cvm", "dt_refer"]].merge(
        financeiro, on=["cd_cvm", "dt_refer"], how="left"
    )
    layout_por_doc["layout"] = (
        layout_por_doc.pop("_financeiro").fillna(False).map({True: "financeiro", False: "geral"})
    )

    contas_escolhidas = contas_escolhidas.merge(layout_por_doc, on=["cd_cvm", "dt_refer"])

    # --- documentos: agrega as versoes do indice, so quem tem conta no zip. ---
    indice_ordenado = indice.sort_values("versao")
    versao_max = indice_ordenado.groupby(["cd_cvm", "dt_refer"], as_index=False).agg(
        versao=("versao", "max"), recebido_original=("dt_recebido", "min")
    )
    ultima_versao = (
        indice_ordenado.groupby(["cd_cvm", "dt_refer"], as_index=False)
        .tail(1)[["cd_cvm", "dt_refer", "dt_recebido", "id_doc"]]
        .rename(columns={"dt_recebido": "recebido_ultima"})
    )
    documentos_indice = versao_max.merge(ultima_versao, on=["cd_cvm", "dt_refer"])

    documentos = doc_chaves.merge(documentos_indice, on=["cd_cvm", "dt_refer"], how="inner")
    documentos = documentos.merge(layout_por_doc, on=["cd_cvm", "dt_refer"], how="left")
    documentos["tipo"] = tipo
    documentos = documentos[COLUNAS_DOCUMENTOS]

    resultados = _extrair_resultados(contas_escolhidas, tipo)
    balancos = _extrair_balancos(contas_escolhidas, capital, indice, tipo)

    return Extracao(documentos.reset_index(drop=True), resultados, balancos)


def _campo_condicional(
    contas: pd.DataFrame,
    *,
    origem: str,
    codigo: str | None,
    desc_prefixo: str | None,
    desc_contem: str | None,
    so_geral: bool,
) -> pd.DataFrame:
    """Linhas de `contas` que casam a regra de um campo. Uma linha por doc/periodo."""
    filtro = contas["origem"] == origem
    if so_geral:
        filtro &= contas["layout"] == "geral"
    if codigo is not None:
        filtro &= contas["cd_conta"] == codigo
    if desc_prefixo is not None:
        filtro &= contas["ds_conta"].str.startswith(desc_prefixo)
    if desc_contem is not None:
        filtro &= contas["ds_conta"].str.contains(desc_contem, regex=False)
    return contas[filtro]


def _extrair_resultados(contas: pd.DataFrame, tipo: str) -> pd.DataFrame:
    dre_dva = contas[contas["origem"].isin(("DRE", "DVA"))]
    periodos = dre_dva[["cd_cvm", "dt_refer", "dt_ini", "dt_fim"]].drop_duplicates()
    if periodos.empty:
        return pd.DataFrame(columns=COLUNAS_RESULTADOS)

    def juntar(campo: str, casadas: pd.DataFrame) -> None:
        chaves = ["cd_cvm", "dt_refer", "dt_ini", "dt_fim"]
        # drop_duplicates: um documento raro tem 2 contas que casam a mesma
        # regra no mesmo periodo (ex.: dois "3.xx" com desc comecando em
        # "lucro/prejuizo"). Sem isso, o merge multiplicaria a linha do
        # periodo e o INSERT final violaria a chave primaria.
        valores = (
            casadas[["cd_cvm", "dt_refer", "dt_ini", "dt_fim", "valor"]]
            .drop_duplicates(subset=chaves, keep="first")
            .rename(columns={"valor": campo})
        )
        nonlocal periodos
        periodos = periodos.merge(valores, on=chaves, how="left")

    juntar(
        "receita",
        _campo_condicional(
            contas, origem="DRE", codigo="3.01", desc_prefixo=None, desc_contem=None, so_geral=False
        ),
    )
    juntar(
        "resultado_bruto",
        _campo_condicional(
            contas,
            origem="DRE",
            codigo="3.03",
            desc_prefixo="resultado bruto",
            desc_contem=None,
            so_geral=True,
        ),
    )
    juntar(
        "ebit",
        _campo_condicional(
            contas,
            origem="DRE",
            codigo="3.05",
            desc_prefixo="resultado antes do resultado financeiro",
            desc_contem=None,
            so_geral=True,
        ),
    )

    # A linha final do resultado tem quatro redacoes no dado real: "Lucro/
    # Prejuizo do Periodo" (a maioria), "Lucro/Prejuizo Consolidado do
    # Periodo", "Lucro ou Prejuizo Liquido do Periodo" e "Lucro ou Prejuizo
    # Liquido Consolidado do Periodo" (Banco do Brasil e outros bancos). Exigir
    # "periodo" ou "exercicio" descarta as linhas do meio da demonstracao, como
    # "Lucro ou Prejuizo das Operacoes Continuadas"; entre as que sobram vale a
    # de maior codigo, que e a ultima da demonstracao. Conferido contra os 2089
    # documentos do ITR de 2026: todos casam.
    chaves_periodo = ["cd_cvm", "dt_refer", "dt_ini", "dt_fim"]
    lucro = (
        contas[
            (contas["origem"] == "DRE")
            & contas["cd_conta"].str.match(r"^3\.\d{2}$")
            & contas["ds_conta"].str.match(_PADRAO_LUCRO)
            & contas["ds_conta"].str.contains("periodo|exercicio", regex=True)
        ]
        .sort_values("cd_conta", ascending=False)
        .drop_duplicates(subset=chaves_periodo, keep="first")
    )
    juntar("lucro_liquido", lucro)

    filhas_lucro = contas[contas["origem"] == "DRE"].merge(
        lucro[["cd_cvm", "dt_refer", "dt_ini", "dt_fim", "cd_conta"]].rename(
            columns={"cd_conta": "codigo_pai"}
        ),
        on=["cd_cvm", "dt_refer", "dt_ini", "dt_fim"],
    )
    filhas_lucro = filhas_lucro[
        filhas_lucro["cd_conta"].str.match(r".*\.\d{2}$")
        & (filhas_lucro["cd_conta"].str.slice(0, -3) == filhas_lucro["codigo_pai"])
        & filhas_lucro["ds_conta"].str.contains("controladora")
    ]
    juntar("lucro_controladores", filhas_lucro)
    # Sem filha nenhuma (nivel 1 ja e a controladora, ou consolidado sem
    # minoritarios): lucro_controladores repete lucro_liquido.
    periodos["lucro_controladores"] = periodos["lucro_controladores"].fillna(
        periodos["lucro_liquido"]
    )
    # Reparticao zerada nao e reparticao, e ausencia.
    #
    # 561 dos 2.317 periodos do ITR de 2023 trazem "Atribuido a Socios da
    # Empresa Controladora" E "a Socios Nao Controladores" ambos em zero, com o
    # consolidado cheio: o Santander declara R$ 2,78 bi no 3T23 e reparte em
    # 0 + 0. A empresa nao preencheu a quebra -- zero ali nao significa que o
    # controlador nao ganhou nada, porque para isso ele teria de ter 0% da
    # companhia.
    #
    # Sem isto o zero seguia ate a ficha como lucro do trimestre, e o grafico
    # desenhava barra nenhuma como se a empresa nao tivesse dado resultado.
    zerado = (
        (periodos["lucro_controladores"] == 0)
        & periodos["lucro_liquido"].notna()
        & (periodos["lucro_liquido"] != 0)
    )
    periodos.loc[zerado, "lucro_controladores"] = periodos.loc[zerado, "lucro_liquido"]

    juntar(
        "depreciacao_amortizacao",
        _campo_condicional(
            contas,
            origem="DVA",
            codigo="7.04.01",
            desc_prefixo="depreciacao",
            desc_contem=None,
            so_geral=True,
        ),
    )

    periodos["tipo"] = tipo
    return periodos[COLUNAS_RESULTADOS].reset_index(drop=True)


def _extrair_balancos(
    contas: pd.DataFrame, capital: pd.DataFrame, indice: pd.DataFrame, tipo: str
) -> pd.DataFrame:
    bpa_bpp = contas[contas["origem"].isin(("BPA", "BPP"))]
    docs = bpa_bpp[["cd_cvm", "dt_refer"]].drop_duplicates()
    if docs.empty:
        return pd.DataFrame(columns=COLUNAS_BALANCOS)

    def juntar(campo: str, casadas: pd.DataFrame) -> None:
        valores = (
            casadas[["cd_cvm", "dt_refer", "valor"]]
            .drop_duplicates(subset=["cd_cvm", "dt_refer"])
            .rename(columns={"valor": campo})
        )
        nonlocal docs
        docs = docs.merge(valores, on=["cd_cvm", "dt_refer"], how="left")

    juntar(
        "ativo_total",
        _campo_condicional(
            contas, origem="BPA", codigo="1", desc_prefixo=None, desc_contem=None, so_geral=False
        ),
    )
    juntar(
        "ativo_circulante",
        _campo_condicional(
            contas,
            origem="BPA",
            codigo="1.01",
            desc_prefixo="ativo circulante",
            desc_contem=None,
            so_geral=True,
        ),
    )

    caixa_geral = _campo_condicional(
        contas,
        origem="BPA",
        codigo="1.01.01",
        desc_prefixo="caixa e equivalentes",
        desc_contem=None,
        so_geral=True,
    )
    caixa_financeiro = contas[
        (contas["origem"] == "BPA")
        & (contas["layout"] == "financeiro")
        & (contas["cd_conta"] == "1.01")
        & contas["ds_conta"].str.startswith("caixa e equivalentes")
    ]
    juntar("caixa", pd.concat([caixa_geral, caixa_financeiro], ignore_index=True))

    juntar(
        "aplicacoes_financeiras",
        _campo_condicional(
            contas,
            origem="BPA",
            codigo="1.01.02",
            desc_prefixo="aplicacoes financeiras",
            desc_contem=None,
            so_geral=True,
        ),
    )
    juntar(
        "passivo_circulante",
        _campo_condicional(
            contas,
            origem="BPP",
            codigo="2.01",
            desc_prefixo="passivo circulante",
            desc_contem=None,
            so_geral=True,
        ),
    )
    juntar(
        "emprestimos_cp",
        _campo_condicional(
            contas,
            origem="BPP",
            codigo="2.01.04",
            desc_prefixo="emprestimos e financiamentos",
            desc_contem=None,
            so_geral=True,
        ),
    )
    juntar(
        "arrendamento_cp",
        _campo_condicional(
            contas,
            origem="BPP",
            codigo="2.01.04.03",
            desc_prefixo=None,
            desc_contem="arrendamento",
            so_geral=True,
        ),
    )
    juntar(
        "emprestimos_lp",
        _campo_condicional(
            contas,
            origem="BPP",
            codigo="2.02.01",
            desc_prefixo="emprestimos e financiamentos",
            desc_contem=None,
            so_geral=True,
        ),
    )
    juntar(
        "arrendamento_lp",
        _campo_condicional(
            contas,
            origem="BPP",
            codigo="2.02.01.03",
            desc_prefixo=None,
            desc_contem="arrendamento",
            so_geral=True,
        ),
    )

    pl = contas[
        (contas["origem"] == "BPP")
        & contas["cd_conta"].str.match(r"^2\.\d{2}$")
        & contas["ds_conta"].str.startswith("patrimonio liquido")
    ]
    juntar("patrimonio_liquido", pl)

    filhas_pl = contas[contas["origem"] == "BPP"].merge(
        pl[["cd_cvm", "dt_refer", "cd_conta"]].rename(columns={"cd_conta": "codigo_pai"}),
        on=["cd_cvm", "dt_refer"],
    )
    filhas_pl = filhas_pl[
        filhas_pl["cd_conta"].str.match(r".*\.\d{2}$")
        & (filhas_pl["cd_conta"].str.slice(0, -3) == filhas_pl["codigo_pai"])
        & filhas_pl["ds_conta"].str.contains("nao controladores")
    ]
    juntar("pl_nao_controladores", filhas_pl)

    # Acoes: liga pelo CNPJ_CIA (composicao do capital nao tem CD_CVM).
    cnpj_por_doc = indice[["cd_cvm", "dt_refer", "cnpj_cia"]].drop_duplicates(
        subset=["cd_cvm", "dt_refer"]
    )
    docs = docs.merge(cnpj_por_doc, on=["cd_cvm", "dt_refer"], how="left")
    docs = docs.merge(capital, on=["cnpj_cia", "dt_refer"], how="left")
    docs = docs.drop(columns=["cnpj_cia"])

    docs["tipo"] = tipo
    return docs[COLUNAS_BALANCOS].reset_index(drop=True)
