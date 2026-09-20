"""Extracao dos dados abertos da CVM (sem banco): tests/fixtures/cvm/README.md
explica de onde vieram os CSVs.
"""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import pytest

from scanner.fundamentos.cvm import (
    CvmIndisponivelError,
    baixar,
    extrair_documentos,
    ler_cadastro,
    ler_valores_mobiliarios,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cvm"

UNIPAR = 11592
ITAU = 19348
ARMAC = 26069
INDIVIDUAL = 27294
BANCO_BRASIL = 1023
TODOS_CD_CVM = {UNIPAR, ITAU, ARMAC, INDIVIDUAL}


def _montar_zip(tmp_path: Path, nome_zip: str, prefixo: str) -> Path:
    destino = tmp_path / nome_zip
    with zipfile.ZipFile(destino, "w") as zf:
        for arquivo in sorted(FIXTURES.glob(f"{prefixo}_cia_aberta_*.csv")):
            zf.write(arquivo, arquivo.name)
    return destino


@pytest.fixture
def itr_zip(tmp_path: Path) -> Path:
    return _montar_zip(tmp_path, "itr_2026.zip", "itr")


@pytest.fixture
def dfp_zip(tmp_path: Path) -> Path:
    return _montar_zip(tmp_path, "dfp_2025.zip", "dfp")


def _resultado(resultados: pd.DataFrame, cd_cvm: int, dt_ini: date, dt_fim: date) -> pd.Series:
    linha = resultados[
        (resultados["cd_cvm"] == cd_cvm)
        & (resultados["dt_ini"] == dt_ini)
        & (resultados["dt_fim"] == dt_fim)
    ]
    assert len(linha) == 1, f"esperava 1 linha, achou {len(linha)}"
    return linha.iloc[0]


def _balanco(balancos: pd.DataFrame, cd_cvm: int, dt_refer: date = date(2026, 6, 30)) -> pd.Series:
    linha = balancos[(balancos["cd_cvm"] == cd_cvm) & (balancos["dt_refer"] == dt_refer)]
    assert len(linha) == 1, f"esperava 1 linha, achou {len(linha)}"
    return linha.iloc[0]


def _documento(documentos: pd.DataFrame, cd_cvm: int, dt_refer: date) -> pd.Series:
    linha = documentos[(documentos["cd_cvm"] == cd_cvm) & (documentos["dt_refer"] == dt_refer)]
    assert len(linha) == 1, f"esperava 1 linha, achou {len(linha)}"
    return linha.iloc[0]


# --- Unipar: layout geral, consolidado -- confere a tabela toda da spec -----


def test_unipar_dre_trimestre_e_acumulado_2026_06(itr_zip: Path) -> None:
    extracao = extrair_documentos(itr_zip, "ITR", TODOS_CD_CVM)

    tri = _resultado(extracao.resultados, UNIPAR, date(2026, 4, 1), date(2026, 6, 30))
    assert tri["receita"] == pytest.approx(1_495_676_000)
    assert tri["resultado_bruto"] == pytest.approx(497_588_000)
    assert tri["ebit"] == pytest.approx(300_481_000)
    assert tri["lucro_liquido"] == pytest.approx(123_321_000)
    assert tri["lucro_controladores"] == pytest.approx(125_074_000)
    # D&A so existe na linha do acumulado.
    assert pd.isna(tri["depreciacao_amortizacao"])

    acumulado = _resultado(extracao.resultados, UNIPAR, date(2026, 1, 1), date(2026, 6, 30))
    assert acumulado["receita"] == pytest.approx(2_733_910_000)
    assert acumulado["lucro_controladores"] == pytest.approx(162_546_000)
    assert acumulado["depreciacao_amortizacao"] == pytest.approx(-154_745_000)


def test_unipar_balanco_2026_06(itr_zip: Path) -> None:
    extracao = extrair_documentos(itr_zip, "ITR", TODOS_CD_CVM)
    linha = _balanco(extracao.balancos, UNIPAR)

    assert linha["ativo_total"] == pytest.approx(7_759_771_000)
    assert linha["ativo_circulante"] == pytest.approx(2_808_901_000)
    assert linha["caixa"] == pytest.approx(635_751_000)
    assert linha["aplicacoes_financeiras"] == pytest.approx(735_544_000)
    assert linha["passivo_circulante"] == pytest.approx(1_177_117_000)
    assert linha["emprestimos_cp"] == pytest.approx(227_600_000)
    assert linha["arrendamento_cp"] == pytest.approx(2_461_000)
    assert linha["emprestimos_lp"] == pytest.approx(3_474_947_000)
    assert linha["arrendamento_lp"] == pytest.approx(9_128_000)
    assert linha["patrimonio_liquido"] == pytest.approx(2_010_867_000)
    assert linha["pl_nao_controladores"] == pytest.approx(12_045_000)
    assert linha["acoes_on"] == 39_059_883
    assert linha["acoes_pn"] == 74_113_382
    assert linha["tesouraria_on"] == 74_500
    assert linha["tesouraria_pn"] == 1_476_612


def test_unipar_documento_2026_06_e_geral_con(itr_zip: Path) -> None:
    extracao = extrair_documentos(itr_zip, "ITR", TODOS_CD_CVM)
    doc = _documento(extracao.documentos, UNIPAR, date(2026, 6, 30))
    assert doc["escopo"] == "con"
    assert doc["layout"] == "geral"
    assert doc["versao"] == 1
    assert doc["recebido_original"] == date(2026, 8, 6)
    assert doc["recebido_ultima"] == date(2026, 8, 6)


def test_unipar_dfp_2025(dfp_zip: Path) -> None:
    extracao = extrair_documentos(dfp_zip, "DFP", TODOS_CD_CVM)
    doc = _documento(extracao.documentos, UNIPAR, date(2025, 12, 31))
    assert doc["recebido_original"] == date(2026, 3, 19)

    resultado = _resultado(extracao.resultados, UNIPAR, date(2025, 1, 1), date(2025, 12, 31))
    assert resultado["receita"] == pytest.approx(5_142_676_000)
    assert resultado["lucro_liquido"] == pytest.approx(481_744_000)
    assert resultado["lucro_controladores"] == pytest.approx(488_622_000)
    assert resultado["depreciacao_amortizacao"] == pytest.approx(-316_152_000)

    balanco = _balanco(extracao.balancos, UNIPAR, date(2025, 12, 31))
    assert balanco["ativo_total"] == pytest.approx(7_234_816_000)
    assert balanco["patrimonio_liquido"] == pytest.approx(1_816_695_000)
    assert balanco["pl_nao_controladores"] == pytest.approx(12_896_000)


# --- Itau: layout financeiro ------------------------------------------------


def test_itau_layout_financeiro(itr_zip: Path) -> None:
    extracao = extrair_documentos(itr_zip, "ITR", TODOS_CD_CVM)
    doc = _documento(extracao.documentos, ITAU, date(2026, 6, 30))
    assert doc["layout"] == "financeiro"
    assert doc["escopo"] == "con"

    tri = _resultado(extracao.resultados, ITAU, date(2026, 4, 1), date(2026, 6, 30))
    assert tri["lucro_liquido"] == pytest.approx(12_324_000_000)
    # Campos "geral:" ficam NULL no layout financeiro.
    assert pd.isna(tri["resultado_bruto"])
    assert pd.isna(tri["ebit"])

    balanco = _balanco(extracao.balancos, ITAU)
    assert balanco["patrimonio_liquido"] == pytest.approx(228_026_000_000)
    assert balanco["caixa"] == pytest.approx(35_351_000_000)
    # ativo_circulante e "geral:" -- no layout financeiro fica NULL.
    assert pd.isna(balanco["ativo_circulante"])


def test_banco_com_outra_redacao_de_lucro(itr_zip: Path) -> None:
    """Nem todo banco escreve a linha do lucro igual ao Itau.

    O Banco do Brasil usa "Lucro ou Prejuizo Liquido Consolidado do Periodo"
    (conta 3.11), e ainda tem "Lucro ou Prejuizo das Operacoes Continuadas"
    (3.07) antes dela, com o MESMO valor no trimestre. Casar so por
    "lucro/prejuizo" deixava 244 documentos de banco sem lucro nenhum; pegar a
    primeira conta que casa pegaria a linha do meio da demonstracao.
    """
    extracao = extrair_documentos(itr_zip, "ITR", {BANCO_BRASIL})
    doc = _documento(extracao.documentos, BANCO_BRASIL, date(2026, 6, 30))
    assert doc["layout"] == "financeiro"

    tri = _resultado(extracao.resultados, BANCO_BRASIL, date(2026, 4, 1), date(2026, 6, 30))
    assert tri["lucro_liquido"] == pytest.approx(3_256_684_000)
    assert tri["lucro_controladores"] == pytest.approx(2_397_643_000)

    acumulado = _resultado(extracao.resultados, BANCO_BRASIL, date(2026, 1, 1), date(2026, 6, 30))
    assert acumulado["lucro_liquido"] == pytest.approx(6_362_961_000)


# --- Empresa so individual: lucro_controladores == lucro_liquido -----------


def test_individual_sem_filha_repete_lucro_liquido(itr_zip: Path) -> None:
    extracao = extrair_documentos(itr_zip, "ITR", TODOS_CD_CVM)
    doc = _documento(extracao.documentos, INDIVIDUAL, date(2026, 6, 30))
    assert doc["escopo"] == "ind"
    assert doc["layout"] == "geral"

    tri = _resultado(extracao.resultados, INDIVIDUAL, date(2026, 4, 1), date(2026, 6, 30))
    assert tri["lucro_liquido"] == pytest.approx(80_000)
    assert tri["lucro_controladores"] == pytest.approx(80_000)


# --- Documento com 2 versoes no indice --------------------------------------


def test_documento_com_duas_versoes(itr_zip: Path) -> None:
    extracao = extrair_documentos(itr_zip, "ITR", TODOS_CD_CVM)
    doc = _documento(extracao.documentos, ARMAC, date(2026, 6, 30))
    assert doc["versao"] == 2
    # v1 recebida 2026-08-11, v2 2026-08-12 (indice real).
    assert doc["recebido_original"] == date(2026, 8, 11)
    assert doc["recebido_ultima"] == date(2026, 8, 12)


# --- Regras de robustez da extracao -----------------------------------------


def test_empresa_fora_de_cd_cvms_nao_aparece(itr_zip: Path) -> None:
    extracao = extrair_documentos(itr_zip, "ITR", {UNIPAR})
    assert ITAU not in set(extracao.documentos["cd_cvm"])
    assert ARMAC not in set(extracao.documentos["cd_cvm"])


def test_penultimo_e_ignorado(itr_zip: Path) -> None:
    extracao = extrair_documentos(itr_zip, "ITR", TODOS_CD_CVM)
    # O comparativo do ano anterior (PENULTIMO) nao pode gerar linha de resultado.
    assert extracao.resultados[
        (extracao.resultados["cd_cvm"] == UNIPAR)
        & (extracao.resultados["dt_fim"] == date(2025, 6, 30))
    ].empty


def test_conta_ausente_vira_null_nao_zero(itr_zip: Path) -> None:
    # Itau (financeiro) nao reporta arrendamento -- o campo tem de ficar NULL.
    extracao = extrair_documentos(itr_zip, "ITR", TODOS_CD_CVM)
    balanco = _balanco(extracao.balancos, ITAU)
    assert pd.isna(balanco["arrendamento_cp"])
    assert pd.isna(balanco["arrendamento_lp"])


def test_composicao_do_capital_liga_pelo_cnpj(itr_zip: Path) -> None:
    extracao = extrair_documentos(itr_zip, "ITR", TODOS_CD_CVM)
    balanco = _balanco(extracao.balancos, UNIPAR)
    assert balanco["acoes_on"] == 39_059_883


def test_normalizacao_de_acento_e_maiuscula(itr_zip: Path) -> None:
    # "Depreciação" (com cedilha e acento) tem de casar com "depreciacao".
    extracao = extrair_documentos(itr_zip, "ITR", TODOS_CD_CVM)
    acumulado = _resultado(extracao.resultados, UNIPAR, date(2026, 1, 1), date(2026, 6, 30))
    assert acumulado["depreciacao_amortizacao"] == pytest.approx(-154_745_000)


def test_escala_unidade_nao_multiplica(tmp_path: Path) -> None:
    """Fabrica uma linha com ESCALA_MOEDA=UNIDADE: nenhuma empresa real do
    recorte reporta assim, entao o caso e construido aqui mesmo.
    """
    indice = (
        "CNPJ_CIA;DT_REFER;VERSAO;CD_CVM;ID_DOC;DT_RECEB\n"
        "11.111.111/0001-11;2026-06-30;1;999999;1;2026-08-01\n"
    )
    bpa = (
        "CNPJ_CIA;DT_REFER;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;"
        "DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA\n"
        "11.111.111/0001-11;2026-06-30;999999;BPA;REAL;UNIDADE;ÚLTIMO;"
        "2026-06-30;1;Ativo Total;12345.0000000000;S\n"
    )
    zip_path = tmp_path / "itr_2026.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        # latin-1, como os CSVs reais da CVM -- escrever em utf-8 (o default
        # de `writestr` com `str`) corromperia o "ÚLTIMO" na releitura.
        zf.writestr("itr_cia_aberta_2026.csv", indice.encode("latin-1"))
        zf.writestr("itr_cia_aberta_BPA_con_2026.csv", bpa.encode("latin-1"))

    extracao = extrair_documentos(zip_path, "ITR", {999999})
    linha = _balanco(extracao.balancos, 999999)
    assert linha["ativo_total"] == pytest.approx(12_345)


def _zip_com_dre(tmp_path: Path, linhas_dre: str) -> Path:
    """Um zip de ITR minimo com uma DRE fabricada, para casos que o recorte real
    nao tem. Mesmo formato dos CSVs da CVM: latin-1 e separador `;`."""
    indice = (
        "CNPJ_CIA;DT_REFER;VERSAO;CD_CVM;ID_DOC;DT_RECEB\n"
        "11.111.111/0001-11;2026-06-30;1;999999;1;2026-08-01\n"
    )
    cabecalho = (
        "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;"
        "ORDEM_EXERC;DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA\n"
    )
    zip_path = tmp_path / "itr_2026.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("itr_cia_aberta_2026.csv", indice.encode("latin-1"))
        zf.writestr(
            "itr_cia_aberta_DRE_con_2026.csv",
            (cabecalho + linhas_dre).encode("latin-1"),
        )
    return zip_path


def _linha_dre(cd_conta: str, ds_conta: str, valor: str) -> str:
    return (
        f"11.111.111/0001-11;2026-06-30;1;FABRICADA S.A.;999999;DRE;REAL;MIL;"
        f"ÚLTIMO;2026-04-01;2026-06-30;{cd_conta};{ds_conta};{valor};S\n"
    )


def test_reparticao_do_lucro_zerada_vale_o_consolidado(tmp_path: Path) -> None:
    """Filha "controladora" em zero com o pai cheio e ausencia, nao reparticao.

    O caso real e o Banco Santander: no 3T23 ele declara R$ 2,78 bi em
    "Lucro/Prejuizo Consolidado do Periodo" (3.09) e reparte em 0 + 0 nas duas
    filhas. Sao 561 dos 2.317 periodos do ITR de 2023 -- e 781 trimestres da
    base local saiam com lucro exatamente zero por causa disso, incluindo
    Santander, Sabesp e Eletrobras.

    Zero ali nao pode significar "o controlador nao ganhou nada": para isso ele
    teria de ter 0% da companhia.
    """
    dre = (
        _linha_dre("3.01", "Receitas da Intermediação Financeira", "32651076.00")
        + _linha_dre("3.09", "Lucro/Prejuízo Consolidado do Período", "2780672.00")
        + _linha_dre("3.09.01", "Atribuído a Sócios da Empresa Controladora", "0.00")
        + _linha_dre("3.09.02", "Atribuído a Sócios Não Controladores", "0.00")
    )
    extracao = extrair_documentos(_zip_com_dre(tmp_path, dre), "ITR", {999999})
    linha = _resultado(extracao.resultados, 999999, date(2026, 4, 1), date(2026, 6, 30))
    assert linha["lucro_liquido"] == pytest.approx(2_780_672_000)
    assert linha["lucro_controladores"] == pytest.approx(2_780_672_000)


def test_reparticao_do_lucro_preenchida_continua_valendo(tmp_path: Path) -> None:
    """A correcao nao pode atropelar quem preencheu: com minoritarios de
    verdade, o lucro dos controladores e MENOR que o consolidado."""
    dre = (
        _linha_dre("3.09", "Lucro/Prejuízo Consolidado do Período", "1000000.00")
        + _linha_dre("3.09.01", "Atribuído a Sócios da Empresa Controladora", "900000.00")
        + _linha_dre("3.09.02", "Atribuído a Sócios Não Controladores", "100000.00")
    )
    extracao = extrair_documentos(_zip_com_dre(tmp_path, dre), "ITR", {999999})
    linha = _resultado(extracao.resultados, 999999, date(2026, 4, 1), date(2026, 6, 30))
    assert linha["lucro_controladores"] == pytest.approx(900_000_000)


def test_prejuizo_repartido_em_zero_tambem_vale_o_consolidado(tmp_path: Path) -> None:
    """O mesmo vale para prejuizo: o sinal nao muda a regra."""
    dre = _linha_dre("3.09", "Lucro/Prejuízo Consolidado do Período", "-450000.00") + _linha_dre(
        "3.09.01", "Atribuído a Sócios da Empresa Controladora", "0.00"
    )
    extracao = extrair_documentos(_zip_com_dre(tmp_path, dre), "ITR", {999999})
    linha = _resultado(extracao.resultados, 999999, date(2026, 4, 1), date(2026, 6, 30))
    assert linha["lucro_controladores"] == pytest.approx(-450_000_000)


def test_consolidado_zerado_de_verdade_continua_zero(tmp_path: Path) -> None:
    """Pai em zero nao e ausencia: nada a substituir, e zero permanece."""
    dre = _linha_dre("3.09", "Lucro/Prejuízo Consolidado do Período", "0.00") + _linha_dre(
        "3.09.01", "Atribuído a Sócios da Empresa Controladora", "0.00"
    )
    extracao = extrair_documentos(_zip_com_dre(tmp_path, dre), "ITR", {999999})
    linha = _resultado(extracao.resultados, 999999, date(2026, 4, 1), date(2026, 6, 30))
    assert linha["lucro_controladores"] == pytest.approx(0)


# --- Cadastro da CVM ---------------------------------------------------------


def test_ler_cadastro_deduplica_e_extrai_cnpj() -> None:
    cadastro = ler_cadastro(FIXTURES / "cad_cia_aberta.csv")
    assert set(cadastro["cd_cvm"]) == {UNIPAR, ITAU, ARMAC, INDIVIDUAL}
    linha = cadastro[cadastro["cd_cvm"] == UNIPAR].iloc[0]
    assert linha["cnpj"] == "33958695000178"
    assert linha["setor_cvm"] == "Petroquímicos e Borracha"
    # cad_cia_aberta.csv real tem linha duplicada para a Unipar e a Armac.
    assert len(cadastro) == len(set(cadastro["cd_cvm"]))


# --- FCA: a ligacao ticker -> empresa ----------------------------------------


def test_fca_le_codigo_de_negociacao_e_cnpj(tmp_path: Path) -> None:
    zip_fca = tmp_path / "fca_2026.zip"
    with zipfile.ZipFile(zip_fca, "w") as zf:
        arquivo = FIXTURES / "fca_cia_aberta_valor_mobiliario_2026.csv"
        zf.write(arquivo, arquivo.name)

    valores = ler_valores_mobiliarios(zip_fca)

    unip6 = valores[valores["ticker"] == "UNIP6"].iloc[0]
    assert unip6["cnpj"] == "33958695000178"
    assert unip6["dt_refer"] == date(2026, 1, 1)
    # Linha de debenture (sem codigo de negociacao) nao liga ticker nenhum.
    assert "" not in set(valores["ticker"])
    assert set(valores["ticker"]) == {"UNIP3", "UNIP6", "ITUB4", "ARMC3"}


# --- Download condicional ----------------------------------------------------


class _RespostaFalsa:
    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self.headers = headers or {}

    def __enter__(self) -> _RespostaFalsa:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=None)  # type: ignore[arg-type]

    def iter_bytes(self, _tamanho: int) -> list[bytes]:
        return [b"conteudo"]


