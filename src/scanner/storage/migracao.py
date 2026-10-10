"""Aplicar as migrations so quando ha alguma pendente.

`alembic upgrade head` sem nada a aplicar nao muda o banco, mas custa um
processo inteiro: outro Python, outro import e outra conexao com o Neon. No
pregao isso acontece uma vez por dia e nao importa. Na checagem de rompimentos
acontecia a cada passada -- medido em 25 execucoes de 09/10/2026, 5,3s de
migrations para 4,7s de checagem, num job de 18,2s.

Aqui a pergunta "ha migration pendente?" e uma consulta na conexao que o
comando ja ia abrir. So quando a resposta e sim o Alembic roda de fato.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from scanner.storage.models import SCHEMA

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def _config(engine: Engine) -> Config:
    """As mesmas migrations do `alembic upgrade head`, apontadas para `engine`.

    Sem o alembic.ini de proposito. Dele so interessariam duas coisas: onde
    estao as migrations, que aqui sai do lugar deste arquivo, e o log do
    Alembic, que a checagem nao precisa. Depender do .ini seria depender de o
    comando rodar na raiz do repositorio.

    A URL vai explicita: o `env.py` so cai em `SCANNER_DATABASE_URL` quando
    ninguem definiu nada, e o banco a migrar tem de ser o que foi consultado.
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    # O configparser le "%" como interpolacao; senha com "%" quebraria aqui.
    url = engine.url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", url)
    return config


def revisao_do_banco(engine: Engine) -> str | None:
    """A revisao gravada em `alembic_version`, ou None num banco nunca migrado."""
    with engine.connect() as conn:
        contexto = MigrationContext.configure(conn, opts={"version_table_schema": SCHEMA})
        return contexto.get_current_revision()


def migrar_se_preciso(engine: Engine) -> str | None:
    """Aplica as migrations pendentes. Devolve a revisao nova, ou None se nao havia.

    Com o banco em dia, o custo e uma consulta. O `upgrade` e o mesmo comando
    do passo de migrations do pregao, so que chamado daqui.
    """
    config = _config(engine)
    alvo = ScriptDirectory.from_config(config).get_current_head()
    if alvo is None or revisao_do_banco(engine) == alvo:
        return None
    command.upgrade(config, "head")
    return alvo
