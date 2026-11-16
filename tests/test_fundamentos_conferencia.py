"""A conferencia dos fundamentos: o banco esta em dia com o que a CVM publicou?"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import Engine, delete
from sqlalchemy.dialects.postgresql import insert

from scanner.config import FundamentosConfig
from scanner.fundamentos.carga import url_do_zip
from scanner.fundamentos.conferencia import (
    COBERTURA_MINIMA,
    ArquivoConferido,
    conferir,
    trimestre_esperado,
)
from scanner.fundamentos.cvm import CvmIndisponivelError
from scanner.storage.models import ArquivoExterno, CvmDocumento, Empresa, EmpresaTicker

DOMINGO_08 = datetime(2026, 11, 8, 10, 48, tzinfo=UTC)
DOMINGO_15 = datetime(2026, 11, 15, 10, 48, tzinfo=UTC)


# --- O arquivo: a CVM tem versao mais nova do que a que o banco processou? -----


def test_o_caso_de_15_11_2026_e_atraso() -> None:
    """A CVM republicou no domingo, o banco ficou com a versao do domingo anterior."""
    arquivo = ArquivoConferido("ITR", 2026, na_cvm=DOMINGO_15, no_banco=DOMINGO_08)
    segunda_a_noite = datetime(2026, 11, 17, 0, 31, tzinfo=UTC)
    assert arquivo.atrasado(segunda_a_noite)


def test_mesma_versao_nos_dois_lados_esta_em_dia() -> None:
    arquivo = ArquivoConferido("ITR", 2026, na_cvm=DOMINGO_15, no_banco=DOMINGO_15)
    assert not arquivo.atrasado(DOMINGO_15 + timedelta(days=3))


def test_arquivo_que_a_cvm_ainda_nao_publicou_nao_esta_atrasado() -> None:
    # O DFP do ano corrente so existe depois que a primeira empresa entrega.
    arquivo = ArquivoConferido("DFP", 2026, na_cvm=None, no_banco=None)
    assert not arquivo.atrasado(DOMINGO_15)


def test_arquivo_publicado_que_o_banco_nunca_leu_e_atraso() -> None:
    arquivo = ArquivoConferido("ITR", 2026, na_cvm=DOMINGO_15, no_banco=None)
    assert arquivo.atrasado(DOMINGO_15 + timedelta(days=1))


def test_republicacao_no_meio_da_passada_nao_e_alarme_falso() -> None:
    """A CVM regrava os zips ao longo de uma hora: o que saiu minutos atras ainda e fila."""
    arquivo = ArquivoConferido("ITR", 2022, na_cvm=DOMINGO_15, no_banco=DOMINGO_08)
    assert not arquivo.atrasado(DOMINGO_15 + timedelta(minutes=20))
    assert arquivo.atrasado(DOMINGO_15 + timedelta(hours=2))


# --- O trimestre que ja deveria estar no banco -------------------------------


@pytest.mark.parametrize(
    ("hoje", "dt_refer", "tipo", "anterior"),
    [
        # 3T26: prazo em 14/11; com a folga da publicacao semanal, vale de 23/11.
        (date(2026, 11, 16), date(2026, 6, 30), "ITR", date(2026, 3, 31)),
        (date(2026, 11, 22), date(2026, 6, 30), "ITR", date(2026, 3, 31)),
        (date(2026, 11, 23), date(2026, 9, 30), "ITR", date(2026, 6, 30)),
        # O 4o trimestre e a DFP, com 90 dias: ate la o esperado segue o 3T.
        (date(2027, 2, 15), date(2026, 9, 30), "ITR", date(2026, 6, 30)),
        (date(2027, 4, 9), date(2026, 12, 31), "DFP", date(2026, 9, 30)),
        # 1T27: 31/03 + 45 dias + 9 de folga = 24/05.
        (date(2027, 5, 23), date(2026, 12, 31), "DFP", date(2026, 9, 30)),
        (date(2027, 5, 24), date(2027, 3, 31), "ITR", date(2026, 12, 31)),
    ],
)
def test_trimestre_esperado_segue_o_prazo_legal_mais_a_publicacao(
    hoje: date, dt_refer: date, tipo: str, anterior: date
) -> None:
    esperado = trimestre_esperado(hoje)
    assert (esperado.dt_refer, esperado.tipo, esperado.anterior) == (dt_refer, tipo, anterior)


# --- A conferencia contra o banco ---------------------------------------------

# Um ano so para este teste: nenhum outro grava documento ou arquivo de 2031.
ANO = 2031
# `model_copy` nao valida: o config de verdade recusa ano no futuro.
CONFIG = FundamentosConfig().model_copy(update={"ano_inicial": ANO})
# 3T31: prazo 14/11/2031, esperado a partir de 23/11/2031.
AGORA = datetime(2031, 11, 25, 12, 0, tzinfo=UTC)
PUBLICADO = datetime(2031, 11, 23, 10, 48, tzinfo=UTC)
ANTIGO = datetime(2031, 11, 16, 10, 48, tzinfo=UTC)
EMPRESAS = list(range(990_001, 990_011))  # dez empresas de mentira


def _arquivo(engine: Engine, tipo: str, modificado_em: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(ArquivoExterno).values(
                url=url_do_zip(tipo, ANO),
                etag="x",
                last_modified="x",
                modificado_em=modificado_em,
                escopo_hash="x",
                verificado_em=AGORA,
                processado_em=AGORA,
            )
        )


def _documentos(engine: Engine, dt_refer: date, empresas: list[int]) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(CvmDocumento),
            [
                {
                    "cd_cvm": cd,
                    "tipo": "ITR",
                    "dt_refer": dt_refer,
                    "versao": 1,
                    "recebido_original": dt_refer + timedelta(days=40),
                    "recebido_ultima": dt_refer + timedelta(days=40),
                    "escopo": "con",
                    "layout": "geral",
                }
                for cd in empresas
            ],
        )


@pytest.fixture
def base(engine: Engine) -> Iterator[Engine]:
    """Dez empresas ligadas a ticker, todas com o 2T31 entregue."""

    def limpar() -> None:
        with engine.begin() as conn:
            conn.execute(delete(EmpresaTicker).where(EmpresaTicker.cd_cvm.in_(EMPRESAS)))
            conn.execute(delete(Empresa).where(Empresa.cd_cvm.in_(EMPRESAS)))
            conn.execute(
                delete(ArquivoExterno).where(
                    ArquivoExterno.url.in_([url_do_zip(t, ANO) for t in ("ITR", "DFP")])
                )
            )

    limpar()
    with engine.begin() as conn:
        conn.execute(
            insert(Empresa),
            [{"cd_cvm": cd, "cnpj": f"{cd:014d}", "nome": f"EMPRESA {cd}"} for cd in EMPRESAS],
        )
        conn.execute(
            insert(EmpresaTicker),
            [
                {
                    "ticker": f"ZZ{cd % 1000:03d}3",
                    "cd_cvm": cd,
                    "fonte": "fca",
                    "verificado_em": AGORA,
                }
                for cd in EMPRESAS
            ],
        )
    _documentos(engine, date(ANO, 6, 30), EMPRESAS)
    yield engine
    limpar()


def _cvm(datas: dict[str, datetime | None]) -> object:
    def consultar(url: str) -> datetime | None:
        return datas["ITR" if "/ITR/" in url else "DFP"]

    return consultar


@pytest.mark.db
def test_tudo_em_dia(base: Engine) -> None:
    _arquivo(base, "ITR", PUBLICADO)
    _documentos(base, date(ANO, 9, 30), EMPRESAS[:9])  # 9 de 10: um atrasado e normal
    resultado = conferir(
        base,
        CONFIG,
        agora=AGORA,
        consultar=_cvm({"ITR": PUBLICADO, "DFP": None}),  # type: ignore[arg-type]
    )
    assert resultado.em_dia, resultado.problemas
    assert any("ITR 2031: em dia" in linha for linha in resultado.linhas)
    assert any("DFP 2031: ainda nao publicado" in linha for linha in resultado.linhas)
    assert any("9 de 10 empresas" in linha for linha in resultado.linhas)


@pytest.mark.db
def test_cvm_republicou_e_o_banco_ficou_com_a_versao_anterior(base: Engine) -> None:
    """O incidente de 15/11/2026, visto pela conferencia."""
    _arquivo(base, "ITR", ANTIGO)
    _documentos(base, date(ANO, 9, 30), EMPRESAS[:9])
    resultado = conferir(
        base,
        CONFIG,
        agora=AGORA,
        consultar=_cvm({"ITR": PUBLICADO, "DFP": None}),  # type: ignore[arg-type]
    )
    assert not resultado.em_dia
    assert len(resultado.problemas) == 1
    assert "ITR 2031" in resultado.problemas[0]
    assert "23/11/2031" in resultado.problemas[0] and "16/11/2031" in resultado.problemas[0]


@pytest.mark.db
def test_arquivo_em_dia_mas_o_trimestre_novo_nao_entrou(base: Engine) -> None:
    """Arquivo lido, documentos nao gravados: so a cobertura enxerga (parser, layout novo)."""
    _arquivo(base, "ITR", PUBLICADO)
    _documentos(base, date(ANO, 9, 30), EMPRESAS[:3])  # 30%: muito abaixo do esperado
    resultado = conferir(
        base,
        CONFIG,
        agora=AGORA,
        consultar=_cvm({"ITR": PUBLICADO, "DFP": None}),  # type: ignore[arg-type]
    )
    assert not resultado.em_dia
    assert "3 de 10 empresas" in resultado.problemas[0]
    assert f"{COBERTURA_MINIMA:.0%}" in resultado.problemas[0]


@pytest.mark.db
def test_antes_do_prazo_o_trimestre_novo_ainda_nao_e_cobrado(base: Engine) -> None:
    """Em plena temporada, com poucas entregas, nao ha alarme: o prazo nao venceu."""
    _arquivo(base, "ITR", ANTIGO)
    _documentos(base, date(ANO, 9, 30), EMPRESAS[:2])
    em_temporada = datetime(2031, 11, 10, 12, 0, tzinfo=UTC)
    resultado = conferir(
        base,
        CONFIG,
        agora=em_temporada,
        consultar=_cvm({"ITR": ANTIGO, "DFP": None}),  # type: ignore[arg-type]
    )
    assert resultado.em_dia, resultado.problemas
    assert any("ITR de 30/06/2031" in linha for linha in resultado.linhas)


@pytest.mark.db
def test_cvm_fora_do_ar_nao_vira_atraso_nem_pontualidade(base: Engine) -> None:
    _arquivo(base, "ITR", ANTIGO)
    _documentos(base, date(ANO, 9, 30), EMPRESAS[:9])

    def fora_do_ar(url: str) -> datetime | None:
        raise CvmIndisponivelError(f"{url}: HTTP 503")

    resultado = conferir(base, CONFIG, agora=AGORA, consultar=fora_do_ar)
    assert resultado.em_dia
    assert sum("CVM nao respondeu" in linha for linha in resultado.linhas) == 2
