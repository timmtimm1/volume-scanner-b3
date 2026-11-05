"""Numeros da suite: expectativa em R com intervalo, contra o controle.

Expectativa = media do R liquido de custos por trade. O intervalo de 95% vem de
bootstrap por MES de entrada (sorteia meses inteiros, com reposicao): trades do
mesmo mes andam juntos (o mercado inteiro sobe ou cai), e sortear trade a trade
daria um intervalo estreito demais.

Protocolo de escolha (o mesmo do estudo dos Setups, decidido em 05/11/2026):
para cada setup, a melhor combinacao de saida e tendencia e escolhida SO com
1995-2015; em 2016-2026 ela e conferida uma vez. Tres niveis (decisao de
05/11/2026), sempre pela conferencia:

- `firme`: intervalo de 95% da expectativa acima de zero e ganha do controle;
- `fraco`: expectativa positiva e ganha do controle, mas o intervalo cruza o zero;
- `falhou`: o resto.
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pandas as pd

from scanner.backtest.simulador import ABERTO, MOTIVOS

F64 = npt.NDArray[np.float64]

ESCOLHA = (1995, 2015)
CONFERENCIA = (2016, 2026)
PERIODOS: dict[str, tuple[int, int]] = {
    "1995-2015": ESCOLHA,
    "2016-2026": CONFERENCIA,
    "tudo": (ESCOLHA[0], CONFERENCIA[1]),
}
GRUPOS = ("todos", "alta", "contra")
FIRME, FRACO, FALHOU = "firme", "fraco", "falhou"
# Combinacao com menos trades que isso no periodo de escolha nao pode ser escolhida.
MINIMO_PARA_ESCOLHER = 100
REPETICOES = 1000


def bootstrap(
    valores: F64, blocos: npt.NDArray[Any], reps: int = REPETICOES, semente: int = 7
) -> tuple[float, float]:
    """Intervalo de 95% da media, sorteando blocos inteiros com reposicao."""
    ok = np.isfinite(valores)
    v, b = valores[ok], blocos[ok]
    if v.size < 2:
        return (float("nan"), float("nan"))
    _, idx = np.unique(b, return_inverse=True)
    somas = np.bincount(idx, weights=v)
    contas = np.bincount(idx).astype(np.float64)
    if somas.size < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(semente)
    sorteio = rng.integers(0, somas.size, size=(reps, somas.size))
    medias = somas[sorteio].sum(axis=1) / contas[sorteio].sum(axis=1)
    lo, hi = np.percentile(medias, [2.5, 97.5])
    return (float(lo), float(hi))


def fechados(trades: pd.DataFrame) -> pd.DataFrame:
    """So trades que sairam (o que ainda esta aberto no fim dos dados nao conta)."""
    return cast(pd.DataFrame, trades[(trades["motivo"] != ABERTO) & np.isfinite(trades["r"])])


def resumo(t: pd.DataFrame) -> dict[str, float | int]:
    """Numeros de um conjunto de trades fechados."""
    r = t["r"].to_numpy(dtype=np.float64)
    n = int(r.size)
    if n == 0:
        return {"n": 0}
    mes = pd.to_datetime(t["data_entrada"]).dt.to_period("M").astype(str).to_numpy()
    ganhos, perdas = r[r > 0], r[r <= 0]
    ctrl = t["r_controle"].to_numpy(dtype=np.float64)
    dif = r - ctrl
    lo, hi = bootstrap(r, mes)
    dlo, dhi = bootstrap(dif, mes)
    dias = t["dias"].to_numpy(dtype=np.float64)
    soma_perdas = -perdas.sum()
    out: dict[str, float | int] = {
        "n": n,
        "acerto": float(ganhos.size / n),
        "ganho_medio": float(ganhos.mean()) if ganhos.size else float("nan"),
        "perda_media": float(perdas.mean()) if perdas.size else float("nan"),
        "payoff": float(ganhos.mean() / -perdas.mean())
        if ganhos.size and perdas.size and perdas.mean() < 0
        else float("nan"),
        "expectativa": float(r.mean()),
        "ic_baixo": lo,
        "ic_alto": hi,
        "fator_lucro": float(ganhos.sum() / soma_perdas) if soma_perdas > 0 else float("nan"),
        "dias_medio": float(dias.mean()),
        "r_por_dia": float(r.sum() / max(dias.sum() + n, 1)),
        "controle": float(np.nanmean(ctrl)) if np.isfinite(ctrl).any() else float("nan"),
        "diferenca": float(np.nanmean(dif)) if np.isfinite(dif).any() else float("nan"),
        "dif_ic_baixo": dlo,
        "dif_ic_alto": dhi,
    }
    contagem = t["motivo"].value_counts()
    for codigo, nome in MOTIVOS.items():
        if codigo != ABERTO:
            out[f"pct_{nome}"] = float(contagem.get(codigo, 0) / n)
    return out


def _do_periodo(t: pd.DataFrame, periodo: tuple[int, int]) -> pd.DataFrame:
    ano = pd.to_datetime(t["data_entrada"]).dt.year
    return t[(ano >= periodo[0]) & (ano <= periodo[1])]


def _do_grupo(t: pd.DataFrame, grupo: str) -> pd.DataFrame:
    if grupo == "alta":
        return t[t["alta"]]
    if grupo == "contra":
        return t[~t["alta"]]
    return t


def grade(trades: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por (setup, saida, grupo, periodo) com os numeros de `resumo`."""
    t = fechados(trades)
    linhas = []
    for (setup, saida), parte in t.groupby(["setup", "saida"], observed=True):
        for grupo in GRUPOS:
            g = _do_grupo(parte, grupo)
            for nome, periodo in PERIODOS.items():
                linhas.append(
                    {"setup": setup, "saida": saida, "grupo": grupo, "periodo": nome}
                    | resumo(_do_periodo(g, periodo))
                )
    return pd.DataFrame(linhas)


