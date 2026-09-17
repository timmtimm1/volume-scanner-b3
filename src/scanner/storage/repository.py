"""Escrita e leitura das barras diarias.

A carga e idempotente: `ON CONFLICT (ticker, trade_date) DO UPDATE`. Recarregar
o mesmo arquivo reescreve os mesmos valores e nao duplica nada. `ingested_at`
NAO e tocado no conflito, para que rodar duas vezes deixe o banco identico.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, NamedTuple

import pandas as pd
from sqlalchemy import Connection, Engine, delete, func, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert

from scanner.features import FEATURE_COLUMNS
from scanner.fundamentos.cvm import Extracao
from scanner.ingest.cotahist import BAR_COLUMNS
from scanner.rompimentos import DIRECOES, Alerta, Direcao
from scanner.storage.models import (
    SCHEMA,
    ArquivoExterno,
    CvmBalanco,
    CvmDocumento,
    CvmResultado,
    DailyBar,
    DailyFeature,
    DigestSend,
    Empresa,
    EmpresaTicker,
    Event,
    FundamentoTrimestre,
    PriceAlert,
    Trade,
    TradeOperacao,
    TradeSnapshot,
    VolumeMetric,
)
from scanner.storage.models import (
    Provento as ProventoModel,
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


def digest_enviado(engine: Engine, trade_date: date) -> bool:
    """Se o resumo deste pregao ja saiu alguma vez."""
    stmt = select(DigestSend.trade_date).where(DigestSend.trade_date == trade_date)
    with engine.connect() as conn:
        return conn.execute(stmt).first() is not None


def marcar_digest_enviado(engine: Engine, trade_date: date) -> bool:
    """Carimba o resumo do pregao como enviado. Devolve se esta chamada carimbou.

    `ON CONFLICT DO NOTHING` em vez de deixar estourar: se duas passadas se
    sobrepuserem, a segunda descobre que perdeu a corrida em vez de derrubar o
    pipeline inteiro por causa do resumo, que e a ultima etapa.

    O `RETURNING` nao e enfeite: num INSERT com ON CONFLICT DO NOTHING o driver
    devolve `rowcount == -1` mesmo quando a linha entrou, e "carimbou?" viraria
    sempre False. Com RETURNING, linha de volta significa insercao e nenhuma
    linha significa conflito -- que e exatamente a pergunta.
    """
    stmt = (
        insert(DigestSend)
        .values(trade_date=trade_date)
        .on_conflict_do_nothing()
        .returning(DigestSend.trade_date)
    )
    with engine.begin() as conn:
        return conn.execute(stmt).first() is not None


def events_for_date(engine: Engine, trade_date: date) -> pd.DataFrame:
    """Todos os eventos de um pregao, notificados ou nao."""
    stmt = select(Event).where(Event.trade_date == trade_date).order_by(Event.max_z_log.desc())
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


class Poda(NamedTuple):
    """Linhas removidas por tabela numa poda."""

    barras: int
    metricas: int
    contexto: int


def prune_bars(engine: Engine, keep_sessions: int) -> Poda:
    """Descarta barras, metricas e contexto anteriores aos ultimos N pregoes.

    A secao 5 do plano diz que o banco hospedado guarda os ultimos 400 pregoes
    de barras e a tabela de eventos. Eventos NAO sao apagados: a ficha do papel
    marca eventos antigos mesmo quando as barras daquele periodo ja sairam, e o
    evento guarda o proprio contexto em `events.features`.

    `daily_features` entrou depois desta funcao existir e ficou de fora da poda:
    crescia sem limite e virou a maior tabela do banco. Agora sai junto, com o
    mesmo corte -- contexto de um pregao cujas barras e metricas ja sairam nao
    aparece em tela nenhuma.
    """
    if keep_sessions < 1:
        raise ValueError("keep_sessions precisa ser ao menos 1")

    corte = retention_cutoff(engine, keep_sessions)
    if corte is None:
        return Poda(0, 0, 0)  # ainda ha menos pregoes do que a retencao pede

    with engine.begin() as conn:
        metricas = conn.execute(
            delete(VolumeMetric).where(VolumeMetric.trade_date < corte)
        ).rowcount
        contexto = conn.execute(
            delete(DailyFeature).where(DailyFeature.trade_date < corte)
        ).rowcount
        barras = conn.execute(delete(DailyBar).where(DailyBar.trade_date < corte)).rowcount
    return Poda(int(barras), int(metricas), int(contexto))


def retention_cutoff(engine: Engine, keep_sessions: int) -> date | None:
    """Primeiro pregao que a retencao mantem, ou None se ainda nao ha o bastante."""
    if keep_sessions < 1:
        raise ValueError("keep_sessions precisa ser ao menos 1")
    with engine.connect() as conn:
        return conn.execute(
            select(DailyBar.trade_date)
            .distinct()
            .order_by(DailyBar.trade_date.desc())
            .limit(1)
            .offset(keep_sessions - 1)
        ).scalar_one_or_none()


def tamanho_do_banco(engine: Engine) -> tuple[int, dict[str, int]]:
    """Bytes do banco inteiro e de cada tabela do projeto, maior primeiro.

    O plano gratuito do Neon tem 0,5 GB. Sem este numero no log de cada pregao,
    a unica forma de saber quanto sobra e abrir o painel -- e ninguem abre ate
    a carga falhar por falta de espaco.
    """
    with engine.connect() as conn:
        total = int(conn.execute(text("SELECT pg_database_size(current_database())")).scalar_one())
        linhas = conn.execute(
            text(
                "SELECT c.relname, pg_total_relation_size(c.oid) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relkind = 'r' "
                "ORDER BY 2 DESC"
            ),
            {"schema": SCHEMA},
        ).all()
    return total, {str(nome): int(tamanho) for nome, tamanho in linhas}


def mb(bytes_: int) -> str:
    """Bytes em MB inteiros, para log."""
    return f"{bytes_ / 1_048_576:,.0f} MB"


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


# --- Trades e marcacao a mercado ---------------------------------------------
#
# `trade_snapshots` fica fora da poda de `prune_bars`: e a razao dela existir.
# As barras que sustentam o fechamento de um trade antigo podem ja ter sido
# descartadas -- o snapshot e o que sobrevive.


def trades_para_marcar(engine: Engine) -> pd.DataFrame:
    """Todos os trades, com o ultimo pregao ja marcado a mercado (se houver).

    LEFT JOIN com o maior `trade_date` de `trade_snapshots` por trade: um trade
    sem snapshot nenhum ainda volta com `ultimo_snapshot` nulo, e a funcao pura
    de `trades.py` marca desde `aberto_em`.
    """
    ultimo = (
        select(
            TradeSnapshot.trade_id,
            func.max(TradeSnapshot.trade_date).label("ultimo_snapshot"),
        )
        .group_by(TradeSnapshot.trade_id)
        .subquery()
    )
    stmt = select(
        Trade.id,
        Trade.ticker,
        Trade.aberto_em,
        Trade.encerrado_em,
        ultimo.c.ultimo_snapshot,
    ).outerjoin(ultimo, ultimo.c.trade_id == Trade.id)
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def operacoes_dos_trades(engine: Engine, trade_ids: Sequence[int]) -> pd.DataFrame:
    """Todas as operacoes dos trades pedidos, na forma que a marcacao a mercado le."""
    colunas = (
        "id",
        "trade_id",
        "data",
        "quantidade_apos",
        "preco_medio_apos",
        "custo_comprado_apos",
        "realizado_apos",
    )
    if not trade_ids:
        return pd.DataFrame(columns=list(colunas))

    stmt = select(
        TradeOperacao.id,
        TradeOperacao.trade_id,
        TradeOperacao.data,
        TradeOperacao.quantidade_apos,
        TradeOperacao.preco_medio_apos,
        TradeOperacao.custo_comprado_apos,
        TradeOperacao.realizado_apos,
    ).where(TradeOperacao.trade_id.in_(list(trade_ids)))
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


_SNAPSHOT_ATUALIZAVEIS = (
    "quantidade",
    "preco_medio",
    "custo_comprado",
    "realizado",
    "fechamento",
    "valor_posicao",
    "resultado",
    "sem_negocio",
)


def trades_do_pregao(engine: Engine, dia: date) -> pd.DataFrame:
    """Posicao dos trades no pregao, para o bloco "Seus trades" do resumo.

    Uma linha por trade que tem snapshot neste `dia` e ainda "fala" dele: esta
    aberto, ou foi encerrado exatamente neste pregao. Encerrado antes do dia ja
    saiu do resumo -- o trade nao diz mais respeito a este pregao. Trade sem
    snapshot no dia (a marcacao noturna ainda nao rodou, por exemplo) tambem
    fica de fora: nao ha posicao para mostrar.

    Ordem: abertos primeiro, depois os encerrados neste dia -- cada grupo por
    ticker. E a mesma ordem em que `format_resumo` monta o bloco.
    """
    # IS NOT NULL e nao `encerrado_em = dia`: a comparacao da NULL para trade
    # aberto, e NULL virando NaN no pandas seria True no astype(bool). Com o
    # filtro abaixo, "tem data de encerramento" ja significa "encerrou hoje".
    encerrado = Trade.encerrado_em.is_not(None).label("encerrado")
    stmt = (
        select(
            Trade.ticker,
            TradeSnapshot.quantidade,
            TradeSnapshot.resultado,
            TradeSnapshot.custo_comprado,
            encerrado,
        )
        .join(TradeSnapshot, TradeSnapshot.trade_id == Trade.id)
        .where(TradeSnapshot.trade_date == dia)
        .where((Trade.encerrado_em.is_(None)) | (Trade.encerrado_em == dia))
        # Aberto (encerrado_em nulo) primeiro: `IS NULL` como True vem antes ao
        # ordenar decrescente. Dentro de cada grupo, por ticker.
        .order_by(Trade.encerrado_em.is_(None).desc(), Trade.ticker)
    )
    with engine.connect() as conn:
        frame = pd.read_sql(stmt, conn)

    frame["quantidade"] = frame["quantidade"].astype("int64")
    frame["resultado"] = pd.to_numeric(frame["resultado"], errors="coerce").astype(float)
    frame["custo_comprado"] = pd.to_numeric(frame["custo_comprado"], errors="coerce").astype(float)
    frame["encerrado"] = frame["encerrado"].astype(bool)
    return frame


def gravar_snapshots(engine: Engine, frame: pd.DataFrame) -> int:
    """Upsert dos snapshots por (trade_id, trade_date). Devolve linhas enviadas.

    Idempotente como o resto da carga: rodar a marcacao duas vezes para o mesmo
    pregao reescreve os mesmos valores em vez de duplicar linha.
    """
    if frame.empty:
        return 0

    linhas = frame.loc[:, ["trade_id", "trade_date", *_SNAPSHOT_ATUALIZAVEIS]].copy()
    linhas["trade_id"] = linhas["trade_id"].astype("int64")
    linhas["trade_date"] = pd.to_datetime(linhas["trade_date"]).dt.date
    rows = _to_rows(linhas)

    statement = insert(TradeSnapshot)
    statement = statement.on_conflict_do_update(
        index_elements=["trade_id", "trade_date"],
        set_={name: statement.excluded[name] for name in _SNAPSHOT_ATUALIZAVEIS},
    )
    with engine.begin() as conn:
        conn.execute(statement, rows)
    return len(rows)


# --- Fundamentos (fundamentos fase 1) ----------------------------------------
#
# Nenhuma destas tabelas entra em `prune_bars`: fundamentos nao tem relacao
# com a retencao de 400 pregoes de barras.

_EMPRESA_ATUALIZAVEIS = ("cnpj", "nome", "nome_comercial", "setor_cvm", "situacao")


def _registros_sql(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Registros para INSERT, com NaN/NaT/`pd.NA` virando None (NULL de verdade).

    `_to_rows` (usado pelas barras) nao faz essa conversao porque o DataFrame
    de barras nunca tem essas colunas ausentes; os campos de fundamentos sao
    naturalmente cheios de NULL (conta que a empresa nao reporta), e um
    `float('nan')` mandado para uma coluna NUMERIC nao vira NULL, vira o valor
    especial NaN do Postgres -- errado aqui.
    """
    limpo = frame.astype(object).where(pd.notna(frame), None)
    return [{str(k): v for k, v in row.items()} for row in limpo.to_dict(orient="records")]


