"""Modelo de dados (secao 8 do plano).

O schema `volume_scanner` isola as tabelas do projeto do `public` do banco.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "volume_scanner"


class Base(DeclarativeBase):
    """Base declarativa, com todas as tabelas presas ao schema do projeto."""

    metadata = MetaData(schema=SCHEMA)


class DailyBar(Base):
    """Barra diaria de um papel, como veio do COTAHIST.

    Dias sem negociacao nao viram linha com zero: simplesmente nao existem.
    """

    __tablename__ = "daily_bars"
    __table_args__ = (Index("ix_daily_bars_trade_date", "trade_date"),)

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    avg_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    volume_shares: Mapped[int | None] = mapped_column(BigInteger)
    volume_financial: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    trades_count: Mapped[int | None] = mapped_column(Integer)
    # TOTNEG e N(05) e satura em 99999: valor censurado, nao valor real.
    trades_censored: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class VolumeMetric(Base):
    """Z-scores de uma janela para um papel num pregao (secao 3.1)."""

    __tablename__ = "volume_metrics"

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    window_size: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    z_log: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    z_raw: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    z_robust: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    rvol: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))


class Event(Base):
    """Evento que cruzou o limiar. Dedupe por (ticker, trade_date)."""

    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("ticker", "trade_date", name="uq_events_ticker_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    max_z_log: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    triggered_windows: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), nullable=False)
    volume_financial: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    # Todo o contexto da secao 3.2 do plano.
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
