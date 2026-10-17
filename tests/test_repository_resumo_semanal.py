"""Resumo semanal no banco: upsert que nao sobrescreve o que ja foi enviado."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import Engine, delete, text

from scanner.storage.models import SCHEMA, ResumoSemanal
from scanner.storage.repository import gravar_resumo_semanal, resumo_semanal

SEXTA = date(2099, 10, 16)  # data longe de qualquer uso real, para nao colidir
INICIO = date(2099, 10, 9)


@pytest.fixture
def limpo(engine: Engine) -> Engine:
    """O banco de teste persiste entre rodadas: apaga a semana usada aqui."""
    with engine.begin() as conn:
        conn.execute(delete(ResumoSemanal).where(ResumoSemanal.semana == SEXTA))
    return engine


@pytest.mark.db
def test_sem_linha_devolve_none(limpo: Engine) -> None:
    assert resumo_semanal(limpo, SEXTA) is None


@pytest.mark.db
def test_grava_e_le(limpo: Engine) -> None:
    ok = gravar_resumo_semanal(
        limpo, semana=SEXTA, inicio=INICIO, fim=SEXTA, payload={"versao": 1, "x": [1, None]}
    )
    assert ok is True
    assert resumo_semanal(limpo, SEXTA) == {"versao": 1, "x": [1, None]}


@pytest.mark.db
def test_regrava_antes_de_enviado(limpo: Engine) -> None:
    gravar_resumo_semanal(limpo, semana=SEXTA, inicio=INICIO, fim=SEXTA, payload={"v": 1})
    novo_fim = date(2099, 10, 15)
    ok = gravar_resumo_semanal(limpo, semana=SEXTA, inicio=INICIO, fim=novo_fim, payload={"v": 2})

    assert ok is True
    assert resumo_semanal(limpo, SEXTA) == {"v": 2}
    with limpo.connect() as conn:
        fim = conn.execute(
            text(f"SELECT fim FROM {SCHEMA}.resumos_semanais WHERE semana = :s"), {"s": SEXTA}
        ).scalar_one()
    assert fim == novo_fim


@pytest.mark.db
def test_recusa_depois_de_enviado_e_aceita_com_substituir(limpo: Engine) -> None:
    gravar_resumo_semanal(limpo, semana=SEXTA, inicio=INICIO, fim=SEXTA, payload={"v": 1})
    with limpo.begin() as conn:
        conn.execute(
            text(f"UPDATE {SCHEMA}.resumos_semanais SET enviado_em = now() WHERE semana = :s"),
            {"s": SEXTA},
        )

    recusou = gravar_resumo_semanal(limpo, semana=SEXTA, inicio=INICIO, fim=SEXTA, payload={"v": 2})
    assert recusou is False
    assert resumo_semanal(limpo, SEXTA) == {"v": 1}

    ok = gravar_resumo_semanal(
        limpo,
        semana=SEXTA,
        inicio=INICIO,
        fim=SEXTA,
        payload={"v": 3},
        substituir_enviado=True,
    )
    assert ok is True
    assert resumo_semanal(limpo, SEXTA) == {"v": 3}
