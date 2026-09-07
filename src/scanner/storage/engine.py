"""Engine e sessoes SQLAlchemy."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from scanner.config import get_settings


def database_url() -> str:
    """URL de conexao resolvida do ambiente."""
    return get_settings().database_url.get_secret_value()


def build_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """Cria o Engine. `pool_pre_ping` porque o Neon derruba conexao ociosa."""
    return create_engine(url or database_url(), echo=echo, pool_pre_ping=True, future=True)


def build_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Fabrica de sessoes ligada a um Engine."""
    return sessionmaker(bind=engine or build_engine(), expire_on_commit=False)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Sessao transacional: commit no sucesso, rollback no erro."""
    factory = build_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping(engine: Engine | None = None) -> str:
    """Testa a conexao e devolve a versao do servidor."""
    target = engine or build_engine()
    with target.connect() as conn:
        return str(conn.execute(text("SELECT version()")).scalar_one())
