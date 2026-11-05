"""Suite de backtest dos setups no COTAHIST de 1995 em diante.

Etapa 1 (`processar`): roda todos os setups e todas as saidas em lotes de papeis
e grava os trades (um arquivo por lote, depois um so).

    python scripts/backtest_setups.py processar <barras.pkl> <pasta>

Etapa 2 (`relatorio`): numeros por setup, saida, tendencia e periodo; a escolha
em 1995-2015 e a conferencia em 2016-2026; ano a ano e curva.

    python scripts/backtest_setups.py relatorio <pasta>

`barras.pkl` sai de `scripts/gatilhos_carregar.py`. Lote de papeis pela variavel
BACKTEST_LOTE (padrao 150): o motor de suporte e resistencia e o que mais pesa
na memoria.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from scanner.backtest.metricas import curva, escolher, grade, por_ano
from scanner.backtest.suite import liquidez_historica, rodar_lote
from scanner.config import load_config
from scanner.gatilhos.classicos import NOMES

LOTE = int(os.environ.get("BACKTEST_LOTE", "150"))
SEMENTE = 20261105


def processar(barras_pkl: Path, pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    cfg = load_config(Path(__file__).resolve().parents[1] / "config.yaml").setups
    b = pd.read_pickle(barras_pkl)
    b["ticker"] = b["ticker"].astype(str)
    sessoes = pd.DatetimeIndex(sorted(pd.to_datetime(b["trade_date"].unique())))
    t0 = time.time()
    liq = liquidez_historica(b, sessoes)
    # so entra papel que foi liquido em algum dia; ordem sorteada (fixa) para os
    # lotes misturarem setores e o controle sortear entre papeis variados
    alguma_vez = sorted(liq.columns[liq.to_numpy().any(axis=0)])
    rng = np.random.default_rng(SEMENTE)
    tickers = list(rng.permutation(alguma_vez))
    print(f"{len(tickers)} papeis liquidos em algum dia, {len(sessoes)} pregoes")
    lotes = [tickers[i : i + LOTE] for i in range(0, len(tickers), LOTE)]
    for k, lote in enumerate(lotes):
        destino = pasta / f"trades_{k:03d}.pkl"
        if destino.exists():
            continue
        t1 = time.time()
        parte = b[b["ticker"].isin(lote)]
        trades = rodar_lote(parte, lote, sessoes, liq, cfg, semente=SEMENTE + k)
        trades.to_pickle(destino)
        print(
            f"lote {k + 1}/{len(lotes)}: {len(trades)} trades ({time.time() - t1:.0f}s)", flush=True
        )
    todos = pd.concat(
        [pd.read_pickle(p) for p in sorted(pasta.glob("trades_*.pkl"))], ignore_index=True
    )
    for col in ("setup", "saida", "ticker"):
        todos[col] = todos[col].astype("category")
    todos.to_pickle(pasta / "trades.pkl")
    print(f"total {len(todos)} trades em {time.time() - t0:.0f}s")


def _json(v: object) -> object:
    if isinstance(v, float) and not np.isfinite(v):
        return None
    if isinstance(v, (np.floating, np.integer, np.bool_)):
        return _json(v.item())
    return v


def relatorio(pasta: Path) -> None:
    t0 = time.time()
    trades = pd.read_pickle(pasta / "trades.pkl")
    g = grade(trades)
    e = escolher(g)
    g.to_pickle(pasta / "grade.pkl")
    e.to_pickle(pasta / "escolha.pkl")
    por_ano(trades).to_pickle(pasta / "por_ano.pkl")
    curva(trades).to_pickle(pasta / "curva.pkl")
    escolha = [{k: _json(v) for k, v in linha.items()} for linha in e.to_dict("records")]
    (pasta / "escolha.json").write_text(json.dumps(escolha, ensure_ascii=False, indent=1))
    print(f"grade {len(g)} linhas, {len(trades)} trades ({time.time() - t0:.0f}s)\n")
    nomes = NOMES | {
        "suporte": "Reversao no suporte (regra de hoje)",
        "media": "Na media (regra de hoje)",
        "forca": "Candle de forca (regra de hoje)",
    }
    for linha in escolha:
        s = str(linha["setup"])
        if "saida" not in linha or linha["saida"] is None:
            print(f"{nomes.get(s, s)}: poucos trades para escolher")
            continue
        print(
            f"{'PASSOU' if linha['passou'] else 'falhou'}  {nomes.get(s, s)}:"
            f" {linha['saida']}/{linha['grupo']}"
            f"  escolha {linha['exp_escolha']:+.3f}R (n {linha['n_escolha']},"
            f" contra controle {linha['dif_escolha']:+.3f})"
            f"  conferencia {linha['exp_conferencia']:+.3f}R"
            f" [{linha['ic_conf_baixo']:+.3f}, {linha['ic_conf_alto']:+.3f}]"
            f" (n {linha['n_conferencia']}, contra controle {linha['dif_conferencia']:+.3f})"
        )


def main() -> None:
    etapa = sys.argv[1]
    if etapa == "processar":
        processar(Path(sys.argv[2]), Path(sys.argv[3]))
    elif etapa == "relatorio":
        relatorio(Path(sys.argv[2]))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
