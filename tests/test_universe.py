"""Universo: cortes de liquidez e de atividade."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import Engine, delete

from scanner.calendar import sessions_before
from scanner.config import UniverseConfig
from scanner.storage.engine import session_scope
from scanner.storage.models import DailyBar
from scanner.universe import (
    compute_liquidity,
    load_universe,
    select_universe,
    tickers,
)

AS_OF = date(2025, 6, 18)
CONFIG = UniverseConfig(
    min_median_volume_brl=500_000, lookback_sessions=60, min_session_coverage=0.8
)


@pytest.fixture
def janela() -> list[date]:
    return sessions_before(AS_OF, CONFIG.lookback_sessions, inclusive=True)


def bars(rows: dict[str, Sequence[tuple[date, float]]]) -> pd.DataFrame:
    """DataFrame long a partir de {ticker: [(pregao, volume), ...]}."""
    registros = [
        {"ticker": ticker, "trade_date": dia, "volume_financial": vol}
        for ticker, pontos in rows.items()
        for dia, vol in pontos
    ]
    return pd.DataFrame(registros, columns=["ticker", "trade_date", "volume_financial"])


def negociou_todos(janela: Sequence[date], volume: float) -> list[tuple[date, float]]:
    return [(dia, volume) for dia in janela]


def test_corte_de_liquidez(janela: list[date]) -> None:
    df = bars(
        {
            "LIQU4": negociou_todos(janela, 1_000_000),
            "ILIQ3": negociou_todos(janela, 100_000),
        }
    )
    assert tickers(select_universe(df, janela, CONFIG)) == ["LIQU4"]


def test_papel_esporadico_com_volume_alto_fica_de_fora(janela: list[date]) -> None:
    # 2 pregoes em 60, mas volumosos: mediana altissima, cobertura de 3%.
    # Sem o corte de atividade, este papel entraria no universo.
    df = bars({"ESPO3": [(janela[0], 50_000_000), (janela[-1], 50_000_000)]})
    stats = compute_liquidity(df, janela)
    assert stats.loc["ESPO3", "median_volume"] == 50_000_000
    assert stats.loc["ESPO3", "sessions_traded"] == 2
    assert select_universe(df, janela, CONFIG).empty


def test_volume_zero_nao_conta_como_pregao_negociado(janela: list[date]) -> None:
    # Volume zero e ausencia de negocio, nao um valor: vira NaN e nao entra na conta.
    df = bars({"ZERO3": negociou_todos(janela, 0.0)})
    stats = compute_liquidity(df, janela)
    assert stats.loc["ZERO3", "sessions_traded"] == 0
    assert pd.isna(stats.loc["ZERO3", "median_volume"])
    assert select_universe(df, janela, CONFIG).empty


def test_cobertura_e_medida_contra_a_janela_nao_contra_o_que_existe(
    janela: list[date],
) -> None:
    metade = janela[: len(janela) // 2]
    df = bars({"MEIO3": negociou_todos(metade, 5_000_000)})
    stats = compute_liquidity(df, janela)
    assert stats.loc["MEIO3", "coverage"] == pytest.approx(0.5)
    assert select_universe(df, janela, CONFIG).empty


def test_barras_fora_da_janela_sao_ignoradas(janela: list[date]) -> None:
    anterior = sessions_before(janela[0], 5)
    df = bars(
        {
            "FORA3": negociou_todos(anterior, 90_000_000) + negociou_todos(janela, 1_000_000),
        }
    )
    stats = compute_liquidity(df, janela)
    assert stats.loc["FORA3", "sessions_traded"] == len(janela)
    assert stats.loc["FORA3", "median_volume"] == 1_000_000


def test_ordenado_do_mais_liquido_para_o_menos(janela: list[date]) -> None:
    df = bars(
        {
            "MEDI3": negociou_todos(janela, 2_000_000),
            "ALTA3": negociou_todos(janela, 9_000_000),
            "BAIX3": negociou_todos(janela, 600_000),
        }
    )
    assert tickers(select_universe(df, janela, CONFIG)) == ["ALTA3", "MEDI3", "BAIX3"]


def test_duplicata_de_ticker_e_data_falha_alto(janela: list[date]) -> None:
    df = bars({"DUPL3": [(janela[0], 1_000_000), (janela[0], 1_000_000)]})
    with pytest.raises(ValueError, match="repetido"):
        compute_liquidity(df, janela)


def test_janela_vazia_devolve_universo_vazio() -> None:
    assert compute_liquidity(bars({}), []).empty


def test_sem_barras_devolve_universo_vazio(janela: list[date]) -> None:
    assert select_universe(bars({}), janela, CONFIG).empty


def test_coluna_faltando_falha_alto(janela: list[date]) -> None:
    df = pd.DataFrame({"ticker": ["X"], "trade_date": [janela[0]]})
    with pytest.raises(ValueError, match="colunas ausentes"):
        compute_liquidity(df, janela)


@pytest.mark.db
def test_load_universe_le_do_banco(engine: Engine, janela: list[date]) -> None:
    linhas = [
        DailyBar(
            ticker=ticker,
            trade_date=dia,
            close=Decimal("10.00"),
            volume_financial=Decimal(volume),
        )
        for ticker, volume in (("DBLQ4", 3_000_000), ("DBIL3", 10_000))
        for dia in janela
    ]
    try:
        with session_scope(engine) as s:
            s.add_all(linhas)

        universo = load_universe(engine, AS_OF, CONFIG)
        # O banco pode ter carga real junto: verifica os dois sinteticos, nao a
        # lista inteira.
        presentes = set(tickers(universo))
        assert "DBLQ4" in presentes
        assert "DBIL3" not in presentes
        assert universo.loc["DBLQ4", "sessions_traded"] == len(janela)
    finally:
        with session_scope(engine) as s:
            s.execute(delete(DailyBar).where(DailyBar.ticker.in_(["DBLQ4", "DBIL3"])))
