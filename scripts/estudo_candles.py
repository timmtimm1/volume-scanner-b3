"""Varredura de padroes de candle na suite de backtest (estudo, nao produto).

Pedido do usuario em 11/11/2026: procurar, entre os padroes de candle das
bibliotecas abertas, algum que passe no mesmo criterio dos setups. Os 62 padroes
sao os do `pandas-ta-classic` (implementacao propria dos 61 do TA-Lib, mais
`inside`), instalado so para este estudo: `uv pip install pandas-ta-classic`.

Cada padrao vira DOIS sinais de compra:

- `NOME+`: o padrao deu sinal de alta;
- `NOME-`: o padrao deu sinal de baixa, e a compra e a FALHA dele (o preco passa
  da maxima no pregao seguinte, contra o que o padrao dizia).

A operacao e a mesma de todo setup da suite (`trades_dos_sinais`): compra R$ 0,01
acima da maxima do candle do sinal, stop R$ 0,01 abaixo da menor minima dos
candles do padrao, as cinco saidas, custo, um trade por vez e o trade de controle.

Sao mais de cem sinais, alguns em 10% dos pregoes: os trades nao cabem na
memoria. Cada lote guarda so a soma por mes de entrada (n, R, R do controle,
ganhos), que e tudo de que a expectativa e o bootstrap por mes precisam.

    python scripts/estudo_candles.py processar <barras.pkl> <pasta>
    python scripts/estudo_candles.py relatorio <pasta>

Protocolo: o de sempre. Para cada sinal, a melhor combinacao de saida e
tendencia e escolhida so com 1995-2015 e conferida uma vez em 2016-2026. Com
mais de cem sinais conferidos, uns 3 passariam do intervalo de 95% por acaso;
por isso o relatorio traz tambem o criterio RIGIDO: o piso do intervalo com a
correcao de Bonferroni (5% dividido pelo numero de sinais conferidos).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd
import pandas_ta_classic as ta

from scanner.backtest.metricas import FALHOU, FIRME, MINIMO_PARA_ESCOLHER, nivel_da_conferencia
from scanner.backtest.suite import liquidez_historica, trades_dos_sinais
from scanner.gatilhos.classicos import CENTAVO, Sinal
from scanner.gatilhos.contexto import calcular
from scanner.gatilhos.matrizes import ajuste_acumulado, montar

F64 = npt.NDArray[np.float64]
B = npt.NDArray[np.bool_]

LOTE = int(os.environ.get("BACKTEST_LOTE", "150"))
SEMENTE = 20261111
REPETICOES = 2000

# Quantos candles cada padrao usa (a minima do padrao e a menor deles). O que
# nao esta aqui usa 3.
UM = [
    "BELTHOLD",
    "CLOSINGMARUBOZU",
    "DOJI",
    "DRAGONFLYDOJI",
    "GRAVESTONEDOJI",
    "HAMMER",
    "HANGINGMAN",
    "HIGHWAVE",
    "INVERTEDHAMMER",
    "LONGLEGGEDDOJI",
    "LONGLINE",
    "MARUBOZU",
    "RICKSHAWMAN",
    "SHOOTINGSTAR",
    "SHORTLINE",
    "SPINNINGTOP",
    "TAKURI",
]
DOIS = [
    "COUNTERATTACK",
    "DARKCLOUDCOVER",
    "DOJISTAR",
    "ENGULFING",
    "HARAMI",
    "HARAMICROSS",
    "HOMINGPIGEON",
    "INNECK",
    "INSIDE",
    "KICKING",
    "KICKINGBYLENGTH",
    "MATCHINGLOW",
    "ONNECK",
    "PIERCING",
    "SEPARATINGLINES",
    "THRUSTING",
]
QUATRO = ["3LINESTRIKE", "CONCEALBABYSWALL"]
CINCO = [
    "BREAKAWAY",
    "HIKKAKE",
    "HIKKAKEMOD",
    "LADDERBOTTOM",
    "MATHOLD",
    "RISEFALL3METHODS",
    "XSIDEGAP3METHODS",
]
TAMANHO = (
    dict.fromkeys(UM, 1)
    | dict.fromkeys(DOIS, 2)
    | dict.fromkeys(QUATRO, 4)
    | dict.fromkeys(CINCO, 5)
)


def nome_curto(coluna: str) -> str:
    """`CDL_DOJI_10_0.1` -> `DOJI`."""
    return coluna.removeprefix("CDL_").split("_")[0]


def menor_minima(minima: F64, n: int) -> F64:
    """A menor minima dos ultimos `n` pregoes de cada papel (NaN nao conta)."""
    return pd.DataFrame(minima).rolling(n, min_periods=1).min().to_numpy(dtype=np.float64)


def sinais_dos_candles(o: F64, h: F64, low: F64, c: F64, tick: F64) -> dict[str, Sinal]:
    """Um `Sinal` por padrao e direcao. Os dias sem negocio saem da serie antes."""
    dias, papeis = c.shape
    gatilho = h + tick
    stops = {n: menor_minima(low, n) - tick for n in (1, 2, 3, 4, 5)}
    armados: dict[str, B] = {}
    for j in range(papeis):
        tem = np.isfinite(o[:, j]) & np.isfinite(h[:, j]) & np.isfinite(low[:, j])
        tem &= np.isfinite(c[:, j])
        if tem.sum() < 30:
            continue
        onde = np.nonzero(tem)[0]
        serie = [pd.Series(x[onde, j]) for x in (o, h, low, c)]
        achados = ta.cdl_pattern(*serie, name="all")
        if achados is None:
            continue
        for coluna in achados.columns:
            valores = achados[coluna].to_numpy(dtype=np.float64)
            for sufixo, marca in (("+", valores > 0), ("-", valores < 0)):
                if not marca.any():
                    continue
                nome = nome_curto(coluna) + sufixo
                if nome not in armados:
                    armados[nome] = np.zeros((dias, papeis), dtype=bool)
                armados[nome][onde[marca], j] = True
    return {
        nome: Sinal(armado=a, gatilho=gatilho, stop=stops[TAMANHO.get(nome[:-1], 3)])
        for nome, a in sorted(armados.items())
    }


def por_mes(trades: pd.DataFrame) -> pd.DataFrame:
    """As somas por (setup, saida, tendencia, mes de entrada) dos trades fechados."""
    t = trades[(trades["motivo"] != 0) & np.isfinite(trades["r"])]
    r = t["r"].astype(np.float64)
    ctrl = t["r_controle"].astype(np.float64)
    tem_ctrl = np.isfinite(ctrl)
    t = t.assign(
        mes=pd.to_datetime(t["data_entrada"]).dt.to_period("M").dt.to_timestamp(),
        r=r,
        ganhou=(r > 0).astype(np.int64),
        ganho=r.where(r > 0, 0.0),
        dif=(r - ctrl).where(tem_ctrl, 0.0),
        n_dif=tem_ctrl.astype(np.int64),
        dias=t["dias"].astype(np.float64),
        risco=t["risco_pct"].astype(np.float64),
    )
    return (
        t.groupby(["setup", "saida", "alta", "mes"], observed=True)
        .agg(
            n=("r", "size"),
            soma_r=("r", "sum"),
            ganhou=("ganhou", "sum"),
            ganho=("ganho", "sum"),
            dif=("dif", "sum"),
            n_dif=("n_dif", "sum"),
            dias=("dias", "sum"),
            risco=("risco", "sum"),
        )
        .reset_index()
    )


def processar(barras_pkl: Path, pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    b = pd.read_pickle(barras_pkl)
    b["ticker"] = b["ticker"].astype(str)
    sessoes = pd.DatetimeIndex(sorted(pd.to_datetime(b["trade_date"].unique())))
    liq = liquidez_historica(b, sessoes)
    alguma_vez = sorted(liq.columns[liq.to_numpy().any(axis=0)])
    tickers = list(np.random.default_rng(SEMENTE).permutation(alguma_vez))
    lotes = [tickers[i : i + LOTE] for i in range(0, len(tickers), LOTE)]
    print(f"{len(tickers)} papeis, {len(sessoes)} pregoes, {len(lotes)} lotes", flush=True)
    for k, lote in enumerate(lotes):
        destino = pasta / f"mensal_{k:03d}.pkl"
        if destino.exists():
            continue
        t1 = time.time()
        m = montar(b[b["ticker"].isin(lote)], lote, sessoes)
        ajuste = ajuste_acumulado(m.fator)
        tick = CENTAVO * ajuste
        liquido = liq.reindex(index=sessoes, columns=lote).fillna(False).to_numpy(dtype=bool)
        sinais = sinais_dos_candles(m.abertura, m.maxima, m.minima, m.fechamento, tick)
        t2 = time.time()
        # um sinal por vez: os trades de todos juntos nao cabem na memoria
        partes = []
        ctx = calcular(m.maxima, m.fechamento, m.volume)
        for i, (nome, sinal) in enumerate(sinais.items()):
            rng = np.random.default_rng([SEMENTE, k, i])
            trades = trades_dos_sinais(m, {nome: sinal}, liquido, tick, ajuste, ctx, rng)
            if not trades.empty:
                partes.append(por_mes(trades))
        pd.concat(partes, ignore_index=True).to_pickle(destino)
        print(
            f"lote {k + 1}/{len(lotes)}: {len(sinais)} sinais,"
            f" candles {t2 - t1:.0f}s, trades {time.time() - t2:.0f}s",
            flush=True,
        )


def intervalo(soma: F64, n: F64, reps: int, alfa: float, rng: np.random.Generator) -> float:
    """Piso do intervalo (percentil `alfa`) da media, sorteando meses inteiros."""
    if soma.size < 2:
        return float("nan")
    medias = []
    for _ in range(0, reps, 2000):
        sorteio = rng.integers(0, soma.size, size=(2000, soma.size))
        medias.append(soma[sorteio].sum(axis=1) / np.maximum(n[sorteio].sum(axis=1), 1))
    return float(np.percentile(np.concatenate(medias), 100 * alfa))


PERIODOS = {"1995-2015": (1995, 2015), "2016-2026": (2016, 2026)}
GRUPOS = {"todos": None, "alta": True, "contra": False}


def grade(mensal: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por (setup, saida, grupo, periodo), com o piso de 95% do intervalo."""
    rng = np.random.default_rng(7)
    ano = mensal["mes"].dt.year
    linhas = []
    for (setup, saida), parte in mensal.groupby(["setup", "saida"], observed=True):
        for grupo, alta in GRUPOS.items():
            g = parte if alta is None else parte[parte["alta"] == alta]
            for periodo, (de, ate) in PERIODOS.items():
                p = g[(ano.loc[g.index] >= de) & (ano.loc[g.index] <= ate)]
                colunas = ["n", "soma_r", "ganhou", "ganho", "dif", "n_dif", "dias"]
                if "risco" in p:
                    colunas.append("risco")
                mm = p.groupby("mes")[colunas]
                s = mm.sum()
                n = float(s["n"].sum())
                if n == 0:
                    continue
                soma_r, nn = s["soma_r"].to_numpy(), s["n"].to_numpy(dtype=np.float64)
                linhas.append(
                    {
                        "setup": setup,
                        "saida": saida,
                        "grupo": grupo,
                        "periodo": periodo,
                        "n": int(n),
                        "acerto": float(s["ganhou"].sum() / n),
                        "ganho_medio": float(s["ganho"].sum() / max(s["ganhou"].sum(), 1)),
                        "expectativa": float(soma_r.sum() / n),
                        "ic_baixo": intervalo(soma_r, nn, REPETICOES, 0.025, rng),
                        "diferenca": float(s["dif"].sum() / max(s["n_dif"].sum(), 1)),
                        "dias_medio": float(s["dias"].sum() / n),
                        "risco_medio": float(s["risco"].sum() / n) if "risco" in s else np.nan,
                        "dif_ic_baixo": intervalo(
                            s["dif"].to_numpy(),
                            s["n_dif"].to_numpy(dtype=np.float64),
                            REPETICOES,
                            0.025,
                            rng,
                        ),
                    }
                )
    return pd.DataFrame(linhas)