def tickers_do_banco(engine: Engine) -> set[str]:
    """Todo ticker que ja apareceu em `daily_bars`."""
    with engine.connect() as conn:
        return {str(t) for t in conn.execute(select(DailyBar.ticker).distinct()).scalars()}


def tickers_pendentes(engine: Engine, tickers: set[str], corte: datetime) -> set[str]:
    """Tickers que ainda precisam ser procurados: sem empresa, ou procurados ha muito.

    Quem ja tem empresa nao e procurado de novo. Quem tem cache negativo
    (`cd_cvm` nulo) espera ate `corte` para uma nova tentativa -- o FCA e
    semanal, e um ETF nunca vai ter empresa nenhuma.
    """
    stmt = select(EmpresaTicker.ticker, EmpresaTicker.cd_cvm, EmpresaTicker.verificado_em)
    with engine.connect() as conn:
        linhas = conn.execute(stmt).all()

    resolvidos = {str(t) for t, cd, _ in linhas if cd is not None}
    recentes = {str(t) for t, cd, quando in linhas if cd is None and quando > corte}
    return tickers - resolvidos - recentes


def contagem_do_mapeamento(engine: Engine) -> tuple[int, int]:
    """Quantos tickers tem empresa ligada e quantos ficaram sem."""
    stmt = select(
        func.count().filter(EmpresaTicker.cd_cvm.is_not(None)),
        func.count().filter(EmpresaTicker.cd_cvm.is_(None)),
    )
    with engine.connect() as conn:
        ligados, sem = conn.execute(stmt).one()
    return int(ligados), int(sem)


