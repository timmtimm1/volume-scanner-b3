"""Historico de juros no banco: upsert em lote, idempotente, e leitura ate uma semana."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import Engine, delete, text
from sqlalchemy.exc import IntegrityError

from scanner.storage.models import SCHEMA, JurosHistorico
from scanner.storage.repository import gravar_juros_historico, juros_historico

S1 = date(2099, 10, 8)  # sextas de um ano longe de qualquer uso real
S2 = date(2099, 10, 15)
S3 = date(2099, 10, 22)


def _frame(*linhas: tuple[date, str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"semana": s, "serie": serie, "taxa": t, "data_base": s, "fonte": "tesouro_direto"}
            for s, serie, t in linhas
        ]
    )


@pytest.fixture
def limpo(engine: Engine) -> Engine:
    """O banco de teste persiste entre rodadas: apaga as semanas usadas aqui."""
    with engine.begin() as conn:
        conn.execute(delete(JurosHistorico).where(JurosHistorico.semana >= date(2099, 1, 1)))
    return engine


def _do_teste(engine: Engine, ate: date | None = None) -> pd.DataFrame:
    frame = juros_historico(engine, ate)
    return frame[frame["semana"] >= date(2099, 1, 1)].reset_index(drop=True)


@pytest.mark.db
def test_grava_e_le_em_ordem(limpo: Engine) -> None:
    n = gravar_juros_historico(
        limpo, _frame((S2, "pre_1a", 12.5), (S1, "selic", 14.25), (S1, "pre_1a", 12.0))
    )

    lido = _do_teste(limpo)
    assert n == 3
    assert list(zip(lido["semana"], lido["serie"], strict=True)) == [
        (S1, "pre_1a"),
        (S1, "selic"),
        (S2, "pre_1a"),
    ]
    assert lido["taxa"].tolist() == [12.0, 14.25, 12.5]
    assert set(lido["fonte"]) == {"tesouro_direto"}


@pytest.mark.db
def test_regravar_atualiza_sem_duplicar_e_nao_apaga_o_resto(limpo: Engine) -> None:
    gravar_juros_historico(limpo, _frame((S1, "pre_1a", 12.0), (S2, "pre_1a", 12.5)))
    # A segunda rodada traz so a semana S2 (corrigida) e a nova S3: S1 continua la.
    gravar_juros_historico(limpo, _frame((S2, "pre_1a", 12.75), (S3, "pre_1a", 13.0)))

    lido = _do_teste(limpo)
    assert lido["semana"].tolist() == [S1, S2, S3]
    assert lido["taxa"].tolist() == [12.0, 12.75, 13.0]


@pytest.mark.db
def test_le_so_ate_a_semana_pedida(limpo: Engine) -> None:
    gravar_juros_historico(limpo, _frame((S1, "pre_1a", 12.0), (S2, "pre_1a", 12.5)))

    assert _do_teste(limpo, S1)["semana"].tolist() == [S1]
    assert _do_teste(limpo, date(2099, 10, 7)).empty


@pytest.mark.db
def test_frame_sem_linhas_nao_grava_nada(limpo: Engine) -> None:
    assert gravar_juros_historico(limpo, pd.DataFrame()) == 0


@pytest.mark.db
def test_serie_desconhecida_e_barrada_pelo_banco(limpo: Engine) -> None:
    with pytest.raises(IntegrityError):
        gravar_juros_historico(limpo, _frame((S1, "pre_20a", 12.0)))


@pytest.mark.db
def test_taxa_e_guardada_com_4_casas(limpo: Engine) -> None:
    gravar_juros_historico(limpo, _frame((S1, "pre_1a", 12.123456)))

    with limpo.connect() as conn:
        taxa = conn.execute(
            text(f"SELECT taxa::text FROM {SCHEMA}.juros_historico WHERE semana = :s"), {"s": S1}
        ).scalar_one()
    assert taxa == "12.1235"
