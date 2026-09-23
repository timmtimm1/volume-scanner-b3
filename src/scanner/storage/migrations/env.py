"""Ambiente Alembic. A URL do banco vem de SCANNER_DATABASE_URL, nunca do .ini."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from scanner.storage.engine import database_url
from scanner.storage.models import SCHEMA, Base

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False` e o padrao do `fileConfig` invertido de
    # proposito. Com o padrao (True), carregar a configuracao de log do
    # alembic.ini DESLIGA todo logger que ja exista -- inclusive os `scanner.*`.
    # Em producao cada comando roda no proprio processo e isso nunca aparecia;
    # na suite de testes, qualquer teste de banco (que migra) apagava o log de
    # todos os que rodassem depois. E o log e o unico lugar onde a cota da brapi
    # aparece antes de a checagem terminar.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Respeita uma URL ja definida pelo chamador (os testes apontam para o banco
# isolado); so cai no ambiente quando ninguem definiu nada.
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option("sqlalchemy.url", database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Gera SQL sem conectar."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        version_table_schema=SCHEMA,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica as migrations no banco configurado."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # A tabela de versao do Alembic tambem mora no schema do projeto.
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema=SCHEMA,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