def tickers_sem_empresa(engine: Engine) -> list[str]:
    """Os tickers ja procurados que nao tem empresa na CVM (ETF, por exemplo)."""
    stmt = (
        select(EmpresaTicker.ticker)
        .where(EmpresaTicker.cd_cvm.is_(None))
        .order_by(EmpresaTicker.ticker)
    )
    with engine.connect() as conn:
        return [str(t) for t in conn.execute(stmt).scalars()]


def cd_cvms_mapeados(engine: Engine) -> set[int]:
    """CD_CVM de toda empresa alcancada por algum ticker do banco."""
    stmt = select(EmpresaTicker.cd_cvm).where(EmpresaTicker.cd_cvm.is_not(None)).distinct()
    with engine.connect() as conn:
        return {int(c) for c in conn.execute(stmt).scalars() if c is not None}


def upsert_empresas(engine: Engine, frame: pd.DataFrame) -> int:
    """Grava empresas, atualizando `atualizado_em` so em quem foi de fato tocado.

    Nunca apaga: uma empresa que saiu do cadastro continua ligada aos papeis
    que ja tinha, e os balancos dela seguem no banco.
    """
    if frame.empty:
        return 0
    rows = _registros_sql(frame.loc[:, ["cd_cvm", *_EMPRESA_ATUALIZAVEIS]])
    statement = insert(Empresa)
    statement = statement.on_conflict_do_update(
        index_elements=["cd_cvm"],
        set_={
            **{name: statement.excluded[name] for name in _EMPRESA_ATUALIZAVEIS},
            "atualizado_em": func.now(),
        },
    )
    with engine.begin() as conn:
        conn.execute(statement, rows)
    return len(rows)


