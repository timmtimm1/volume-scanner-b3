"""Carga de fundamentos com banco: empresas + zips da CVM (sem rede de verdade).

`tests/fixtures/cvm/README.md` explica de onde vieram os CSVs usados aqui.
"""

from __future__ import annotations

import shutil
import zipfile
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import Engine, delete, select
from sqlalchemy.dialects.postgresql import insert

from scanner.config import FundamentosConfig
from scanner.fundamentos import carga as carga_mod
from scanner.fundamentos.b3 import B3IndisponivelError, Candidato
from scanner.fundamentos.cvm import CvmIndisponivelError, Download
from scanner.storage import repository
from scanner.storage.models import (
    ArquivoExterno,
    CvmDocumento,
    CvmResultado,
    DailyBar,
    Empresa,
    EmpresaTicker,
)

pytestmark = pytest.mark.db

FIXTURES = Path(__file__).parent / "fixtures" / "cvm"

UNIPAR, ITAU, ARMAC, INDIVIDUAL = 11592, 19348, 26069, 27294
TICKERS = {
    "UNIP6": ("UNIP", UNIPAR),
    "ITUB4": ("ITUB", ITAU),
    "ARMC3": ("ARMC", ARMAC),
    "CRSM3": ("CRSM", INDIVIDUAL),
}
TODOS_CD_CVM = [UNIPAR, ITAU, ARMAC, INDIVIDUAL]


# O que a busca da B3 responde para CRSM3, o unico ticker fora do FCA aqui.
# O primeiro candidato imita a armadilha real do EMBR3: uma empresa homonima
# que nem cadastro na CVM tem. A carga so pode aceitar o segundo.
HOMONIMA = 917848
CANDIDATOS_B3 = {
    "CRSM3": [
        # Sem registro na CVM: barrada pela primeira guarda, nem vai ao detalhe.
        Candidato(HOMONIMA, "ROTA DE SANTA MARIA COMERCIO LTDA"),
        # Existe na CVM, mas os codigos dela nao tem CRSM3: barrada pela segunda.
        Candidato(ARMAC, "ARMAC LOCACAO S.A."),
        Candidato(INDIVIDUAL, "CONCESSIONARIA ROTA DE SANTA MARIA S.A"),
    ],
}
CODIGOS_B3 = {
    HOMONIMA: {"RSMC3"},
    ARMAC: {"ARMC3"},
    INDIVIDUAL: {"CRSM3"},
}


class B3Falsa:
    """Substitui os dois endpoints da B3, guardando o que foi perguntado."""

    def __init__(self) -> None:
        self.buscas: list[str] = []
        self.detalhes: list[int] = []
        self.fora_do_ar = False

    def buscar(self, _cliente: object, ticker: str) -> list[Candidato]:
        self.buscas.append(ticker)
        if self.fora_do_ar:
            raise B3IndisponivelError("B3 fora do ar (teste)")
        return CANDIDATOS_B3.get(ticker, [])

    def codigos(self, _cliente: object, cd_cvm: int) -> set[str]:
        self.detalhes.append(cd_cvm)
        return CODIGOS_B3.get(cd_cvm, set())


def _copiar_fca(ano: int) -> Callable[[Path], None]:
    """Monta o zip do FCA do ano com o recorte real de `tests/fixtures/cvm`."""

    def builder(destino: Path) -> None:
        arquivo = FIXTURES / f"fca_cia_aberta_valor_mobiliario_{ano}.csv"
        with zipfile.ZipFile(destino, "w") as zf:
            zf.write(arquivo, arquivo.name)

    return builder


def _montar_zip_fixture(destino: Path, prefixo: str) -> None:
    with zipfile.ZipFile(destino, "w") as zf:
        for arquivo in sorted(FIXTURES.glob(f"{prefixo}_cia_aberta_*.csv")):
            zf.write(arquivo, arquivo.name)