def relatorio(pasta: Path) -> None:
    mensal = pd.concat(
        [pd.read_pickle(p) for p in sorted(pasta.glob("mensal_*.pkl"))], ignore_index=True
    )
    mensal = mensal.groupby(["setup", "saida", "alta", "mes"], observed=True).sum().reset_index()
    g = grade(mensal)
    g.to_pickle(pasta / "grade.pkl")
    dentro = g[(g["periodo"] == "1995-2015") & (g["n"] >= MINIMO_PARA_ESCOLHER)]
    fora = g[g["periodo"] == "2016-2026"].set_index(["setup", "saida", "grupo"])
    escolhidos = []
    for setup, cand in dentro.groupby("setup"):
        melhor = cand.sort_values("expectativa", ascending=False).iloc[0]
        chave = (setup, melhor["saida"], melhor["grupo"])
        if chave not in fora.index:
            continue
        conf = fora.loc[chave]
        escolhidos.append(
            {
                "setup": setup,
                "saida": melhor["saida"],
                "grupo": melhor["grupo"],
                "exp_escolha": melhor["expectativa"],
                "dif_escolha": melhor["diferenca"],
                "n": int(conf["n"]),
                "acerto": conf["acerto"],
                "exp": conf["expectativa"],
                "ic_baixo": conf["ic_baixo"],
                "dif": conf["diferenca"],
                "dias": conf["dias_medio"],
                "risco": conf.get("risco_medio", np.nan),
                "dif_ic": conf.get("dif_ic_baixo", np.nan),
                "nivel": nivel_da_conferencia(
                    float(conf["expectativa"]), float(conf["ic_baixo"]), float(conf["diferenca"])
                ),
            }
        )
    e = pd.DataFrame(escolhidos)
    # criterio rigido: Bonferroni sobre os sinais conferidos, com mais sorteios
    k = len(e)
    rng = np.random.default_rng(11)
    ano = mensal["mes"].dt.year
    rigido = []
    for linha in e.itertuples():
        if linha.nivel == FALHOU:
            rigido.append(float("nan"))
            continue
        p = mensal[(mensal["setup"] == linha.setup) & (mensal["saida"] == linha.saida)]
        if linha.grupo != "todos":
            p = p[p["alta"] == (linha.grupo == "alta")]
        p = p[ano.loc[p.index] >= 2016].groupby("mes")[["soma_r", "n"]].sum()
        rigido.append(
            intervalo(
                p["soma_r"].to_numpy(),
                p["n"].to_numpy(dtype=np.float64),
                200_000,
                0.025 / k,
                rng,
            )
        )
    e["ic_rigido"] = rigido
    e["passa_rigido"] = (e["nivel"] == FIRME) & (e["ic_rigido"] > 0)
    e = e.sort_values(["nivel", "exp"], ascending=[True, False])
    e.to_pickle(pasta / "escolha.pkl")
    e.to_csv(pasta / "escolha.csv", index=False)
    print(f"{k} sinais conferidos: {e['nivel'].value_counts().to_dict()}")
    print(f"passam no criterio rigido (Bonferroni, {k} testes): {int(e['passa_rigido'].sum())}\n")
    with pd.option_context("display.width", 200, "display.max_rows", 300):
        print(e[e["nivel"] != FALHOU].round(3).to_string(index=False))


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