def upsert_empresa_tickers(
    engine: Engine,
    ligacoes: dict[str, int],
    pela_b3: Iterable[str],
    sem_empresa: Sequence[str],
    verificado_em: datetime,
) -> int:
    """Grava a ligacao ticker -> empresa, incluindo o cache negativo.

    `sem_empresa` sao os tickers procurados sem sucesso: gravam `cd_cvm` nulo
    para nao serem procurados de novo amanha. Quem nao foi procurado (porque a
    B3 caiu no meio) nao entra aqui, e fica pendente para a proxima passada.
    """
    da_b3 = set(pela_b3)
    rows: list[dict[str, Any]] = [
        {
            "ticker": ticker,
            "cd_cvm": cd_cvm,
            "fonte": "b3" if ticker in da_b3 else "fca",
            "verificado_em": verificado_em,
        }
        for ticker, cd_cvm in sorted(ligacoes.items())
    ]
    rows.extend(
        {"ticker": ticker, "cd_cvm": None, "fonte": None, "verificado_em": verificado_em}
        for ticker in sem_empresa
    )
    if not rows:
        return 0

    statement = insert(EmpresaTicker)
    statement = statement.on_conflict_do_update(
        index_elements=["ticker"],
        set_={
            "cd_cvm": statement.excluded.cd_cvm,
            "fonte": statement.excluded.fonte,
            "verificado_em": statement.excluded.verificado_em,
        },
    )
    with engine.begin() as conn:
        conn.execute(statement, rows)
    return len(rows)


# --- Proventos (fundamentos fase 2) ------------------------------------------


def empresas_para_consultar(engine: Engine, campo: str, corte: datetime) -> list[dict[str, Any]]:
    """Empresas cuja consulta `campo` nunca foi feita ou ja passou da validade.

    `campo` e uma das colunas de carimbo: `detalhe_em`, `proventos_em` ou
    `historico_em`. Sem isso, cada execucao repetiria as tres perguntas para
    todas as empresas ligadas.
    """
    coluna = getattr(Empresa, campo)
    stmt = (
        select(Empresa.cd_cvm, Empresa.nome, Empresa.emissor_b3, Empresa.nome_pregao)
        .where((coluna.is_(None)) | (coluna < corte))
        .order_by(Empresa.cd_cvm)
    )
    with engine.connect() as conn:
        return [linha._asdict() for linha in conn.execute(stmt)]