class ServidorFalso:
    """Substitui `baixar`: serve os fixtures reais, com versao controlavel por URL."""

    def __init__(self) -> None:
        self.versao: dict[str, int] = {}
        self.builders: dict[str, Callable[[Path], None]] = {}
        self.chamadas: list[tuple[str, str | None, str | None, bool]] = []
        self.falhando: set[str] = set()

    def registrar(self, url: str, builder: Callable[[Path], None]) -> None:
        self.builders[url] = builder
        self.versao.setdefault(url, 1)

    def bump(self, url: str) -> None:
        self.versao[url] = self.versao.get(url, 1) + 1

    def __call__(
        self,
        url: str,
        destino: Path,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        forcar: bool = False,
        **_kwargs: object,
    ) -> Download:
        self.chamadas.append((url, etag, last_modified, forcar))
        if url in self.falhando:
            raise CvmIndisponivelError(f"falha simulada em {url}")
        if url not in self.builders:
            return Download(False, None, None, None, None)

        versao_atual = f"v{self.versao[url]}"
        if not forcar and etag == versao_atual:
            return Download(False, None, etag, last_modified, None)

        destino.parent.mkdir(parents=True, exist_ok=True)
        self.builders[url](destino)
        modificado = datetime(2026, 1, self.versao[url], tzinfo=UTC)
        return Download(True, destino, versao_atual, f"lm-{versao_atual}", modificado)


@pytest.fixture
def config() -> FundamentosConfig:
    return FundamentosConfig(ano_inicial=2025, dias_para_rechecar_ticker=7)


@pytest.fixture
def servidor(monkeypatch: pytest.MonkeyPatch) -> ServidorFalso:
    fake = ServidorFalso()
    cadastro_fixture = FIXTURES / "cad_cia_aberta.csv"

    def _copiar_cadastro(destino: Path) -> None:
        shutil.copy(cadastro_fixture, destino)

    fake.registrar(carga_mod.CADASTRO_URL, _copiar_cadastro)
    fake.registrar(
        carga_mod._url_zip("ITR", 2026), lambda destino: _montar_zip_fixture(destino, "itr")
    )
    fake.registrar(
        carga_mod._url_zip("DFP", 2025), lambda destino: _montar_zip_fixture(destino, "dfp")
    )
    fake.registrar(carga_mod._url_fca(2025), _copiar_fca(2025))
    fake.registrar(carga_mod._url_fca(2026), _copiar_fca(2026))
    monkeypatch.setattr(carga_mod, "baixar", fake)
    return fake


@pytest.fixture
def b3(monkeypatch: pytest.MonkeyPatch) -> B3Falsa:
    falsa = B3Falsa()
    monkeypatch.setattr(carga_mod, "novo_cliente", lambda: _ClienteDescartavel())
    monkeypatch.setattr(carga_mod, "buscar_candidatos", falsa.buscar)
    monkeypatch.setattr(carga_mod, "codigos_da_empresa", falsa.codigos)
    # As etapas de proventos (fase 2) rodam no mesmo comando; aqui elas nao sao
    # o assunto, e a B3 nao pode ser chamada de verdade. Os testes delas vivem
    # em `test_fundamentos_proventos_carga.py`.
    monkeypatch.setattr(carga_mod, "detalhe_da_empresa", lambda *_a, **_k: None)
    monkeypatch.setattr(carga_mod, "proventos_recentes", lambda *_a, **_k: [])
    monkeypatch.setattr(carga_mod, "proventos_historicos", lambda *_a, **_k: [])
    return falsa


class _ClienteDescartavel:
    """`httpx.Client` de mentira: a B3 falsa nao usa o cliente para nada."""

    def close(self) -> None:
        return None


@pytest.fixture
def tickers(engine: Engine) -> Iterator[list[str]]:
    codigos = list(TICKERS)
    with engine.begin() as conn:
        conn.execute(
            insert(DailyBar).values(
                [
                    {
                        "ticker": ticker,
                        "trade_date": date(2026, 1, 2),
                        "close": 10,
                        "volume_financial": 1,
                    }
                    for ticker in codigos
                ]
            )
        )
    yield codigos
    with engine.begin() as conn:
        conn.execute(delete(DailyBar).where(DailyBar.ticker.in_(codigos)))
        conn.execute(delete(EmpresaTicker).where(EmpresaTicker.ticker.in_(codigos)))
        conn.execute(delete(Empresa).where(Empresa.cd_cvm.in_(TODOS_CD_CVM)))
        conn.execute(
            delete(ArquivoExterno).where(
                ArquivoExterno.url.in_(
                    [
                        carga_mod.CADASTRO_URL,
                        carga_mod._url_zip("ITR", 2025),
                        carga_mod._url_zip("ITR", 2026),
                        carga_mod._url_zip("DFP", 2025),
                        carga_mod._url_zip("DFP", 2026),
                        carga_mod._url_fca(2025),
                        carga_mod._url_fca(2026),
                    ]
                )
            )
        )


