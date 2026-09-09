"""Escrita e leitura das barras diarias.

A carga e idempotente: `ON CONFLICT (ticker, trade_date) DO UPDATE`. Recarregar
o mesmo arquivo reescreve os mesmos valores e nao duplica nada. `ingested_at`
NAO e tocado no conflito, para que rodar duas vezes deixe o banco identico.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from scanner.features import FEATURE_COLUMNS
from scanner.ingest.cotahist import BAR_COLUMNS
from scanner.rompimentos import DIRECOES, Alerta, Direcao
from scanner.storage.models import (
    SCHEMA,
    DailyBar,
    DailyFeature,
    Event,
    PriceAlert,
    VolumeMetric,
)

# Colunas reescritas quando a linha ja existe. `ingested_at` fica de fora.
_UPDATABLE = tuple(c for c in BAR_COLUMNS if c not in ("ticker", "trade_date"))


def _to_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame para lista de dicionarios, no formato que o INSERT espera."""
    return [{str(k): v for k, v in row.items()} for row in frame.to_dict(orient="records")]


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Converte o DataFrame para linhas prontas para o INSERT."""
    prepared = frame.loc[:, list(BAR_COLUMNS)].copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"]).dt.date
    prepared["volume_shares"] = prepared["volume_shares"].astype("int64")
    prepared["trades_count"] = prepared["trades_count"].astype("int64")
    prepared["trades_censored"] = prepared["trades_censored"].astype(bool)
    return _to_rows(prepared)


def upsert_bars(engine: Engine, frame: pd.DataFrame, *, chunk_size: int = 5_000) -> int:
    """Grava as barras, sobrescrevendo as que ja existirem. Devolve linhas enviadas."""
    if frame.empty:
        return 0

    rows = _records(frame)
    statement = insert(DailyBar)
    statement = statement.on_conflict_do_update(
        index_elements=["ticker", "trade_date"],
        set_={name: statement.excluded[name] for name in _UPDATABLE},
    )

    with engine.begin() as conn:
        for start in range(0, len(rows), chunk_size):
            conn.execute(statement, rows[start : start + chunk_size])
    return len(rows)


def count_bars(engine: Engine) -> int:
    """Total de barras armazenadas."""
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(DailyBar)).scalar_one())


def stored_range(engine: Engine) -> tuple[date | None, date | None]:
    """Primeiro e ultimo pregao presentes no banco."""
    with engine.connect() as conn:
        row = conn.execute(
            select(func.min(DailyBar.trade_date), func.max(DailyBar.trade_date))
        ).one()
    return row[0], row[1]


def sessions_stored(engine: Engine) -> int:
    """Quantidade de pregoes distintos no banco."""
    with engine.connect() as conn:
        return int(
            conn.execute(select(func.count(func.distinct(DailyBar.trade_date)))).scalar_one()
        )


def load_bars(engine: Engine, *, since: date | None = None) -> pd.DataFrame:
    """Barras completas para o calculo, em formato longo.

    O calculo precisa do historico inteiro mesmo em modo incremental: sem os N
    pregoes anteriores nao ha baseline.
    """
    stmt = select(
        DailyBar.ticker,
        DailyBar.trade_date,
        DailyBar.open,
        DailyBar.high,
        DailyBar.low,
        DailyBar.close,
        DailyBar.avg_price,
        DailyBar.volume_shares,
        DailyBar.volume_financial,
        DailyBar.trades_count,
        DailyBar.trades_censored,
    )
    if since is not None:
        stmt = stmt.where(DailyBar.trade_date >= since)

    with engine.connect() as conn:
        frame = pd.read_sql(stmt, conn)

    for column in ("open", "high", "low", "close", "avg_price", "volume_financial"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
    return frame


def upsert_metrics(engine: Engine, metrics: pd.DataFrame, *, replace_all: bool = False) -> int:
    """Grava os z-scores.

    O payload vai por COPY em bloco unico: `write_row` linha a linha custava
    dezenas de segundos para meio milhao de linhas, e o recalculo full tem de
    caber em 60s.

    `replace_all` troca a tabela inteira -- e o que o modo full faz, e evita
    meio milhao de ON CONFLICT contra linhas que serao todas sobrescritas.
    """
    if metrics.empty:
        return 0

    prepared = metrics.loc[
        :, ["ticker", "trade_date", "window_size", "z_log", "z_raw", "z_robust", "rvol"]
    ].copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"]).dt.date
    prepared["window_size"] = prepared["window_size"].astype("int64")

    payload = io.StringIO()
    # Formato TEXT do COPY: separador tab e \N para nulo.
    prepared.to_csv(payload, sep="\t", header=False, index=False, na_rep="\\N")

    colunas = "ticker, trade_date, window_size, z_log, z_raw, z_robust, rvol"
    atualizaveis = ("z_log", "z_raw", "z_robust", "rvol")
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in atualizaveis)

    with engine.begin() as conn:
        raw = conn.connection.driver_connection
        with raw.cursor() as cur:  # type: ignore[union-attr]
            if replace_all:
                cur.execute(f"TRUNCATE {SCHEMA}.volume_metrics")
                destino = f"{SCHEMA}.volume_metrics"
            else:
                cur.execute(
                    f"CREATE TEMP TABLE tmp_metrics "
                    f"(LIKE {SCHEMA}.volume_metrics INCLUDING DEFAULTS) ON COMMIT DROP"
                )
                destino = "tmp_metrics"

            with cur.copy(f"COPY {destino} ({colunas}) FROM STDIN") as copy:
                copy.write(payload.getvalue())

            if not replace_all:
                cur.execute(
                    f"INSERT INTO {SCHEMA}.volume_metrics ({colunas}) "
                    f"SELECT {colunas} FROM tmp_metrics "
                    f"ON CONFLICT (ticker, trade_date, window_size) DO UPDATE SET {set_clause}"
                )
    return len(prepared)


def count_metrics(engine: Engine) -> int:
    """Total de linhas de metrica armazenadas."""
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(VolumeMetric)).scalar_one())


def last_metric_date(engine: Engine) -> date | None:
    """Ultimo pregao com metrica calculada."""
    with engine.connect() as conn:
        return conn.execute(select(func.max(VolumeMetric.trade_date))).scalar_one()


def insert_events(engine: Engine, events: pd.DataFrame) -> int:
    """Grava eventos novos. Devolve quantos de fato entraram.

    `ON CONFLICT DO NOTHING` sobre (ticker, trade_date) e o dedupe da secao 4:
    rodar o scan de novo nao cria evento repetido nem reabre a notificacao.
    """
    if events.empty:
        return 0

    linhas: list[dict[str, Any]] = []
    for _, evento in events.iterrows():
        linhas.append(
            {
                "ticker": str(evento["ticker"]),
                "trade_date": pd.Timestamp(evento["trade_date"]).date(),
                "max_z_log": float(evento["max_z_log"]),
                "triggered_windows": [int(w) for w in evento["triggered_windows"]],
                "volume_financial": float(evento["volume_financial"]),
                "features": evento["features"],
            }
        )

    # RETURNING porque `rowcount` devolve -1 em executemany com DO NOTHING:
    # so as linhas de fato inseridas voltam, e e isso que se quer contar.
    statement = (
        insert(Event)
        .on_conflict_do_nothing(index_elements=["ticker", "trade_date"])
        .returning(Event.id)
    )
    with engine.begin() as conn:
        return len(conn.execute(statement, linhas).fetchall())


def pending_events(engine: Engine, trade_date: date) -> pd.DataFrame:
    """Eventos do pregao ainda nao notificados, do maior z para o menor."""
    stmt = (
        select(
            Event.id,
            Event.ticker,
            Event.trade_date,
            Event.max_z_log,
            Event.triggered_windows,
            Event.volume_financial,
            Event.features,
        )
        .where(Event.trade_date == trade_date)
        .where(Event.notified_at.is_(None))
        .order_by(Event.max_z_log.desc())
    )
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def mark_notified(engine: Engine, event_ids: Sequence[int]) -> int:
    """Carimba os eventos como notificados."""
    if not event_ids:
        return 0
    with engine.begin() as conn:
        resultado = conn.execute(
            update(Event).where(Event.id.in_(list(event_ids))).values(notified_at=func.now())
        )
        return int(resultado.rowcount)


def events_for_date(engine: Engine, trade_date: date) -> pd.DataFrame:
    """Todos os eventos de um pregao, notificados ou nao."""
    stmt = select(Event).where(Event.trade_date == trade_date).order_by(Event.max_z_log.desc())
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def prune_bars(engine: Engine, keep_sessions: int) -> tuple[int, int]:
    """Descarta barras e metricas anteriores aos ultimos N pregoes.

    A secao 5 do plano diz que o banco hospedado guarda os ultimos 400 pregoes
    de barras e a tabela de eventos. Eventos NAO sao apagados: a ficha do papel
    marca eventos antigos mesmo quando as barras daquele periodo ja sairam.

    Devolve (barras removidas, metricas removidas).
    """
    if keep_sessions < 1:
        raise ValueError("keep_sessions precisa ser ao menos 1")

    with engine.connect() as conn:
        corte = conn.execute(
            select(DailyBar.trade_date)
            .distinct()
            .order_by(DailyBar.trade_date.desc())
            .limit(1)
            .offset(keep_sessions - 1)
        ).scalar_one_or_none()

    if corte is None:
        return 0, 0  # ainda ha menos pregoes do que a retencao pede

    with engine.begin() as conn:
        metricas = conn.execute(
            delete(VolumeMetric).where(VolumeMetric.trade_date < corte)
        ).rowcount
        barras = conn.execute(delete(DailyBar).where(DailyBar.trade_date < corte)).rowcount
    return int(barras), int(metricas)


def retention_cutoff(engine: Engine, keep_sessions: int) -> date | None:
    """Primeiro pregao que a retencao mantem, ou None se ainda nao ha o bastante."""
    with engine.connect() as conn:
        return conn.execute(
            select(DailyBar.trade_date)
            .distinct()
            .order_by(DailyBar.trade_date.desc())
            .limit(1)
            .offset(keep_sessions - 1)
        ).scalar_one_or_none()


def upsert_features(engine: Engine, features: pd.DataFrame) -> int:
    """Grava o contexto da secao 3.2 de cada (papel, pregao).

    Vai por COPY numa temporaria, como as metricas: sao ~300 linhas por pregao,
    mas um recalculo full traz centenas de milhares de uma vez.

    Linhas sem nenhuma feature calculada nao entram: papel novo demais para ter
    qualquer janela ainda nao tem contexto, e uma linha de nulos so ocuparia
    espaco.
    """
    if features.empty:
        return 0

    colunas_de_feature = [c for c in FEATURE_COLUMNS if c in features.columns]
    prontas = features.loc[:, ["ticker", "trade_date", *colunas_de_feature]].copy()
    prontas["trade_date"] = pd.to_datetime(prontas["trade_date"]).dt.date

    valores = prontas[colunas_de_feature]
    prontas = prontas[valores.notna().any(axis=1)]
    if prontas.empty:
        return 0

    def como_json(linha: pd.Series) -> str:
        corpo = {
            nome: (None if pd.isna(linha[nome]) else float(linha[nome]))
            for nome in colunas_de_feature
        }
        return json.dumps(corpo, allow_nan=False)

    payload = io.StringIO()
    pd.DataFrame(
        {
            "ticker": prontas["ticker"],
            "trade_date": prontas["trade_date"],
            "features": prontas.apply(como_json, axis=1),
        }
    ).to_csv(payload, sep="\t", header=False, index=False, quoting=csv.QUOTE_NONE, escapechar="\\")

    with engine.begin() as conn:
        raw = conn.connection.driver_connection
        with raw.cursor() as cur:  # type: ignore[union-attr]
            cur.execute(
                f"CREATE TEMP TABLE tmp_features "
                f"(LIKE {SCHEMA}.daily_features INCLUDING DEFAULTS) ON COMMIT DROP"
            )
            with cur.copy("COPY tmp_features (ticker, trade_date, features) FROM STDIN") as copy:
                copy.write(payload.getvalue())
            cur.execute(
                f"INSERT INTO {SCHEMA}.daily_features (ticker, trade_date, features) "
                f"SELECT ticker, trade_date, features FROM tmp_features "
                f"ON CONFLICT (ticker, trade_date) DO UPDATE SET features = EXCLUDED.features"
            )
    return len(prontas)


def count_features(engine: Engine) -> int:
    """Total de linhas de contexto armazenadas."""
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(DailyFeature)).scalar_one())


# --- Alertas de rompimento ---------------------------------------------------
#
# Os unicos dados do sistema que nao vem do COTAHIST: o usuario escolhe o nivel
# e o sistema vigia. Por isso ficam fora do ciclo de retencao -- podar barras
# antigas nunca pode apagar um alerta que o usuario ainda espera.


# Colunas do alerta, na ordem em que `_para_alerta` as le. Selecionar colunas em
# vez da entidade mantem estas funcoes no mesmo estilo Core do resto do arquivo
# -- `select(PriceAlert)` numa Connection devolveria a primeira coluna, nao o
# objeto, e a leitura passaria a exigir uma Session so aqui.
_ALERTA_COLUNAS = (
    PriceAlert.id,
    PriceAlert.ticker,
    PriceAlert.trade_date,
    PriceAlert.preco,
    PriceAlert.direcao,
    PriceAlert.criado_em,
    PriceAlert.disparado_em,
    PriceAlert.preco_disparo,
    PriceAlert.fonte_disparo,
)


def _para_alerta(linha: Any) -> Alerta:
    """Linha do banco para o dataclass que o resto do sistema usa."""
    direcao: Direcao = "acima" if linha.direcao == "acima" else "abaixo"
    return Alerta(
        id=int(linha.id),
        ticker=str(linha.ticker),
        trade_date=linha.trade_date,
        preco=linha.preco,
        direcao=direcao,
        criado_em=linha.criado_em,
        disparado_em=linha.disparado_em,
        preco_disparo=linha.preco_disparo,
        fonte_disparo=linha.fonte_disparo,
    )


def criar_alerta(
    engine: Engine, ticker: str, trade_date: date, preco: Decimal, direcao: str
) -> int:
    """Grava um alerta novo e devolve o id.

    Nao ha dedupe: dois alertas iguais no mesmo papel sao permitidos de
    proposito. Impedir isso exigiria decidir o que conta como "igual" (mesmo
    centavo? faixa de 1%?), e errar essa regra silenciaria um alerta legitimo.
    """
    if direcao not in DIRECOES:
        raise ValueError(f"direcao invalida: {direcao!r}")
    statement = (
        insert(PriceAlert)
        .values(
            ticker=ticker.upper(),
            trade_date=trade_date,
            preco=preco,
            direcao=direcao,
        )
        .returning(PriceAlert.id)
    )
    with engine.begin() as conn:
        return int(conn.execute(statement).scalar_one())


def alertas_ativos(engine: Engine) -> list[Alerta]:
    """Os que ainda nao dispararam -- o que o job de 15 minutos consulta."""
    stmt = select(*_ALERTA_COLUNAS).where(PriceAlert.disparado_em.is_(None))
    with engine.connect() as conn:
        return [_para_alerta(linha) for linha in conn.execute(stmt)]


def listar_alertas(engine: Engine, ticker: str | None = None) -> list[Alerta]:
    """Todos os alertas, ativos e disparados. Ativos primeiro, mais novos antes."""
    stmt = select(*_ALERTA_COLUNAS)
    if ticker is not None:
        stmt = stmt.where(PriceAlert.ticker == ticker.upper())
    stmt = stmt.order_by(
        PriceAlert.disparado_em.is_(None).desc(),
        PriceAlert.criado_em.desc(),
    )
    with engine.connect() as conn:
        return [_para_alerta(linha) for linha in conn.execute(stmt)]


def marcar_disparado(engine: Engine, alerta_id: int, *, preco: Decimal, fonte: str) -> bool:
    """Desativa o alerta, guardando a cotacao que o disparou.

    `disparado_em IS NULL` na clausula: se duas passadas se sobrepuserem, a
    segunda nao remarca nem reenvia. Devolve se esta chamada foi a que disparou.
    """
    stmt = (
        update(PriceAlert)
        .where(PriceAlert.id == alerta_id, PriceAlert.disparado_em.is_(None))
        .values(disparado_em=func.now(), preco_disparo=preco, fonte_disparo=fonte)
    )
    with engine.begin() as conn:
        return conn.execute(stmt).rowcount > 0


def reativar_alerta(engine: Engine, alerta_id: int) -> bool:
    """Religa um alerta que ja disparou, limpando o registro do disparo."""
    stmt = (
        update(PriceAlert)
        .where(PriceAlert.id == alerta_id)
        .values(disparado_em=None, preco_disparo=None, fonte_disparo=None)
    )
    with engine.begin() as conn:
        return conn.execute(stmt).rowcount > 0


def apagar_alerta(engine: Engine, alerta_id: int) -> bool:
    """Remove o alerta de vez."""
    with engine.begin() as conn:
        return conn.execute(delete(PriceAlert).where(PriceAlert.id == alerta_id)).rowcount > 0