def test_baixar_200_grava_arquivo_e_devolve_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cabecalhos = {"ETag": "abc", "Last-Modified": "Wed, 06 Aug 2026 12:00:00 GMT"}
    resposta = _RespostaFalsa(200, cabecalhos)
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: resposta)

    destino = tmp_path / "arquivo.zip"
    resultado = baixar("http://exemplo/arquivo.zip", destino)

    assert resultado.alterado is True
    assert resultado.caminho == destino
    assert destino.read_bytes() == b"conteudo"
    assert resultado.etag == "abc"
    assert resultado.modificado_em is not None


def test_baixar_304_nao_baixa_nada(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _RespostaFalsa(304))

    destino = tmp_path / "arquivo.zip"
    resultado = baixar("http://exemplo/arquivo.zip", destino, etag="abc")

    assert resultado.alterado is False
    assert resultado.caminho is None
    assert not destino.exists()


def test_baixar_com_exigir_conteudo_ignora_304_sem_arquivo_em_disco(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No runner do GitHub o cache comeca vazio a cada execucao.

    Mandar `If-None-Match` sem ter o arquivo levaria um 304 e deixaria quem
    precisa LER o conteudo (cadastro e FCA) sem nada nas maos.
    """
    enviados: list[dict[str, str]] = []

    def fake_stream(_metodo: str, _url: str, **kwargs: object) -> _RespostaFalsa:
        enviados.append(dict(kwargs.get("headers") or {}))  # type: ignore[arg-type]
        return _RespostaFalsa(200, {"ETag": "novo"})

    monkeypatch.setattr(httpx, "stream", fake_stream)

    destino = tmp_path / "cad.csv"
    baixar("http://x/cad.csv", destino, etag="antigo", exigir_conteudo=True)
    assert enviados[-1] == {}, "sem arquivo em disco, nao pode pedir condicional"

    # Com o arquivo em disco, a checagem condicional volta a valer.
    baixar("http://x/cad.csv", destino, etag="antigo", exigir_conteudo=True)
    assert enviados[-1] == {"If-None-Match": "antigo"}


def test_baixar_404_vira_ausencia_nao_erro(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _RespostaFalsa(404))

    resultado = baixar("http://exemplo/dfp_2027.zip", tmp_path / "arquivo.zip")

    assert resultado.alterado is False
    assert resultado.caminho is None


def test_baixar_desiste_apos_tentativas_esgotadas(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _RespostaFalsa(503))
    monkeypatch.setattr("time.sleep", lambda _s: None)

    with pytest.raises(CvmIndisponivelError):
        baixar("http://exemplo/arquivo.zip", tmp_path / "arquivo.zip", tentativas=2, espera=0)