AGORA = datetime(2026, 9, 17, tzinfo=UTC)


def _rodar(
    engine: Engine,
    config: FundamentosConfig,
    *,
    forcar: bool = False,
    agora: datetime = AGORA,
) -> carga_mod.RelatorioFundamentos:
    return carga_mod.atualizar_fundamentos(engine, config, agora=agora, forcar=forcar, pausa_b3=0)


def test_carga_liga_as_quatro_empresas(
    engine: Engine,
    config: FundamentosConfig,
    servidor: ServidorFalso,
    b3: B3Falsa,
    tickers: list[str],
) -> None:
    relatorio = _rodar(engine, config)

    assert not relatorio.teve_falha
    assert repository.contar_empresas(engine) == 4
    assert repository.tickers_sem_empresa(engine) == []
    # UNIP6, ITUB4 e ARMC3 saem do FCA; CRSM3 so existe na busca da B3.
    assert repository.contagem_do_mapeamento(engine) == (4, 0)
    assert b3.buscas == ["CRSM3"]

    with engine.connect() as conn:
        total_docs = conn.execute(
            select(CvmDocumento).where(CvmDocumento.cd_cvm.in_(TODOS_CD_CVM))
        ).all()
    # Unipar: ITR 2026-03, ITR 2026-06, DFP 2025-12. Itau: ITR 2026-06.
    # Armac: ITR 2026-06. Individual: ITR 2026-06. Total 6 documentos.
    assert len(total_docs) == 6


def test_escopo_vem_de_daily_bars(
    engine: Engine,
    config: FundamentosConfig,
    servidor: ServidorFalso,
    b3: B3Falsa,
    tickers: list[str],
) -> None:
    # So dois tickers no banco -- so essas duas empresas devem ficar ligadas.
    with engine.begin() as conn:
        conn.execute(delete(DailyBar).where(DailyBar.ticker.in_(["ARMC3", "CRSM3"])))

    _rodar(engine, config)

    ligados = {int(c) for c in repository.cd_cvms_mapeados(engine)}
    assert ligados == {UNIPAR, ITAU}


def test_segunda_carga_e_toda_304_e_nao_toca_nos_dados(
    engine: Engine,
    config: FundamentosConfig,
    servidor: ServidorFalso,
    b3: B3Falsa,
    tickers: list[str],
) -> None:
    _rodar(engine, config)
    with engine.connect() as conn:
        antes = pd.read_sql(select(CvmDocumento).where(CvmDocumento.cd_cvm.in_(TODOS_CD_CVM)), conn)

    relatorio = _rodar(engine, config)

    assert not relatorio.teve_falha
    interessa = ("ITR 2026", "DFP 2025")
    processados = [linha for linha in relatorio.arquivos if any(p in linha for p in interessa)]
    assert processados and all("sem mudanca" in linha for linha in processados)
    with engine.connect() as conn:
        depois = pd.read_sql(
            select(CvmDocumento).where(CvmDocumento.cd_cvm.in_(TODOS_CD_CVM)), conn
        )
    pd.testing.assert_frame_equal(
        antes.sort_values(["cd_cvm", "tipo", "dt_refer"]).reset_index(drop=True),
        depois.sort_values(["cd_cvm", "tipo", "dt_refer"]).reset_index(drop=True),
    )


def test_carga_dupla_do_zero_e_idempotente(
    engine: Engine,
    config: FundamentosConfig,
    servidor: ServidorFalso,
    b3: B3Falsa,
    tickers: list[str],
) -> None:
    _rodar(engine, config)
    with engine.connect() as conn:
        resultado1 = pd.read_sql(
            select(CvmDocumento).where(CvmDocumento.cd_cvm.in_(TODOS_CD_CVM)), conn
        )
    contagem1 = repository.contar_empresas(engine)

    # "do zero" de novo: reseta os arquivos_externos para forcar reprocessar.
    with engine.begin() as conn:
        conn.execute(
            delete(ArquivoExterno).where(
                ArquivoExterno.url.in_(
                    [carga_mod._url_zip("ITR", 2026), carga_mod._url_zip("DFP", 2025)]
                )
            )
        )
    relatorio2 = _rodar(engine, config)

    assert not relatorio2.teve_falha
    assert repository.contar_empresas(engine) == contagem1
    with engine.connect() as conn:
        resultado2 = pd.read_sql(
            select(CvmDocumento).where(CvmDocumento.cd_cvm.in_(TODOS_CD_CVM)), conn
        )
    assert len(resultado1) == len(resultado2)


