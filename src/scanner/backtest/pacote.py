"""A rodada num arquivo so, para subir sem os trades (secao 14 do plano).

A suite roda na maquina do usuario e o endereco do banco de producao vive so
nos segredos do GitHub. O pacote e o que `enviar` precisa -- a grade, a escolha,
o ano a ano, a curva, a amostra de trades e o resumo da rodada -- em JSON
compactado, sem os milhoes de trades. O workflow `backtest-enviar` baixa o
pacote e grava a rodada no banco (11/11/2026).

JSON e nao pickle de proposito: o arquivo sai da maquina e e lido no CI, e
pickle executa codigo ao abrir. As tabelas voltam com os valores como estao no
arquivo (texto fica texto: o setup "9.1" nao pode virar numero); so as colunas
de data sao convertidas.
"""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

TABELAS = ("grade", "escolha", "anos", "curva", "amostra")
# Colunas de data de cada tabela: o resto volta como veio do JSON.
DATAS = {"curva": ("mes",), "amostra": ("data_sinal", "data_entrada", "data_saida")}


def gravar_pacote(caminho: Path, *, rodada: dict[str, Any], **tabelas: pd.DataFrame) -> None:
    """Grava a rodada em `caminho` (.json.gz). `tabelas`: as cinco de `TABELAS`."""
    faltam = set(TABELAS) - set(tabelas)
    if faltam:
        raise ValueError(f"faltam tabelas no pacote: {sorted(faltam)}")
    corpo: dict[str, Any] = {
        "rodada": {k: v.isoformat() if isinstance(v, date) else v for k, v in rodada.items()},
    }
    for nome in TABELAS:
        corpo[nome] = json.loads(
            tabelas[nome].to_json(orient="split", date_format="iso", double_precision=15)
        )
    with gzip.open(caminho, "wt", encoding="utf-8") as f:
        json.dump(corpo, f)


def ler_pacote(caminho: Path) -> dict[str, Any]:
    """O que `enviar` recebe: `rodada` e as cinco tabelas."""
    with gzip.open(caminho, "rt", encoding="utf-8") as f:
        corpo = json.load(f)
    rodada = dict(corpo["rodada"])
    for campo in ("dados_de", "dados_ate"):
        rodada[campo] = date.fromisoformat(rodada[campo])
    saida: dict[str, Any] = {"rodada": rodada}
    for nome in TABELAS:
        t = corpo[nome]
        frame = pd.DataFrame(t["data"], columns=t["columns"]).astype(object)
        for coluna in DATAS.get(nome, ()):
            frame[coluna] = pd.to_datetime(frame[coluna]).dt.tz_localize(None)
        saida[nome] = frame
    return saida
