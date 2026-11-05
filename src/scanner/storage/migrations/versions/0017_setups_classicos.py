"""Setups classicos no pregao diario e a preferencia de cada setup (secao 14).

Decisoes de 05/11/2026:

- `setups.categoria` ganha os setups classicos (9.1 a 9.4, 123, PFR, MMA 20,
  pullback), ao lado de reversao, media e forca;
- `setups.saida_regra`: a saida que o setup segue depois de confirmado, uma das
  cinco da suite de backtest. Gravada na noite em que o setup arma (congelada,
  como o resto da linha). NULL = a regra antiga (fecha abaixo da minima ou 20
  pregoes), so dos setups gravados antes desta migration;
- `setups.estado` ganha os fins das saidas novas: `alvo`, `movel` (stop movel)
  e `mme9`. `stop` e `prazo` continuam (o teto de 60 pregoes e `prazo`);
- `setups.alta`: a etiqueta de tendencia (acima da MMA 200 subindo). NULL nas
  linhas antigas;
- `setup_preferencias`: o que o usuario escolheu no app para cada setup --
  alerta ligado ou nao e a saida. Sem linha, vale o padrao do `config.yaml`.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "volume_scanner"
CATEGORIAS = (
    "'reversao', 'forca', 'media', '9.1', '9.2', '9.3', '9.4', '123', 'pfr', 'mma20', 'pullback'"
)
SAIDAS = "'alvo1', 'alvo2', 'alvo3', 'minimas', 'mme9'"
ESTADOS = "'armado', 'confirmado', 'nao_confirmou', 'stop', 'prazo', 'alvo', 'movel', 'mme9'"


def upgrade() -> None:
    op.drop_constraint("ck_setups_categoria", "setups", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_setups_categoria", "setups", f"categoria IN ({CATEGORIAS})", schema=SCHEMA
    )
    op.drop_constraint("ck_setups_estado", "setups", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_setups_estado", "setups", f"estado IN ({ESTADOS})", schema=SCHEMA
    )
    op.add_column("setups", sa.Column("alta", sa.Boolean(), nullable=True), schema=SCHEMA)
    op.add_column("setups", sa.Column("saida_regra", sa.Text(), nullable=True), schema=SCHEMA)
    op.create_check_constraint(
        "ck_setups_saida_regra",
        "setups",
        f"saida_regra IS NULL OR saida_regra IN ({SAIDAS})",
        schema=SCHEMA,
    )
    op.create_table(
        "setup_preferencias",
        sa.Column("categoria", sa.Text(), nullable=False),
        sa.Column("alerta", sa.Boolean(), nullable=False),
        sa.Column("saida", sa.Text(), nullable=False),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("categoria"),
        sa.CheckConstraint(f"categoria IN ({CATEGORIAS})", name="ck_setup_preferencias_categoria"),
        sa.CheckConstraint(f"saida IN ({SAIDAS})", name="ck_setup_preferencias_saida"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("setup_preferencias", schema=SCHEMA)
    op.execute(f"DELETE FROM {SCHEMA}.setups WHERE categoria NOT IN ('reversao', 'forca', 'media')")
    op.execute(
        f"UPDATE {SCHEMA}.setups SET estado = 'stop' WHERE estado IN ('alvo', 'movel', 'mme9')"
    )
    op.drop_constraint("ck_setups_saida_regra", "setups", schema=SCHEMA, type_="check")
    op.drop_column("setups", "saida_regra", schema=SCHEMA)
    op.drop_column("setups", "alta", schema=SCHEMA)
    op.drop_constraint("ck_setups_estado", "setups", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_setups_estado",
        "setups",
        "estado IN ('armado', 'confirmado', 'nao_confirmou', 'stop', 'prazo')",
        schema=SCHEMA,
    )
    op.drop_constraint("ck_setups_categoria", "setups", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_setups_categoria",
        "setups",
        "categoria IN ('reversao', 'forca', 'media')",
        schema=SCHEMA,
    )