def test_reapresentacao_troca_numeros_e_mantem_recebido_original(
    engine: Engine,
    config: FundamentosConfig,
    servidor: ServidorFalso,
    b3: B3Falsa,
    tickers: list[str],
) -> None:
    _rodar(engine, config)
    with engine.connect() as conn:
        doc_antes = conn.execute(
            select(CvmDocumento.recebido_original, CvmDocumento.versao).where(
                CvmDocumento.cd_cvm == UNIPAR, CvmDocumento.dt_refer == date(2026, 6, 30)
            )
        ).one()

    # A CVM publica uma nova versao do mesmo arquivo (o indice do zip fixture
    # ja trai a Armac com 2 versoes; aqui simulamos o zip inteiro mudando).
    servidor.bump(carga_mod._url_zip("ITR", 2026))
    relatorio = _rodar(engine, config)

    assert not relatorio.teve_falha
    with engine.connect() as conn:
        doc_depois = conn.execute(
            select(CvmDocumento.recebido_original, CvmDocumento.versao).where(
                CvmDocumento.cd_cvm == UNIPAR, CvmDocumento.dt_refer == date(2026, 6, 30)
            )
        ).one()
    assert doc_depois.recebido_original == doc_antes.recebido_original


def test_mudanca_de_escopo_forca_download_incondicional(
    engine: Engine,
    config: FundamentosConfig,
    servidor: ServidorFalso,
    b3: B3Falsa,
    tickers: list[str],
) -> None:
    with engine.begin() as conn:
        conn.execute(delete(DailyBar).where(DailyBar.ticker == "CRSM3"))
    _rodar(engine, config)
    chamadas_antes = len(servidor.chamadas)

    # O emissor novo aparece no banco: o escopo muda, e o proximo download do
    # zip do ITR tem de ser incondicional (sem etag), mesmo sem `forcar`.
    with engine.begin() as conn:
        conn.execute(
            insert(DailyBar).values(
                ticker="CRSM3", trade_date=date(2026, 1, 2), close=10, volume_financial=1
            )
        )
    servidor.chamadas.clear()
    _rodar(engine, config)

    chamada_itr = [c for c in servidor.chamadas if c[0] == carga_mod._url_zip("ITR", 2026)]
    assert chamada_itr, "o zip do ITR 2026 tem de ser consultado de novo"
    sem_etag = "sem etag: o escopo mudou, o download tem de ser incondicional"
    assert chamada_itr[0][1] is None, sem_etag
    assert chamadas_antes > 0


def test_b3_fora_do_ar_nao_grava_cache_negativo(
    engine: Engine,
    config: FundamentosConfig,
    servidor: ServidorFalso,
    b3: B3Falsa,
    tickers: list[str],
) -> None:
    """Se a B3 cai no meio, o ticker fica pendente -- nao vira "nao existe".

    Gravar cache negativo aqui esconderia a empresa por uma semana por causa
    de uma indisponibilidade de minutos.
    """
    b3.fora_do_ar = True

    relatorio = _rodar(engine, config)

    assert any("B3 fora do ar" in aviso for aviso in relatorio.avisos)
    # As tres do FCA entraram; a da B3 nao, e sem cache negativo.
    assert repository.contagem_do_mapeamento(engine) == (3, 0)
    with engine.connect() as conn:
        linha = conn.execute(select(EmpresaTicker).where(EmpresaTicker.ticker == "CRSM3")).first()
    assert linha is None

    b3.fora_do_ar = False
    _rodar(engine, config)
    assert repository.contagem_do_mapeamento(engine) == (4, 0)


def test_busca_da_b3_recusa_empresa_homonima(
    engine: Engine,
    config: FundamentosConfig,
    servidor: ServidorFalso,
    b3: B3Falsa,
    tickers: list[str],
) -> None:
    """A guarda do EMBR3: candidato sem o ticker nos codigos dele nao vale."""
    _rodar(engine, config)

    empresa = repository.empresa_do_ticker(engine, "CRSM3")
    assert empresa is not None
    assert empresa["cd_cvm"] == INDIVIDUAL
    assert empresa["fonte"] == "b3"
    # A homonima nao esta no cadastro da CVM: barrada antes mesmo do detalhe.
    assert HOMONIMA not in b3.detalhes
    # A Armac esta no cadastro, foi consultada, e caiu porque CRSM3 nao esta
    # entre os codigos dela -- e a segunda guarda fazendo o trabalho.
    assert b3.detalhes == [ARMAC, INDIVIDUAL]


