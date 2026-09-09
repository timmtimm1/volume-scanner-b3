"""Modelo de dados: as tabelas batem com a secao 8 do plano."""

from __future__ import annotations

import pytest
from sqlalchemy import Table, UniqueConstraint

from scanner.storage.models import SCHEMA, Base


def table(name: str) -> Table:
    """A Table do metadata, ja qualificada pelo schema do projeto."""
    return Base.metadata.tables[f"{SCHEMA}.{name}"]


def test_todas_as_tabelas_no_schema_do_projeto() -> None:
    assert {t.schema for t in Base.metadata.tables.values()} == {SCHEMA}


def test_nomes_das_tabelas() -> None:
    # Duas tabelas nao estao na secao 8 do plano, e as duas tem motivo escrito:
    #
    # `daily_features` (migration 0002) existe para a tela mostrar contexto
    # abaixo do limiar de alerta, onde `events` nao tem linha.
    #
    # `price_alerts` (migration 0003) e a unica que guarda decisao do usuario e
    # nao dado derivado do COTAHIST: o nivel de preco que ele pediu para vigiar.
    assert {t.name for t in Base.metadata.tables.values()} == {
        "daily_bars",
        "volume_metrics",
        "events",
        "daily_features",
        "price_alerts",
    }


def test_contexto_e_por_papel_e_pregao_nao_por_janela() -> None:
    # As features da secao 3.2 nao dependem de janela, diferente das metricas:
    # uma linha por (papel, pregao) e o suficiente.
    assert [c.name for c in table("daily_features").primary_key] == [
        "ticker",
        "trade_date",
    ]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("daily_bars", ["ticker", "trade_date"]),
        ("volume_metrics", ["ticker", "trade_date", "window_size"]),
        ("events", ["id"]),
    ],
)
def test_chaves_primarias(name: str, expected: list[str]) -> None:
    assert [c.name for c in table(name).primary_key] == expected


def test_dedupe_de_evento_por_ticker_e_data() -> None:
    unicos = {
        tuple(sorted(c.name for c in con.columns))
        for con in table("events").constraints
        if isinstance(con, UniqueConstraint)
    }
    assert ("ticker", "trade_date") in unicos


def test_colunas_obrigatorias_de_daily_bars() -> None:
    cols = table("daily_bars").columns
    assert cols["close"].nullable is False
    assert cols["volume_financial"].nullable is False
    assert cols["trades_censored"].nullable is False
    # Dia sem negociacao e ausencia de linha, nunca zero: o OHLC e opcional.
    assert cols["open"].nullable is True


def test_janela_por_metrica_e_parte_da_chave() -> None:
    # Uma linha por (ticker, pregao, janela): 30, 45 e 60 convivem.
    assert "window_size" in {c.name for c in table("volume_metrics").primary_key}