def marcar_consulta(engine: Engine, cd_cvm: int, campo: str, momento: datetime) -> None:
    """Carimba que a consulta `campo` foi feita agora para esta empresa."""
    stmt = update(Empresa).where(Empresa.cd_cvm == cd_cvm).values({campo: momento})
    with engine.begin() as conn:
        conn.execute(stmt)


def gravar_detalhe_b3(
    engine: Engine,
    cd_cvm: int,
    *,
    emissor: str | None,
    nome_pregao: str | None,
    papeis: Mapping[str, tuple[str, str | None]],
    momento: datetime,
) -> int:
    """Guarda como a B3 chama a empresa e o ISIN/classe de cada papel dela.

    `papeis` e {ticker: (isin, classe)}. So toca em ticker que ja esta ligado a
    ESTA empresa: a B3 lista papeis que podem nem estar no nosso banco, e um
    ticker de outra empresa jamais e reescrito aqui.
    """
    with engine.begin() as conn:
        conn.execute(
            update(Empresa)
            .where(Empresa.cd_cvm == cd_cvm)
            .values(emissor_b3=emissor, nome_pregao=nome_pregao, detalhe_em=momento)
        )
        tocados = 0
        for ticker, (isin, classe) in papeis.items():
            resultado = conn.execute(
                update(EmpresaTicker)
                .where(EmpresaTicker.ticker == ticker, EmpresaTicker.cd_cvm == cd_cvm)
                .values(isin=isin, classe=classe)
            )
            tocados += resultado.rowcount
    return tocados


def papeis_da_empresa(engine: Engine, cd_cvm: int) -> list[dict[str, Any]]:
    """Os papeis ligados a empresa, com ISIN e classe quando ja conhecidos."""
    stmt = (
        select(EmpresaTicker.ticker, EmpresaTicker.isin, EmpresaTicker.classe)
        .where(EmpresaTicker.cd_cvm == cd_cvm)
        .order_by(EmpresaTicker.ticker)
    )
    with engine.connect() as conn:
        return [linha._asdict() for linha in conn.execute(stmt)]


def fechamentos_dos_papeis(
    engine: Engine, tickers: Sequence[str], datas: Sequence[date]
) -> dict[tuple[str, date], Decimal]:
    """Fechamentos do COTAHIST para conferir os precos que a B3 informa."""
    if not tickers or not datas:
        return {}
    stmt = select(DailyBar.ticker, DailyBar.trade_date, DailyBar.close).where(
        DailyBar.ticker.in_(list(tickers)), DailyBar.trade_date.in_(list(datas))
    )
    with engine.connect() as conn:
        return {(str(t), d): Decimal(str(c)) for t, d, c in conn.execute(stmt)}


def gravar_proventos(
    engine: Engine,
    linhas: Sequence[Mapping[str, Any]],
    *,
    tickers: Sequence[str],
    fonte: str,
    desde: date | None,
    ate: date | None,
) -> int:
    """Troca a janela de datas inteira destes papeis por `linhas`.

    Nao ha upsert linha a linha porque nao existe chave unica: um provento pago
    em parcelas aparece uma vez por parcela, com a mesma data com e o mesmo
    valor. Apagar a janela que a B3 acabou de responder e gravar o que veio e o
    que mantem a carga idempotente sem inventar chave.
    """
    if not tickers:
        return 0

    alvo = delete(ProventoModel).where(
        ProventoModel.ticker.in_(list(tickers)), ProventoModel.fonte == fonte
    )
    if desde is not None:
        alvo = alvo.where(ProventoModel.data_com >= desde)
    if ate is not None:
        alvo = alvo.where(ProventoModel.data_com < ate)

    with engine.begin() as conn:
        conn.execute(alvo)
        if linhas:
            conn.execute(insert(ProventoModel), [dict(linha) for linha in linhas])
    return len(linhas)


def primeiro_provento_recente(engine: Engine, tickers: Sequence[str]) -> date | None:
    """A data com mais antiga que a consulta dos recentes cobre nestes papeis.

    E a fronteira entre as duas consultas: dali para tras vale o historico,
    dali para frente vale o que veio com ISIN, que identifica o papel sem
    depender de nome nenhum.
    """
    if not tickers:
        return None
    stmt = select(func.min(ProventoModel.data_com)).where(
        ProventoModel.ticker.in_(list(tickers)), ProventoModel.fonte == "recente"
    )
    with engine.connect() as conn:
        return conn.execute(stmt).scalar_one()