def test_ticker_sem_empresa_vira_cache_negativo_e_nao_repete_a_busca(
    engine: Engine,
    config: FundamentosConfig,
    servidor: ServidorFalso,
    b3: B3Falsa,
    tickers: list[str],
) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(DailyBar).values(
                ticker="XPTO11", trade_date=date(2026, 1, 2), close=10, volume_financial=1
            )
        )
    try:
        _rodar(engine, config)
        assert "XPTO11" in b3.buscas
        assert repository.tickers_sem_empresa(engine) == ["XPTO11"]

        b3.buscas.clear()
        _rodar(engine, config)
        assert b3.buscas == [], "cache negativo tem de evitar a busca de novo"

        # Passada a validade, procura de novo -- o FCA e semanal e pode mudar.
        depois = AGORA + timedelta(days=config.dias_para_rechecar_ticker + 1)
        _rodar(engine, config, agora=depois)
        assert b3.buscas == ["XPTO11"]
    finally:
        with engine.begin() as conn:
            conn.execute(delete(EmpresaTicker).where(EmpresaTicker.ticker == "XPTO11"))
            conn.execute(delete(DailyBar).where(DailyBar.ticker == "XPTO11"))


def test_fca_mais_novo_vence_entre_anos(
    engine: Engine,
    config: FundamentosConfig,
    servidor: ServidorFalso,
    b3: B3Falsa,
    tickers: list[str],
) -> None:
    """UNIP6 aparece no FCA de 2025 e no de 2026; vale o mais novo."""
    _rodar(engine, config)

    with engine.connect() as conn:
        linha = conn.execute(
            select(EmpresaTicker.cd_cvm, EmpresaTicker.fonte).where(EmpresaTicker.ticker == "UNIP6")
        ).one()
    assert (linha.cd_cvm, linha.fonte) == (UNIPAR, "fca")


def test_falha_num_arquivo_nao_impede_os_outros(
    engine: Engine,
    config: FundamentosConfig,
    servidor: ServidorFalso,
    b3: B3Falsa,
    tickers: list[str],
) -> None:
    servidor.falhando.add(carga_mod._url_zip("DFP", 2025))

    relatorio = _rodar(engine, config)

    assert relatorio.teve_falha
    assert any("DFP 2025" in falha for falha in relatorio.falhas)
    # O ITR 2026 tem de ter sido processado normalmente, apesar da falha do DFP.
    assert any("ITR 2026" in linha and "atualizado" in linha for linha in relatorio.arquivos)
    with engine.connect() as conn:
        doc_unipar_itr = conn.execute(
            select(CvmDocumento).where(
                CvmDocumento.cd_cvm == UNIPAR,
                CvmDocumento.tipo == "ITR",
                CvmDocumento.dt_refer == date(2026, 6, 30),
            )
        ).first()
    assert doc_unipar_itr is not None


def test_cascade_apaga_filhas_ao_reprocessar(
    engine: Engine,
    config: FundamentosConfig,
    servidor: ServidorFalso,
    b3: B3Falsa,
    tickers: list[str],
) -> None:
    _rodar(engine, config)
    with engine.connect() as conn:
        resultados_antes = conn.execute(
            select(CvmResultado).where(CvmResultado.cd_cvm == UNIPAR)
        ).all()
    assert resultados_antes

    url_itr_2026 = carga_mod._url_zip("ITR", 2026)
    with engine.begin() as conn:
        conn.execute(delete(ArquivoExterno).where(ArquivoExterno.url == url_itr_2026))
    servidor.bump(url_itr_2026)
    _rodar(engine, config)

    with engine.connect() as conn:
        ainda_la = conn.execute(
            select(CvmDocumento).where(
                CvmDocumento.cd_cvm == UNIPAR,
                CvmDocumento.tipo == "ITR",
                CvmDocumento.dt_refer == date(2026, 6, 30),
            )
        ).first()
    assert ainda_la is not None