def nivel_da_conferencia(expectativa: float, ic_baixo: float, diferenca: float) -> str:
    """Firme, fraco ou falhou, pelos numeros de 2016-2026 da combinacao escolhida."""
    if not (expectativa > 0 and diferenca > 0):
        return FALHOU
    return FIRME if ic_baixo > 0 else FRACO


def escolher(g: pd.DataFrame) -> pd.DataFrame:
    """Por setup: a combinacao escolhida em 1995-2015 e como ela foi em 2016-2026."""
    linhas: list[dict[str, object]] = []
    dentro = g[(g["periodo"] == "1995-2015") & (g["n"] >= MINIMO_PARA_ESCOLHER)]
    fora = {
        (str(x["setup"]), str(x["saida"]), str(x["grupo"])): x
        for x in g[g["periodo"] == "2016-2026"].to_dict("records")
    }
    for setup, parte in g.groupby("setup", observed=True):
        candidatos = dentro[dentro["setup"] == setup]
        combinacoes = len(parte[parte["periodo"] == "1995-2015"])
        if candidatos.empty:
            linhas.append(
                {"setup": setup, "nivel": FALHOU, "passou": False, "combinacoes": combinacoes}
            )
            continue
        melhor = candidatos.sort_values("expectativa", ascending=False).iloc[0]
        conf = fora.get((str(setup), str(melhor["saida"]), str(melhor["grupo"])))
        nan = float("nan")
        exp_fora = float(conf["expectativa"]) if conf is not None else nan
        dif_fora = float(conf["diferenca"]) if conf is not None else nan
        ic_baixo = float(conf["ic_baixo"]) if conf is not None else nan
        nivel = nivel_da_conferencia(exp_fora, ic_baixo, dif_fora)
        linhas.append(
            {
                "setup": setup,
                "saida": melhor["saida"],
                "grupo": melhor["grupo"],
                "combinacoes": combinacoes,
                "n_escolha": int(melhor["n"]),
                "exp_escolha": float(melhor["expectativa"]),
                "dif_escolha": float(melhor["diferenca"]),
                "n_conferencia": int(conf["n"]) if conf is not None else 0,
                "exp_conferencia": exp_fora,
                "ic_conf_baixo": ic_baixo,
                "ic_conf_alto": float(conf["ic_alto"]) if conf is not None else nan,
                "dif_conferencia": dif_fora,
                "nivel": nivel,
                "passou": nivel != FALHOU,
            }
        )
    return pd.DataFrame(linhas)


def por_ano(trades: pd.DataFrame) -> pd.DataFrame:
    """Por (setup, saida, grupo, ano de entrada): n, expectativa, soma de R, controle."""
    t = fechados(trades)
    t = t.assign(ano=pd.to_datetime(t["data_entrada"]).dt.year)
    partes = []
    for grupo in GRUPOS:
        g = _do_grupo(t, grupo)
        a = (
            g.groupby(["setup", "saida", "ano"], observed=True)
            .agg(
                n=("r", "size"),
                expectativa=("r", "mean"),
                soma_r=("r", "sum"),
                controle=("r_controle", "mean"),
            )
            .reset_index()
            .assign(grupo=grupo)
        )
        partes.append(a)
    return pd.concat(partes, ignore_index=True)


def curva(trades: pd.DataFrame) -> pd.DataFrame:
    """R acumulado por mes de saida (1R por trade, sem juros compostos) e o recuo maximo.

    Soma de R, nao carteira: trades simultaneos somam juntos. Mostra a forma do
    resultado no tempo (onde ganhou, onde devolveu), nao o saldo de uma conta.
    """
    t = fechados(trades)
    t = t.assign(mes=pd.to_datetime(t["data_saida"]).dt.to_period("M").dt.to_timestamp())
    partes = []
    for grupo in GRUPOS:
        g = _do_grupo(t, grupo)
        m = (
            g.groupby(["setup", "saida", "mes"], observed=True)
            .agg(r=("r", "sum"), controle=("r_controle", "sum"), n=("r", "size"))
            .reset_index()
            .sort_values(["setup", "saida", "mes"])
        )
        m["acumulado"] = m.groupby(["setup", "saida"], observed=True)["r"].cumsum()
        m["controle_acumulado"] = m.groupby(["setup", "saida"], observed=True)["controle"].cumsum()
        topo = m.groupby(["setup", "saida"], observed=True)["acumulado"].cummax()
        m["recuo"] = m["acumulado"] - topo.clip(lower=0)
        partes.append(m.assign(grupo=grupo))
    return pd.concat(partes, ignore_index=True)