def proventos_recentes_dos_papeis(
    engine: Engine, tickers: Sequence[str]
) -> list[tuple[str, date, Decimal]]:
    """Os proventos ja identificados pelo ISIN, para conferir o historico."""
    if not tickers:
        return []
    stmt = select(ProventoModel.ticker, ProventoModel.data_com, ProventoModel.valor).where(
        ProventoModel.ticker.in_(list(tickers)), ProventoModel.fonte == "recente"
    )
    with engine.connect() as conn:
        return [(str(t), d, Decimal(str(v))) for t, d, v in conn.execute(stmt)]


def contar_proventos(engine: Engine) -> tuple[int, int]:
    """Quantos proventos estao guardados, e de quantos papeis."""
    stmt = select(func.count(), func.count(func.distinct(ProventoModel.ticker)))
    with engine.connect() as conn:
        total, papeis = conn.execute(stmt).one()
    return int(total), int(papeis)


def proventos_do_papel(engine: Engine, ticker: str, limite: int = 12) -> pd.DataFrame:
    """Os proventos mais recentes de um papel -- ferramenta de conferencia."""
    stmt = (
        select(
            ProventoModel.data_com,
            ProventoModel.tipo,
            ProventoModel.valor,
            ProventoModel.data_pagamento,
            ProventoModel.fonte,
        )
        .where(ProventoModel.ticker == ticker.upper())
        .order_by(ProventoModel.data_com.desc())
        .limit(limite)
    )
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


# --- Trimestres calculados (fundamentos fase 3) ------------------------------


