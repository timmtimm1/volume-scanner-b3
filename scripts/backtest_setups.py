"""Suite de backtest dos setups no COTAHIST de 1995 em diante.

Etapa 1 (`processar`): roda todos os setups e todas as saidas em lotes de papeis
e grava os trades (um arquivo por lote, depois um so).

    python scripts/backtest_setups.py processar <barras.pkl> <pasta>

Etapa 2 (`relatorio`): numeros por setup, saida, tendencia e periodo; a escolha
em 1995-2015 e a conferencia em 2016-2026; ano a ano e curva.

    python scripts/backtest_setups.py relatorio <pasta>

Etapa 3 (`enviar`): grava o resultado no banco de SCANNER_DATABASE_URL, numa
rodada nova (o site mostra a mais recente; ficam as duas ultimas).

    python scripts/backtest_setups.py enviar <pasta>

Para a producao, sem o endereco do banco na maquina: `empacotar` grava a rodada
num arquivo so (`<pasta>/rodada.json.gz`, sem os trades) e o workflow
`backtest-enviar` do GitHub faz o envio com ele (ver README).

    python scripts/backtest_setups.py empacotar <pasta>
    python scripts/backtest_setups.py enviar <pasta>/rodada.json.gz

`barras.pkl` sai de `scripts/gatilhos_carregar.py`. Lote de papeis pela variavel
BACKTEST_LOTE (padrao 150): o motor de suporte e resistencia e o que mais pesa
na memoria.

Estudo de uma regra (variantes): BACKTEST_SO=9.1,9.2 limita aos setups pedidos;
BACKTEST_TENDENCIA_9X=MMA80, MME80 ou nenhuma troca o filtro de tendencia dos
9.x; BACKTEST_PIVO_9X=3 (ou outro k) ou nenhum, o de topos e fundos ascendentes;
BACKTEST_REGRA_91=suporte_volume, tendencia ou nenhum, o do 9.1;
BACKTEST_PERTO_9X=0.35 (ATR) ou nenhum, o "perto da MME 9" dos 9.2 a 9.4 (padrao:
os do codigo).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from scanner.backtest.envio import amostra_de_trades, enviar, resumo_da_rodada
from scanner.backtest.metricas import curva, escolher, grade, por_ano
from scanner.backtest.pacote import gravar_pacote, ler_pacote
from scanner.backtest.simulador import TETO
from scanner.backtest.suite import CUSTO, liquidez_historica, rodar_lote
from scanner.config import load_config
from scanner.gatilhos.classicos import NOMES, RegrasClassicas

LOTE = int(os.environ.get("BACKTEST_LOTE", "150"))


def _variante() -> tuple[RegrasClassicas | None, frozenset[str] | None]:
    """Regras e setups do estudo pedido nas variaveis de ambiente (ou o padrao)."""
    so_txt = os.environ.get("BACKTEST_SO", "").strip()
    so = frozenset(x.strip() for x in so_txt.split(",") if x.strip()) or None
    t = os.environ.get("BACKTEST_TENDENCIA_9X", "").strip().upper()
    p = os.environ.get("BACKTEST_PIVO_9X", "").strip().lower()
    r91 = os.environ.get("BACKTEST_REGRA_91", "").strip().lower()
    perto_txt = os.environ.get("BACKTEST_PERTO_9X", "").strip().lower()
    if not t and not p and not r91 and not perto_txt:
        return None, so
    padrao = RegrasClassicas()
    tendencia = padrao.tendencia_9x
    if t == "NENHUMA":
        tendencia = None
    elif t:
        tipo, periodo = t[:3], int(t[3:])
        if tipo not in ("MMA", "MME"):
            raise SystemExit(f"BACKTEST_TENDENCIA_9X invalida: {t}")
        tendencia = (tipo, periodo)
    pivo = padrao.pivo_9x if not p else (None if p == "nenhum" else int(p))
    if r91 and r91 not in ("suporte_volume", "tendencia", "nenhum"):
        raise SystemExit(f"BACKTEST_REGRA_91 invalida: {r91}")
    perto = (
        padrao.perto_9x if not perto_txt else (None if perto_txt == "nenhum" else float(perto_txt))
    )
    return RegrasClassicas(
        tendencia_9x=tendencia, pivo_9x=pivo, regra_91=r91 or padrao.regra_91, perto_9x=perto
    ), so


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
        regras, so = _variante()
        trades = rodar_lote(
            parte, lote, sessoes, liq, cfg, semente=SEMENTE + k, regras_classicas=regras, so=so
        )
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
            f"{str(linha['nivel']).upper():6}  {nomes.get(s, s)}:"
            f" {linha['saida']}/{linha['grupo']}"
            f"  escolha {linha['exp_escolha']:+.3f}R (n {linha['n_escolha']},"
            f" contra controle {linha['dif_escolha']:+.3f})"
            f"  conferencia {linha['exp_conferencia']:+.3f}R"
            f" [{linha['ic_conf_baixo']:+.3f}, {linha['ic_conf_alto']:+.3f}]"
            f" (n {linha['n_conferencia']}, contra controle {linha['dif_conferencia']:+.3f})"
        )


def _da_pasta(pasta: Path) -> dict[str, object]:
    """A rodada de uma pasta de resultado, no formato de `enviar`."""
    trades = pd.read_pickle(pasta / "trades.pkl")
    return {
        "rodada": resumo_da_rodada(trades, CUSTO, TETO),
        "grade": pd.read_pickle(pasta / "grade.pkl"),
        "escolha": pd.read_pickle(pasta / "escolha.pkl"),
        "anos": pd.read_pickle(pasta / "por_ano.pkl"),
        "curva": pd.read_pickle(pasta / "curva.pkl"),
        "amostra": amostra_de_trades(trades),
    }


def empacotar(pasta: Path) -> None:
    destino = pasta / "rodada.json.gz"
    gravar_pacote(destino, **_da_pasta(pasta))  # type: ignore[arg-type]
    print(f"{destino} ({destino.stat().st_size / 1e6:.1f} MB)")


def enviar_rodada(origem: Path) -> None:
    """`origem`: a pasta do resultado, ou o pacote (`rodada.json.gz`) feito por `empacotar`."""
    from scanner.storage.engine import build_engine
    from scanner.storage.migracao import migrar_se_preciso

    t0 = time.time()
    partes = ler_pacote(origem) if origem.is_file() else _da_pasta(origem)
    engine = build_engine()
    migrar_se_preciso(engine)
    rodada = partes["rodada"]
    rodada_id = enviar(engine, **partes)  # type: ignore[arg-type]
    print(
        f"rodada {rodada_id} gravada: dados de {rodada['dados_de']:%d/%m/%Y} a"  # type: ignore[index]
        f" {rodada['dados_ate']:%d/%m/%Y}, {rodada['trades']} trades ({time.time() - t0:.0f}s)"  # type: ignore[index]
    )


def main() -> None:
    etapa = sys.argv[1]
    if etapa == "processar":
        processar(Path(sys.argv[2]), Path(sys.argv[3]))
    elif etapa == "relatorio":
        relatorio(Path(sys.argv[2]))
    elif etapa == "empacotar":
        empacotar(Path(sys.argv[2]))
    elif etapa == "enviar":
        enviar_rodada(Path(sys.argv[2]))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