def dado_bruto_da_cvm(engine: Engine) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Resultados, balancos e documentos, inteiros, para o recalculo."""
    resultados = select(CvmResultado)
    balancos = select(CvmBalanco)
    documentos = select(
        CvmDocumento.cd_cvm,
        CvmDocumento.tipo,
        CvmDocumento.dt_refer,
        CvmDocumento.recebido_original.label("publicado_em"),
        CvmDocumento.layout,
    )
    with engine.connect() as conn:
        return (
            pd.read_sql(resultados, conn),
            pd.read_sql(balancos, conn),
            pd.read_sql(documentos, conn),
        )


def gravar_trimestres(engine: Engine, frame: pd.DataFrame) -> int:
    """Troca a tabela de trimestres pela recem-calculada.

    A tabela e derivada: apagar e regravar e mais simples e mais seguro do que
    casar linha a linha, e sao poucos milhares de linhas. Se um documento for
    reapresentado e mudar de numero, o trimestre acompanha sem sobra.
    """
    if frame.empty:
        return 0
    linhas = _registros_sql(frame)
    with engine.begin() as conn:
        conn.execute(delete(FundamentoTrimestre))
        conn.execute(insert(FundamentoTrimestre), linhas)
    return len(linhas)


def contar_trimestres(engine: Engine) -> tuple[int, int]:
    """Quantos trimestres estao calculados, e de quantas empresas."""
    stmt = select(func.count(), func.count(func.distinct(FundamentoTrimestre.cd_cvm)))
    with engine.connect() as conn:
        total, empresas = conn.execute(stmt).one()
    return int(total), int(empresas)


def trimestres_do_ticker(engine: Engine, ticker: str, limite: int = 8) -> pd.DataFrame:
    """Os ultimos trimestres da empresa do papel, do mais novo para o mais antigo."""
    stmt = (
        select(FundamentoTrimestre)
        .join(EmpresaTicker, EmpresaTicker.cd_cvm == FundamentoTrimestre.cd_cvm)
        .where(EmpresaTicker.ticker == ticker.upper())
        .order_by(FundamentoTrimestre.dt_fim.desc())
        .limit(limite)
    )
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def buscar_arquivo_externo(engine: Engine, url: str) -> dict[str, Any] | None:
    """O estado salvo do controle de download condicional de `url`, se existir."""
    stmt = select(
        ArquivoExterno.etag,
        ArquivoExterno.last_modified,
        ArquivoExterno.modificado_em,
        ArquivoExterno.escopo_hash,
        ArquivoExterno.processado_em,
    ).where(ArquivoExterno.url == url)
    with engine.connect() as conn:
        linha = conn.execute(stmt).first()
    return None if linha is None else linha._asdict()


def marcar_arquivo_verificado(engine: Engine, url: str, verificado_em: datetime) -> None:
    """304: nada mudou. So registra que a checagem aconteceu agora."""
    statement = insert(ArquivoExterno).values(url=url, verificado_em=verificado_em)
    statement = statement.on_conflict_do_update(
        index_elements=["url"], set_={"verificado_em": statement.excluded.verificado_em}
    )
    with engine.begin() as conn:
        conn.execute(statement)


def registrar_arquivo_externo(
    engine: Engine,
    url: str,
    *,
    etag: str | None,
    last_modified: str | None,
    modificado_em: datetime | None,
    escopo_hash: str,
    verificado_em: datetime,
) -> None:
    """Upsert de `arquivos_externos` fora de uma transacao maior (ex.: o cadastro da CVM)."""
    with engine.begin() as conn:
        _upsert_arquivo_externo(
            conn,
            url=url,
            etag=etag,
            last_modified=last_modified,
            modificado_em=modificado_em,
            escopo_hash=escopo_hash,
            verificado_em=verificado_em,
        )


def _upsert_arquivo_externo(
    conn: Connection,
    *,
    url: str,
    etag: str | None,
    last_modified: str | None,
    modificado_em: datetime | None,
    escopo_hash: str,
    verificado_em: datetime,
) -> None:
    statement = insert(ArquivoExterno).values(
        url=url,
        etag=etag,
        last_modified=last_modified,
        modificado_em=modificado_em,
        escopo_hash=escopo_hash,
        verificado_em=verificado_em,
        processado_em=verificado_em,
    )
    statement = statement.on_conflict_do_update(
        index_elements=["url"],
        set_={
            "etag": statement.excluded.etag,
            "last_modified": statement.excluded.last_modified,
            "modificado_em": statement.excluded.modificado_em,
            "escopo_hash": statement.excluded.escopo_hash,
            "verificado_em": statement.excluded.verificado_em,
            "processado_em": statement.excluded.processado_em,
        },
    )
    conn.execute(statement)


class RelatorioGravacao(NamedTuple):
    """O que aconteceu ao gravar um arquivo da CVM."""

    documentos: int
    novos: int
    com_nova_versao: int


def gravar_arquivo_cvm(
    engine: Engine,
    extracao: Extracao,
    *,
    url: str,
    etag: str | None,
    last_modified: str | None,
    modificado_em: datetime | None,
    escopo_hash: str,
    verificado_em: datetime,
) -> RelatorioGravacao:
    """Grava uma extracao inteira e atualiza `arquivos_externos`, numa transacao so.

    Apaga os documentos (cd_cvm, tipo, dt_refer) presentes na extracao -- as
    linhas de `cvm_resultados`/`cvm_balancos` caem juntas por CASCADE -- e
    insere tudo de novo. `recebido_original` de um documento que ja existia
    vira o menor entre o valor anterior e o novo: a reapresentacao troca os
    numeros, mas nao muda quando o mercado soube pela primeira vez.
    """
    documentos = extracao.documentos.copy()
    if documentos.empty:
        with engine.begin() as conn:
            _upsert_arquivo_externo(
                conn,
                url=url,
                etag=etag,
                last_modified=last_modified,
                modificado_em=modificado_em,
                escopo_hash=escopo_hash,
                verificado_em=verificado_em,
            )
        return RelatorioGravacao(0, 0, 0)

    chaves = list(documentos[["cd_cvm", "tipo", "dt_refer"]].itertuples(index=False, name=None))
    chave_composta = tuple_(CvmDocumento.cd_cvm, CvmDocumento.tipo, CvmDocumento.dt_refer)

    with engine.begin() as conn:
        anteriores = pd.read_sql(
            select(
                CvmDocumento.cd_cvm,
                CvmDocumento.tipo,
                CvmDocumento.dt_refer,
                CvmDocumento.versao,
                CvmDocumento.recebido_original,
            ).where(chave_composta.in_(chaves)),
            conn,
        )
        renomeadas = {
            "versao": "versao_anterior",
            "recebido_original": "recebido_original_anterior",
        }
        documentos = documentos.merge(
            anteriores.rename(columns=renomeadas),
            on=["cd_cvm", "tipo", "dt_refer"],
            how="left",
        )
        novos = int(documentos["versao_anterior"].isna().sum())
        # fillna(-1) antes de comparar: comparar contra pd.NA direto emite
        # RuntimeWarning e obriga a lidar com dtype nullable no resultado.
        com_nova_versao = int(
            (documentos["versao"] > documentos["versao_anterior"].fillna(-1)).sum()
        )

        minimo = pd.concat(
            [
                pd.to_datetime(documentos["recebido_original"]),
                pd.to_datetime(documentos["recebido_original_anterior"]),
            ],
            axis=1,
        ).min(axis=1)
        documentos["recebido_original"] = minimo.dt.date
        documentos = documentos.drop(columns=["versao_anterior", "recebido_original_anterior"])

        conn.execute(delete(CvmDocumento).where(chave_composta.in_(chaves)))
        conn.execute(insert(CvmDocumento), _registros_sql(documentos))
        if not extracao.resultados.empty:
            conn.execute(insert(CvmResultado), _registros_sql(extracao.resultados))
        if not extracao.balancos.empty:
            conn.execute(insert(CvmBalanco), _registros_sql(extracao.balancos))

        _upsert_arquivo_externo(
            conn,
            url=url,
            etag=etag,
            last_modified=last_modified,
            modificado_em=modificado_em,
            escopo_hash=escopo_hash,
            verificado_em=verificado_em,
        )

    return RelatorioGravacao(len(documentos), novos, com_nova_versao)


def contar_empresas(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(Empresa)).scalar_one())


def documentos_por_tipo_e_ano(engine: Engine) -> pd.DataFrame:
    """Quantos documentos existem, por tipo e ano de `dt_refer`."""
    stmt = select(
        CvmDocumento.tipo,
        func.extract("year", CvmDocumento.dt_refer).label("ano"),
        func.count().label("total"),
    ).group_by(CvmDocumento.tipo, text("ano"))
    with engine.connect() as conn:
        frame = pd.read_sql(stmt, conn)
    frame["ano"] = frame["ano"].astype(int)
    return frame.sort_values(["tipo", "ano"]).reset_index(drop=True)


def datas_dos_arquivos_externos(engine: Engine) -> pd.DataFrame:
    """`modificado_em` de cada arquivo controlado -- "data dos dados da CVM"."""
    stmt = select(ArquivoExterno.url, ArquivoExterno.modificado_em, ArquivoExterno.processado_em)
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def empresa_do_ticker(engine: Engine, ticker: str) -> dict[str, Any] | None:
    """A empresa ligada ao ticker em `empresa_tickers`.

    Nunca por prefixo: a ligacao e a que a carga gravou, vinda do FCA da CVM
    ou de uma busca conferida na B3.
    """
    stmt = (
        select(
            Empresa.cd_cvm,
            Empresa.cnpj,
            Empresa.nome,
            Empresa.nome_comercial,
            Empresa.setor_cvm,
            Empresa.situacao,
            EmpresaTicker.fonte,
        )
        .join(EmpresaTicker, EmpresaTicker.cd_cvm == Empresa.cd_cvm)
        .where(EmpresaTicker.ticker == ticker.upper())
    )
    with engine.connect() as conn:
        linha = conn.execute(stmt).first()
    return None if linha is None else linha._asdict()


def ultimos_documentos_da_empresa(engine: Engine, cd_cvm: int, limite: int = 4) -> pd.DataFrame:
    """Os `limite` documentos mais recentes de uma empresa, com data de referencia."""
    stmt = (
        select(
            CvmDocumento.tipo,
            CvmDocumento.dt_refer,
            CvmDocumento.versao,
            CvmDocumento.recebido_original,
            CvmDocumento.recebido_ultima,
            CvmDocumento.escopo,
            CvmDocumento.layout,
        )
        .where(CvmDocumento.cd_cvm == cd_cvm)
        .order_by(CvmDocumento.dt_refer.desc())
        .limit(limite)
    )
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def resultados_da_empresa(engine: Engine, cd_cvm: int, tipo: str, dt_refer: date) -> pd.DataFrame:
    """Todas as linhas de `cvm_resultados` (tri e acumulado) de um documento."""
    stmt = (
        select(CvmResultado)
        .where(
            CvmResultado.cd_cvm == cd_cvm,
            CvmResultado.tipo == tipo,
            CvmResultado.dt_refer == dt_refer,
        )
        .order_by(CvmResultado.dt_fim.desc())
    )
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def balanco_da_empresa(engine: Engine, cd_cvm: int, tipo: str, dt_refer: date) -> pd.DataFrame:
    """A linha de `cvm_balancos` de um documento."""
    stmt = select(CvmBalanco).where(
        CvmBalanco.cd_cvm == cd_cvm, CvmBalanco.tipo == tipo, CvmBalanco.dt_refer == dt_refer
    )
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)
