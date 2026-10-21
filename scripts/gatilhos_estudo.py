"""Estudo dos candles gatilho no COTAHIST de 1995 em diante.

Etapa 1 (`processar`): roda candles, contexto e o motor de suporte/resistencia
em lotes de papeis e grava UMA LINHA POR PAPEL POR DIA LIQUIDO, com as camadas e
o que o preco fez depois (5, 10, 20 e 60 pregoes).

    python scripts/gatilhos_estudo.py processar <barras.pkl> <saida_dir> [tol_atr pivo]

Universo de cada dia, sem olhar o futuro: mediana do volume dos 60 pregoes
anteriores acima do piso, e negocio em ao menos 48 desses 60. O piso e o R$ 500
mil de hoje escalado pelo tamanho do mercado de cada epoca (mediana de 250
pregoes do volume total), para "liquido em 1996" querer dizer o mesmo que hoje.

Retorno em excesso = retorno do papel menos a media simples dos papeis liquidos
no mesmo dia e horizonte. Precos ajustados por desdobramento/grupamento, NAO por
proventos: dividendo puxa todos os retornos um pouco para baixo, o excesso anula
a maior parte disso.
"""

from __future__ import annotations

import pickle
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd

from scanner.gatilhos.candles import padroes
from scanner.gatilhos.contexto import atr_wilder, calcular
from scanner.gatilhos.matrizes import montar
from scanner.gatilhos.medias import toques_na_media
from scanner.gatilhos.niveis import Regras, detectar

F64 = npt.NDArray[np.float64]

PISO_HOJE = 500_000.0
# Papeis por lote. O pico de memoria cresce com o lote: com 250, ~1,3 GB; numa
# maquina com pouca memoria livre, GATILHOS_LOTE=100 cabe em bem menos.
LOTE = int(__import__("os").environ.get("GATILHOS_LOTE", "250"))
HORIZONTES = (5, 10, 20, 60)
ALVO_R = 2.0
PRAZO_R = 20


def universo(b: pd.DataFrame, sessoes: pd.DatetimeIndex) -> pd.Series:
    """Booleano por (ticker, trade_date): o papel era liquido naquele dia."""
    pos = pd.Series(np.arange(len(sessoes)), index=sessoes)
    b = b.assign(s=pos.loc[b["trade_date"]].to_numpy())
    mercado = b.groupby("s")["volume_financial"].sum().reindex(range(len(sessoes)))
    m250 = mercado.rolling(250, min_periods=60).median().bfill()
    piso = PISO_HOJE * m250 / m250.iloc[-1]
    b = b.sort_values(["ticker", "s"])
    g = b.groupby("ticker", observed=True)
    med = g["volume_financial"].transform(lambda x: x.shift(1).rolling(60, min_periods=48).median())
    cobre = (b["s"] - g["s"].shift(48)) <= 60
    liquido = (med >= piso.to_numpy()[b["s"].to_numpy()]) & cobre
    return pd.Series(
        liquido.to_numpy(), index=pd.MultiIndex.from_arrays([b["ticker"], b["trade_date"]])
    )


def _frente(m: F64, h: int) -> F64:
    out = np.full_like(m, np.nan)
    out[:-h] = m[h:]
    return out


def _janela_min(m: F64, n: int) -> F64:
    return pd.DataFrame(m).rolling(n, min_periods=1).min().to_numpy(dtype=np.float64)


def processar_lote(
    b: pd.DataFrame,
    tickers: list[str],
    sessoes: pd.DatetimeIndex,
    liq: pd.DataFrame,
    regras: Regras,
) -> tuple[pd.DataFrame, dict[str, object]]:
    m = montar(b, tickers, sessoes)
    o, h, low, c = m.abertura, m.maxima, m.minima, m.fechamento
    atr = atr_wilder(h, low, c)
    ctx = calcular(h, c, m.volume)
    pad = padroes(o, h, low, c, atr)
    ret, ev = detectar(h, low, c, atr, regras)
    medias = toques_na_media(low, c, atr)

    # o que veio depois
    cff = pd.DataFrame(c).ffill(limit=5).to_numpy(dtype=np.float64)
    fut = {f"r{hz}": _frente(cff, hz) / c - 1 for hz in HORIZONTES}

    # trade de referencia: entra no fechamento, stop na minima do padrao, alvo 2R
    tam = np.where(pad["estrela"], 3, np.where(pad["engolfo"] | pad["piercing"], 2, 1))
    stop = np.where(tam == 3, _janela_min(low, 3), np.where(tam == 2, _janela_min(low, 2), low))
    risco = c - stop
    risco[risco < 0.002 * c] = np.nan
    alvo = c + ALVO_R * risco
    resultado = np.full_like(c, np.nan)
    aberto = np.isfinite(risco)
    for d in range(1, PRAZO_R + 1):
        ld, hd = _frente(low, d), _frente(h, d)
        perde = aberto & (ld < stop)
        ganha = aberto & ~perde & (hd >= alvo)
        resultado[perde] = -1.0
        resultado[ganha] = ALVO_R
        aberto &= ~(perde | ganha)
    fim = (_frente(cff, PRAZO_R) - c) / risco
    resultado[aberto] = fim[aberto]

    # entrada com confirmacao: so compra se o dia seguinte passar da maxima do
    # candle; entra na maxima (ou na abertura, se abriu acima dela)
    o1, h1, l1 = _frente(o, 1), _frente(h, 1), _frente(low, 1)
    with np.errstate(invalid="ignore"):
        confirma = h1 > h
        entrada = np.where(confirma, np.fmax(o1, h), np.nan)
        risco_c = entrada - stop
        risco_c[~(risco_c > 0.002 * entrada)] = np.nan
    alvo_c = entrada + ALVO_R * risco_c
    res_c = np.full_like(c, np.nan)
    aberto = np.isfinite(risco_c)
    # no dia da entrada a ordem dos precos e desconhecida: minima abaixo do stop
    # conta como stop, mesmo que tenha vindo antes da entrada (conservador)
    with np.errstate(invalid="ignore"):
        perde = aberto & (l1 < stop)
        res_c[perde] = -1.0
        aberto &= ~perde
        ganha = aberto & (h1 >= alvo_c)
        res_c[ganha] = ALVO_R
        aberto &= ~ganha
        for d in range(2, PRAZO_R + 2):
            ld, hd = _frente(low, d), _frente(h, d)
            perde = aberto & (ld < stop)
            ganha = aberto & ~perde & (hd >= alvo_c)
            res_c[perde] = -1.0
            res_c[ganha] = ALVO_R
            aberto &= ~(perde | ganha)
        fim_c = (_frente(cff, PRAZO_R + 1) - entrada) / risco_c
    res_c[aberto] = fim_c[aberto]
    conf = {f"rc{hz}": _frente(cff, hz + 1) / entrada - 1 for hz in HORIZONTES}
    # retorno do mercado na mesma janela da entrada confirmada (fechamento do dia
    # seguinte ate o horizonte), para o excesso
    d1 = {f"rd{hz}": _frente(cff, hz + 1) / _frente(cff, 1) - 1 for hz in HORIZONTES}

    mask = liq.reindex(index=sessoes, columns=tickers).fillna(False).to_numpy(dtype=bool)
    dd, tt = np.nonzero(mask)

    def col(a: F64 | npt.NDArray[np.generic], tipo: str = "float32") -> npt.NDArray[np.generic]:
        return np.asarray(a[dd, tt]).astype(tipo)

    linhas = {
        "s": dd.astype(np.int32),
        "ticker": pd.Categorical(np.asarray(tickers)[tt]),
        "close": col(c),
        "atr": col(atr),
        "tol": col(ret.tol),
        **{k: col(v, "bool") for k, v in pad.items()},
        "ret_ant": col(ctx["ret_ant"]),
        "recuo": col(ctx["recuo"]),
        "queda": col(ctx["queda"], "bool"),
        "baixa": col(ctx["baixa"], "bool"),
        "correcao": col(ctx["correcao"], "bool"),
        "rvol": col(ctx["rvol"]),
        "z": col(ctx["z"]),
        "z6": col(pd.DataFrame(ctx["z"]).rolling(21, min_periods=1).max().to_numpy() >= 6, "bool"),
        "sup_preco": col(ret.sup_preco),
        "sup_forca": col(ret.sup_forca, "int16"),
        "res_preco": col(ret.res_preco),
        "res_forca": col(ret.res_forca, "int16"),
        "rompeu_res": col(ret.rompeu_res, "bool"),
        "rompeu_res_forca": col(ret.rompeu_res_forca, "int16"),
        "caixa": col(ret.caixa_altura),
        "risco": col(risco / c),
        "res_r": col(resultado),
        **{k: col(v) for k, v in fut.items()},
        "confirma": col(confirma, "bool"),
        "res_r_conf": col(res_c),
        **{k: col(v) for k, v in conf.items()},
        **{k: col(v) for k, v in d1.items()},
    }
    for nome_media, (_, toque) in medias.items():
        for camada in range(3):
            linhas[f"{nome_media}_toca{camada + 1}"] = col(toque[camada], "bool")
    for camada in range(3):
        linhas[f"toca{camada + 1}_forca"] = col(ret.toca_forca[camada], "int16")
        linhas[f"toca{camada + 1}_furou"] = col(ret.toca_furou[camada], "bool")
        linhas[f"toca{camada + 1}_virou"] = col(ret.toca_virou[camada], "bool")
        linhas[f"toca{camada + 1}_seg"] = col(ret.toca_seg[camada], "int32")
        linhas[f"toca{camada + 1}_preco"] = col(ret.toca_preco[camada])
    extra = {
        "segmentos": ev.segmentos.assign(
            ticker=np.asarray(tickers)[ev.segmentos["col"].astype(int)]
        ),
        "toques": ev.toques.assign(ticker=np.asarray(tickers)[ev.toques["col"].astype(int)]),
        "despejos": ev.despejos,
        "resumo": ev.resumo,
    }
    return pd.DataFrame(linhas), extra


def processar(barras: Path, saida: Path, regras: Regras) -> None:
    t0 = time.time()
    b = pd.read_pickle(barras)
    b["ticker"] = b["ticker"].astype(str)
    sessoes = pd.DatetimeIndex(np.sort(b["trade_date"].unique()))
    liq_s = universo(b, sessoes)
    alguma_vez = liq_s.groupby(level=0).any()
    sempre = sorted(alguma_vez.index[alguma_vez.to_numpy()])
    liq_s = liq_s[liq_s.index.get_level_values(0).isin(sempre)]
    # booleano, e nao objeto: com NaN o unstack daria uma matriz de objetos
    liq = liq_s.unstack("ticker").fillna(False).astype(bool)
    print(
        f"universo: {len(sempre)} papeis liquidos em algum dia ({time.time() - t0:.0f}s)",
        flush=True,
    )
    b = b[b["ticker"].isin(sempre)]

    saida.mkdir(parents=True, exist_ok=True)
    partes: list[int] = []
    segs, toques, despejos = [], [], 0
    resumo: dict[str, int] = {}
    for k in range(0, len(sempre), LOTE):
        lote = sempre[k : k + LOTE]
        df, extra = processar_lote(b, lote, sessoes, liq, regras)
        # cada lote vai para o disco: com pouca memoria livre, acumular os lotes
        # em memoria matava o processo antes do fim
        df.to_pickle(saida / f"_lote_{k // LOTE:03d}.pkl")
        partes.append(len(df))
        segs.append(extra["segmentos"])
        toques.append(extra["toques"])
        despejos += int(extra["despejos"])  # type: ignore[call-overload]
        for chave, v in extra["resumo"].items():  # type: ignore[attr-defined]
            resumo[chave] = resumo.get(chave, 0) + int(v)
        print(
            f"lote {k // LOTE + 1}: {len(lote)} papeis, {partes[-1]} linhas "
            f"({time.time() - t0:.0f}s)",
            flush=True,
        )
        del df, extra
        __import__("gc").collect()

    del b, liq, liq_s
    __import__("gc").collect()
    arquivos = sorted(saida.glob("_lote_*.pkl"))
    dados = pd.concat([pd.read_pickle(a) for a in arquivos], ignore_index=True)
    dados["ticker"] = dados["ticker"].astype("category")
    for a in arquivos:
        a.unlink()
    for hz in HORIZONTES:
        media = dados.groupby("s")[f"r{hz}"].transform("mean")
        dados[f"x{hz}"] = (dados[f"r{hz}"] - media).astype("float32")
        media_d1 = dados.groupby("s")[f"rd{hz}"].transform("mean")
        dados[f"xc{hz}"] = (dados[f"rc{hz}"] - media_d1).astype("float32")
        dados = dados.drop(columns=[f"rd{hz}"])
    saida.mkdir(parents=True, exist_ok=True)
    dados.to_pickle(saida / "linhas.pkl")
    with (saida / "eventos.pkl").open("wb") as f:
        pickle.dump(
            {
                "segmentos": pd.concat(segs, ignore_index=True),
                "toques": pd.concat(toques, ignore_index=True),
                "despejos": despejos,
                "resumo": resumo,
                "sessoes": sessoes,
                "regras": regras,
            },
            f,
        )
    print(f"pronto: {len(dados)} linhas, {despejos} despejos, {resumo} ({time.time() - t0:.0f}s)")


# ---------------------------------------------------------------------------
# Etapa 2: relatorio. Le linhas.pkl e escreve o JSON que a pagina desenha.
# ---------------------------------------------------------------------------

PERIODOS = ((1995, 2005), (2006, 2015), (2016, 2026))
INTERVALO = 5  # mesmo papel e mesmo grupo dentro de 5 pregoes = um evento so


def camadas(d: pd.DataFrame, toques: int = 3) -> dict[str, pd.Series]:
    """As camadas como mascaras sobre as linhas (papel x dia liquido)."""
    t1, t2, t3 = (d[f"toca{k}_forca"] >= toques for k in (1, 2, 3))
    rev1 = d["martelo"] | d["libelula"]
    rev2 = d["engolfo"] | d["piercing"]
    rev3 = d["estrela"]
    candle = rev1 | rev2 | rev3
    em1, em2, em3 = rev1 & t1, rev2 & t2, rev3 & t3
    gat = em1 | em2 | em3
    camada = np.where(em1, 1, np.where(em2, 2, 3))
    pega = lambda nome: pd.Series(  # noqa: E731
        np.choose(camada - 1, [d[f"toca{k}_{nome}"].to_numpy() for k in (1, 2, 3)]), index=d.index
    )
    return {
        "candle": candle,
        "gat": gat,
        "toca": t1,
        "forca_toque": pega("forca"),
        "furou": pega("furou"),
        "virou": pega("virou"),
        "vol": d["rvol"] >= 1.5,
        "lateral": d["caixa"].notna(),
        "rompe": d["rompeu_res_forca"] >= toques,
        "forca": d["forca"],
        "rev1": rev1,
        "rev2": rev2,
    }


def _dedup(d: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    e = d.loc[mask.to_numpy()].sort_values(["ticker", "s"])
    anterior = e.groupby("ticker", observed=True)["s"].shift(1)
    return e[(e["s"] - anterior).isna() | ((e["s"] - anterior) > INTERVALO)]


def medir(e: pd.DataFrame, sessoes: pd.DatetimeIndex) -> dict[str, object]:
    """Media do excesso com intervalo de 95% pela media de cada mes.

    Eventos do mesmo mes andam juntos (o mercado mexe em todos). Tratar cada um
    como independente daria intervalo estreito demais; a media mensal nao.
    """
    mes = sessoes[e["s"].to_numpy()].to_period("M")
    out: dict[str, object] = {"n": len(e), "meses": int(pd.Series(mes).nunique())}
    for hz in HORIZONTES:
        x = e[f"x{hz}"].to_numpy(dtype=np.float64) * 100
        ok = np.isfinite(x)
        if ok.sum() < 30:
            out[str(hz)] = None
            continue
        mensal = pd.Series(x[ok]).groupby(np.asarray(mes)[ok]).mean()
        ep = mensal.std(ddof=1) / np.sqrt(len(mensal)) if len(mensal) > 1 else np.nan
        out[str(hz)] = {
            "media": round(float(x[ok].mean()), 3),
            "mensal": round(float(mensal.mean()), 3),
            "ic": round(float(1.96 * ep), 3),
            "mediana": round(float(np.median(x[ok])), 3),
            "acerto": round(float((x[ok] > 0).mean() * 100), 1),
            "bruto": round(float(np.nanmean(e[f"r{hz}"]) * 100), 3),
        }
    r = e["res_r"].to_numpy(dtype=np.float64)
    r = r[np.isfinite(r)]
    if len(r) >= 30:
        out["r"] = {
            "exp": round(float(r.mean()), 3),
            "alvo": round(float((r >= ALVO_R).mean() * 100), 1),
            "stop": round(float((r <= -1).mean() * 100), 1),
            "risco": round(float(np.nanmedian(e["risco"]) * 100), 2),
        }
    return out


def relatorio(pasta: Path, saida: Path) -> None:
    import json

    t0 = time.time()
    d = pd.read_pickle(pasta / "linhas.pkl")
    with (pasta / "eventos.pkl").open("rb") as f:
        ev = pickle.load(f)
    sessoes: pd.DatetimeIndex = ev["sessoes"]
    c = camadas(d)
    gat, vol = c["gat"], c["vol"]
    todos = pd.Series(True, index=d.index)

    defs: list[tuple[str, str, pd.Series]] = [
        ("base", "Qualquer dia de papel líquido", todos),
        ("candle", "Candle de reversão em qualquer lugar", c["candle"]),
        ("toca", "Toque em suporte, sem candle de reversão", c["toca"] & ~c["candle"]),
        ("gat", "Candle de reversão no suporte (gatilho)", gat),
        ("gat_vol", "Gatilho com volume alto (≥ 1,5×)", gat & vol),
        ("gat_sem_vol", "Gatilho com volume normal ou baixo", gat & ~vol),
    ]
    contextos = (
        ("queda", "queda recente", d["queda"]),
        ("baixa", "tendência de baixa", d["baixa"]),
        ("lateral", "lateralização", c["lateral"]),
        ("correcao", "correção em alta", d["correcao"]),
    )
    nenhum = ~(d["queda"] | d["baixa"] | c["lateral"] | d["correcao"])
    for k, nome, m in contextos:
        defs.append((f"ctx_{k}", f"Qualquer dia em {nome}", m))
        defs.append((f"gat_{k}", f"Gatilho em {nome}", gat & m))
        defs.append((f"gat_vol_{k}", f"Gatilho + volume alto em {nome}", gat & vol & m))
    defs.append(("gat_nenhum", "Gatilho sem nenhum dos contextos", gat & nenhum))
    for k, nome in (
        ("martelo", "Martelo"),
        ("libelula", "Doji libélula"),
        ("engolfo", "Engolfo de alta"),
        ("piercing", "Piercing"),
        ("estrela", "Estrela da manhã"),
    ):
        defs.append((f"tipo_{k}", f"{nome} no suporte", gat & d[k]))
        defs.append((f"solto_{k}", f"{nome} em qualquer lugar", d[k]))
    # toques do suporte tocado pelo martelo/libelula (camada de 1 candle)
    martelos = (d["martelo"] | d["libelula"]) & (d["toca1_forca"] >= 2)
    t1 = d["toca1_forca"]
    for k, nome, m in (
        ("2", "2 toques", t1 == 2),
        ("3", "3 toques", t1 == 3),
        ("4", "4 toques", t1 == 4),
        ("5", "5 ou mais toques", t1 >= 5),
    ):
        defs.append((f"toques_{k}", f"Martelo/libélula em suporte de {nome}", martelos & m))
    defs += [
        ("furou", "Gatilho que furou e voltou", gat & c["furou"]),
        ("dentro", "Gatilho dentro da tolerância", gat & ~c["furou"]),
        ("virou", "Gatilho em resistência rompida (reteste)", gat & c["virou"]),
        ("nativo", "Gatilho em suporte que nunca foi rompido", gat & ~c["virou"]),
        ("z6", "Gatilho com 6σ nos 20 pregões anteriores", gat & d["z6"]),
        ("sem_z6", "Gatilho sem 6σ recente", gat & ~d["z6"]),
        ("rv_baixo", "Gatilho, volume < 1×", gat & (d["rvol"] < 1)),
        ("rv_medio", "Gatilho, volume 1–1,5×", gat & (d["rvol"] >= 1) & (d["rvol"] < 1.5)),
        ("rv_alto", "Gatilho, volume 1,5–2,5×", gat & (d["rvol"] >= 1.5) & (d["rvol"] < 2.5)),
        ("rv_muito", "Gatilho, volume ≥ 2,5×", gat & (d["rvol"] >= 2.5)),
        ("forca_rompe", "Candle de força rompendo resistência", c["forca"] & c["rompe"]),
        (
            "rompe_sem_forca",
            "Rompimento de resistência sem candle de força",
            c["rompe"] & ~c["forca"],
        ),
        ("forca_sup", "Candle de força saindo do suporte", c["forca"] & c["toca"]),
        ("forca_solto", "Candle de força em qualquer lugar", c["forca"]),
    ]

    grupos, periodos = [], {}
    for gid, nome, m in defs:
        e = d.loc[m.to_numpy()] if gid == "base" else _dedup(d, m)
        info = medir(e, sessoes)
        grupos.append({"id": gid, "nome": nome, **info})
        if gid in (
            "base",
            "candle",
            "toca",
            "gat",
            "gat_vol",
            "gat_baixa",
            "gat_queda",
            "gat_lateral",
            "ctx_baixa",
            "ctx_queda",
            "virou",
            "furou",
            "forca_rompe",
            "rv_muito",
            "rv_baixo",
        ):
            anos_e = sessoes.year.to_numpy()[e["s"].to_numpy()]
            periodos[gid] = {
                f"{a}–{b}": medir(e[(anos_e >= a) & (anos_e <= b)], sessoes) for a, b in PERIODOS
            }
            # o mesmo grupo sem papel abaixo de R$ 1 (os de centavos dos anos 90)
            periodos[gid]["sem centavos"] = medir(e[e["close"] >= 1.0], sessoes)
        print(f"{gid:16} n={info['n']:>8} ({time.time() - t0:.0f}s)", flush=True)

    eg = _dedup(d, gat)
    anos_g = sessoes.year.to_numpy()[eg["s"].to_numpy()]
    por_ano = []
    for a in range(1996, 2027):
        sel = eg[anos_g == a]
        x = sel["x20"].to_numpy(dtype=np.float64) * 100
        x = x[np.isfinite(x)]
        por_ano.append(
            {"ano": a, "n": len(sel), "media": round(float(x.mean()), 2) if len(x) else None}
        )

    meta = {
        "inicio": str(sessoes[0].date()),
        "fim": str(sessoes[-1].date()),
        "sessoes": len(sessoes),
        "linhas": len(d),
        "papeis": int(d["ticker"].nunique()),
        "por_dia": round(len(d) / d["s"].nunique(), 1),
        "gatilhos_por_dia": round(int(gat.sum()) / d["s"].nunique(), 2),
        **ev["resumo"],
        "despejos": ev["despejos"],
        "regras": {
            k: getattr(ev["regras"], k)
            for k in (
                "pivo",
                "tol_atr",
                "tol_min_pct",
                "furo_atr",
                "rompe_fech",
                "validade",
                "caixa_max_pct",
                "caixa_pregoes",
            )
        },
    }
    saida.write_text(
        json.dumps(
            {"meta": meta, "grupos": grupos, "periodos": periodos, "anos": por_ano},
            ensure_ascii=False,
        )
    )
    print(f"relatorio em {saida} ({time.time() - t0:.0f}s)")


# ---------------------------------------------------------------------------
# Etapa 3: exemplos sorteados para conferir no olho, e os papeis de hoje.
# ---------------------------------------------------------------------------

SEMENTE = 21
POR_TIPO = 8


def _barras_de(
    m: object, col: int, de: int, ate: int, sessoes: pd.DatetimeIndex
) -> list[list[object]]:
    o, h, low, c = (getattr(m, a)[:, col] for a in ("abertura", "maxima", "minima", "fechamento"))
    v = m.volume[:, col]
    out: list[list[object]] = []
    for i in range(max(de, 0), min(ate, len(sessoes) - 1) + 1):
        if np.isnan(c[i]):
            continue
        out.append(
            [
                str(sessoes[i].date()),
                *(float(f"{x:.6g}") for x in (o[i], h[i], low[i], c[i])),
                round(float(v[i]) / 1e3) if np.isfinite(v[i]) else 0,
            ]
        )
    return out


def _niveis_de(
    ev: dict[str, pd.DataFrame], ticker: str, de: int, ate: int, dia: int, sessoes: pd.DatetimeIndex
) -> list[dict[str, object]]:
    """Segmentos do papel que aparecem na janela, com o preco que tinham no `dia`."""
    # ids de segmento sao unicos dentro do papel (cada lote numera do zero)
    todos = ev["segmentos"][ev["segmentos"]["ticker"] == ticker]
    seg = todos[(todos["inicio"] <= ate) & (todos["fim"].isna() | (todos["fim"] >= de))]
    tq_papel = ev["toques"][ev["toques"]["ticker"] == ticker]
    tq = tq_papel[tq_papel["seg"].isin(seg["seg"])]
    out = []
    for _, sgm in seg.iterrows():
        meus = tq[tq["seg"] == sgm["seg"]]
        # o nivel troca de papel uma vez so: o historico e o lado de origem
        hist = int((tq_papel["seg"] == sgm["origem"]).sum()) if sgm["origem"] >= 0 else 0
        conhecidos = meus[meus["conf"] <= dia]
        preco = (
            float(conhecidos["preco_nivel"].iloc[-1])
            if len(conhecidos)
            else float(sgm["preco_inicial"])
        )
        if len(meus) + hist < 2:
            continue
        # dia em que o nivel passou a valer (3 toques contando o historico)
        falta = max(0, 3 - hist)
        vale = (
            int(meus["conf"].iloc[falta - 1])
            if falta and len(meus) >= falta
            else (int(sgm["inicio"]) if not falta else None)
        )
        ini = int(meus["dia"].iloc[0]) if sgm["origem"] < 0 and len(meus) else int(sgm["inicio"])
        fim = int(sgm["fim"]) if pd.notna(sgm["fim"]) else len(sessoes) - 1
        out.append(
            {
                "lado": int(sgm["lado"]),
                "preco": round(preco, 4),
                "virou": bool(sgm["origem"] >= 0),
                "de": str(sessoes[max(ini, de)].date()),
                "ate": str(sessoes[min(fim, ate)].date()),
                "vale": str(sessoes[vale].date()) if vale is not None and vale <= ate else None,
                "rompeu": str(sessoes[fim].date())
                if pd.notna(sgm["fim"]) and sgm["motivo"] == 1 and de <= fim <= ate
                else None,
                "toques": [
                    [str(sessoes[int(t.dia)].date()), bool(t.furo)]
                    for t in meus.itertuples()
                    if de <= t.dia <= ate
                ],
                "hist": hist,
            }
        )
    return out


def exemplos(pasta: Path, barras: Path, saida: Path) -> None:
    import json

    d = pd.read_pickle(pasta / "linhas.pkl")
    with (pasta / "eventos.pkl").open("rb") as f:
        ev = pickle.load(f)
    sessoes: pd.DatetimeIndex = ev["sessoes"]
    c = camadas(d)
    rng = np.random.default_rng(SEMENTE)

    def sorteia(mask: pd.Series, n: int = POR_TIPO) -> pd.DataFrame:
        # sem os papeis de centavos dos anos 90: o desenho fica ilegivel
        ok = (d["s"].to_numpy() < len(sessoes) - 25) & (d["close"].to_numpy() >= 1.0)
        e = _dedup(d, mask & pd.Series(ok, index=d.index))
        # um terco de cada decada, para o sorteio nao ficar todo em 2021
        anos_e = sessoes.year.to_numpy()[e["s"].to_numpy()]
        partes = []
        for a, b in PERIODOS:
            sub = e[(anos_e >= a) & (anos_e <= b)]
            k = min(len(sub), int(np.ceil(n / 3)))
            if k:
                partes.append(sub.iloc[rng.choice(len(sub), k, replace=False)])
        return pd.concat(partes).sort_values("s").head(n) if partes else e.head(0)

    # martelo e companhia so contam no suporte (decisao do usuario, 21/10)
    candles_sel = {
        k: sorteia(c["gat"] & d[k])
        for k in ("martelo", "libelula", "engolfo", "piercing", "estrela")
    }
    candles_sel["forca"] = sorteia(c["forca"] & (c["toca"] | c["rompe"]))
    escolhida = regra(d, c, *REGRA_ESCOLHIDA)
    niveis_sel = {
        "escolhida": sorteia(escolhida, 12),
        "destaque": sorteia(escolhida & (d["rvol"] >= 2.5)),
        "gat": sorteia(c["gat"]),
        "furou": sorteia(c["gat"] & c["furou"]),
        "virou": sorteia(c["gat"] & c["virou"]),
        "forca_rompe": sorteia(c["forca"] & c["rompe"]),
        "lateral": sorteia(c["lateral"] & (d["toca1_forca"] >= 2), 6),
    }

    precisa = sorted(
        {t for g in (*candles_sel.values(), *niveis_sel.values()) for t in g["ticker"]}
    )
    b = pd.read_pickle(barras)
    b["ticker"] = b["ticker"].astype(str)
    hoje = d[d["s"] == d["s"].max()]
    atuais = sorted(hoje["ticker"])
    m = montar(
        b[b["ticker"].isin(precisa + atuais)],
        precisa + [t for t in atuais if t not in precisa],
        sessoes,
    )
    colunas = {t: k for k, t in enumerate(m.tickers)}

    def linha_info(r: pd.Series) -> dict[str, object]:
        return {
            "rvol": round(float(r["rvol"]), 2) if np.isfinite(r["rvol"]) else None,
            "r20": round(float(r["r20"]) * 100, 1) if np.isfinite(r["r20"]) else None,
            "x20": round(float(r["x20"]) * 100, 1) if np.isfinite(r["x20"]) else None,
            "res_r": round(float(r["res_r"]), 2) if np.isfinite(r["res_r"]) else None,
            "ctx": [k for k in ("queda", "baixa", "correcao") if bool(r[k])]
            + (["lateral"] if np.isfinite(r["caixa"]) else []),
            "toques": int(max(r["toca1_forca"], r["toca2_forca"], r["toca3_forca"])),
            "risco": round(float(r["risco"]) * 100, 2) if np.isfinite(r["risco"]) else None,
            "espaco": round(float((r["res_preco"] - r["close"]) / (r["risco"] * r["close"])), 1)
            if np.isfinite(r["res_preco"]) and np.isfinite(r["risco"]) and r["risco"] > 0
            else None,
            "confirmou": bool(r["confirma"]),
            "res_r_conf": round(float(r["res_r_conf"]), 2)
            if np.isfinite(r["res_r_conf"])
            else None,
        }

    saida_d: dict[str, object] = {"candles": {}, "niveis": {}, "papeis": [], "hoje": None}
    for k, sel in candles_sel.items():
        saida_d["candles"][k] = [  # type: ignore[index]
            {
                "t": r.ticker,
                "dia": str(sessoes[r.s].date()),
                "barras": _barras_de(m, colunas[r.ticker], r.s - 14, r.s + 4, sessoes),
                **linha_info(pd.Series(r._asdict())),
            }
            for r in sel.itertuples()
        ]
    for k, sel in niveis_sel.items():
        lst = []
        for r in sel.itertuples():
            de, ate = r.s - 120, r.s + 25
            lst.append(
                {
                    "t": r.ticker,
                    "dia": str(sessoes[r.s].date()),
                    "barras": _barras_de(m, colunas[r.ticker], de, ate, sessoes),
                    "niveis": _niveis_de(ev, r.ticker, de, ate, r.s, sessoes),
                    **linha_info(pd.Series(r._asdict())),
                }
            )
        saida_d["niveis"][k] = lst  # type: ignore[index]

    # papeis de hoje: 250 pregoes, niveis com o preco de hoje e os gatilhos do periodo
    ult = int(d["s"].max())
    for t in atuais:
        de = ult - 249
        sel = d[(d["ticker"] == t) & (d["s"] >= de)]
        gat_t = sel[escolhida.loc[sel.index]]
        marcas = []
        for r in gat_t.itertuples():
            tipos = [
                k
                for k in ("martelo", "libelula", "engolfo", "piercing", "estrela")
                if getattr(r, k)
            ]
            marcas.append(
                [
                    str(sessoes[r.s].date()),
                    tipos,
                    bool(r.rvol >= 2.5),
                    bool(r.confirma) if r.s < ult else None,
                ]
            )
        ultima = sel[sel["s"] == ult].iloc[0]
        saida_d["papeis"].append(
            {  # type: ignore[attr-defined]
                "t": t,
                "barras": _barras_de(m, colunas[t], de, ult, sessoes),
                "niveis": _niveis_de(ev, t, de, ult, ult, sessoes),
                "marcas": marcas,
                "hoje": {
                    **linha_info(ultima),
                    "close": round(float(ultima["close"]), 2),
                    "candle": [
                        k
                        for k in ("martelo", "libelula", "engolfo", "piercing", "estrela", "forca")
                        if bool(ultima[k])
                    ],
                    "gat": bool(c["gat"].loc[ultima.name]),
                    "filtrado": bool(escolhida.loc[ultima.name]),
                    "queda": bool(ultima["queda"]),
                    "baixa": bool(ultima["baixa"]),
                    "sup": round(float(ultima["sup_preco"]), 2)
                    if np.isfinite(ultima["sup_preco"])
                    else None,
                    "sup_forca": int(ultima["sup_forca"]),
                    "res": round(float(ultima["res_preco"]), 2)
                    if np.isfinite(ultima["res_preco"])
                    else None,
                    "res_forca": int(ultima["res_forca"]),
                    "toca": bool(ultima["toca1_forca"] >= 3),
                    "furou": bool(ultima["toca1_furou"]),
                    "virou": bool(ultima["toca1_virou"]),
                    "z6": bool(ultima["z6"]),
                    "ret_ant": round(float(ultima["ret_ant"]) * 100, 1)
                    if np.isfinite(ultima["ret_ant"])
                    else None,
                },
            }
        )
    saida.write_text(json.dumps(saida_d, ensure_ascii=False, separators=(",", ":")))
    print(
        f"exemplos em {saida}: {len(saida.read_bytes()) // 1024} KB, {len(atuais)} papeis de hoje"
    )


# ---------------------------------------------------------------------------
# Etapa 4: validacao da regra escolhida. Cortes escolhidos so com 1995-2015,
# conferidos em 2016-2026; e a entrada com confirmacao.
# ---------------------------------------------------------------------------

DENTRO = (1995, 2015)
FORA = (2016, 2026)
REGRA_ESCOLHIDA = (1.5, True, 2.0)  # volume minimo, sem queda/baixa, espaco em R


def regra(
    d: pd.DataFrame,
    c: dict[str, pd.Series],
    vol_min: float,
    sem_ruim: bool,
    espaco: float,
    tipo: str = "reversao",
) -> pd.Series:
    """Gatilho filtrado: candle no suporte + volume + contexto + espaco ate a resistencia."""
    base = c["gat"] if tipo == "reversao" else c["forca"] & (c["toca"] | c["rompe"])
    m = base & (d["rvol"] >= vol_min) if vol_min > 0 else base.copy()
    if sem_ruim:
        m &= ~(d["queda"] | d["baixa"])
    if espaco > 0:
        risco = d["risco"] * d["close"]
        livre = (d["res_preco"] - d["close"]) / risco
        m &= (livre >= espaco) | d["res_preco"].isna()
    return m


def _confirmados(e: pd.DataFrame) -> pd.DataFrame:
    e = e[e["confirma"]].copy()
    for hz in HORIZONTES:
        e[f"x{hz}"] = e[f"xc{hz}"]
        e[f"r{hz}"] = e[f"rc{hz}"]
    e["res_r"] = e["res_r_conf"]
    return e


def validar(pasta: Path, saida: Path) -> None:
    import itertools
    import json

    d = pd.read_pickle(pasta / "linhas.pkl")
    with (pasta / "eventos.pkl").open("rb") as f:
        sessoes: pd.DatetimeIndex = pickle.load(f)["sessoes"]
    c = camadas(d)
    ano = pd.Series(sessoes.year.to_numpy()[d["s"].to_numpy()], index=d.index)
    dentro = ano.between(*DENTRO)
    fora = ano.between(*FORA)

    def resumo(m: pd.Series, onde: pd.Series) -> dict[str, object]:
        e = _dedup(d, m & onde)
        out = medir(e, sessoes)
        ec = _confirmados(e)
        out["confirmados"] = round(len(ec) / max(len(e), 1) * 100, 1)
        out["conf"] = medir(ec, sessoes) if len(ec) >= 30 else None
        return out

    grade = []
    for vol, ruim, esp in itertools.product(
        (0.0, 1.5, 2.0, 2.5), (False, True), (0.0, 1.0, 2.0, 3.0)
    ):
        e = _dedup(d, regra(d, c, vol, ruim, esp) & dentro)
        if len(e) < 300:
            continue
        info = medir(e, sessoes)
        grade.append(
            {
                "vol": vol,
                "sem_ruim": ruim,
                "espaco": esp,
                "n": len(e),
                "dentro": info["20"],
                "r": info.get("r"),
            }
        )
    grade.sort(key=lambda g: g["dentro"]["mensal"], reverse=True)
    for pos, g in enumerate(grade, 1):
        g["posicao"] = pos
        g["fora"] = medir(
            _dedup(d, regra(d, c, g["vol"], g["sem_ruim"], g["espaco"]) & fora), sessoes
        )["20"]

    escolhida = regra(d, c, *REGRA_ESCOLHIDA)
    destaque = regra(d, c, 2.5, True, 2.0)
    forca = regra(d, c, 1.5, True, 2.0, tipo="forca")
    todos = pd.Series(True, index=d.index)
    blocos = {}
    for nome, m in (
        ("gat", c["gat"]),
        ("escolhida", escolhida),
        ("destaque", destaque),
        ("forca", forca),
    ):
        blocos[nome] = {
            "dentro": resumo(m, dentro),
            "fora": resumo(m, fora),
            "tudo": resumo(m, todos),
        }
        print(
            nome,
            {
                k: (
                    v["n"],
                    v["20"]["mensal"] if v.get("20") else None,
                    v["20"]["ic"] if v.get("20") else None,
                    v["confirmados"],
                    v["conf"]["20"]["mensal"] if v.get("conf") else None,
                    (v.get("r") or {}).get("exp"),
                    ((v.get("conf") or {}).get("r") or {}).get("exp"),
                )
                for k, v in blocos[nome].items()
            },
            flush=True,
        )

    # lista de hoje com a regra escolhida
    ult = int(d["s"].max())
    hoje = d[(d["s"] == ult) & escolhida]
    lista = [
        {"t": r.ticker, "rvol": round(float(r.rvol), 2), "destaque": bool(r.rvol >= 2.5)}
        for r in hoje.itertuples()
    ]
    por_semana = len(_dedup(d, escolhida & (ano >= 2025))) / (d.loc[ano >= 2025, "s"].nunique() / 5)
    saida.write_text(
        json.dumps(
            {"grade": grade, "blocos": blocos, "hoje": lista, "por_semana": round(por_semana, 2)},
            ensure_ascii=False,
        )
    )
    print(
        "melhor dentro:",
        {k: grade[0][k] for k in ("vol", "sem_ruim", "espaco", "n")},
        grade[0]["dentro"]["mensal"],
        "fora",
        grade[0]["fora"]["mensal"],
        grade[0]["fora"]["ic"],
    )
    pos = next(g for g in grade if (g["vol"], g["sem_ruim"], g["espaco"]) == REGRA_ESCOLHIDA)
    print(
        "escolhida: posicao",
        pos["posicao"],
        "de",
        len(grade),
        "dentro",
        pos["dentro"]["mensal"],
        "fora",
        pos["fora"]["mensal"],
        pos["fora"]["ic"],
    )
    for g in grade[:8]:
        print(
            g["vol"],
            g["sem_ruim"],
            g["espaco"],
            g["n"],
            g["dentro"]["mensal"],
            g["dentro"]["ic"],
            "| fora",
            g["fora"]["mensal"],
            g["fora"]["ic"],
        )
    print("hoje:", lista, "por semana 2025-26:", round(por_semana, 2))


# ---------------------------------------------------------------------------
# Etapa 5: media movel como suporte (MME 9 e MMA 20, em tendencia).
# ---------------------------------------------------------------------------


def _filtrar(
    d: pd.DataFrame, base: pd.Series, vol: float, sem_ruim: bool, espaco: float
) -> pd.Series:
    m = base & (d["rvol"] >= vol) if vol > 0 else base.copy()
    if sem_ruim:
        m &= ~(d["queda"] | d["baixa"])
    if espaco > 0:
        livre = (d["res_preco"] - d["close"]) / (d["risco"] * d["close"])
        m &= (livre >= espaco) | d["res_preco"].isna()
    return m


def validar_medias(pasta: Path, saida: Path) -> None:
    import json

    d = pd.read_pickle(pasta / "linhas.pkl")
    with (pasta / "eventos.pkl").open("rb") as f:
        sessoes: pd.DatetimeIndex = pickle.load(f)["sessoes"]
    c = camadas(d)
    rev1, rev2, rev3 = c["rev1"], c["rev2"], d["estrela"]

    def na_media(nm: str) -> pd.Series:
        return (rev1 & d[f"{nm}_toca1"]) | (rev2 & d[f"{nm}_toca2"]) | (rev3 & d[f"{nm}_toca3"])

    mme9, mma20 = na_media("mme9"), na_media("mma20")
    media = mme9 | mma20
    ano = pd.Series(sessoes.year.to_numpy()[d["s"].to_numpy()], index=d.index)
    partes = {"dentro": ano.between(*DENTRO), "fora": ano.between(*FORA), "tudo": ano > 0}

    def resumo(m: pd.Series, onde: pd.Series) -> dict[str, object]:
        e = _dedup(d, m & onde)
        out = medir(e, sessoes)
        ec = _confirmados(e)
        out["confirmados"] = round(len(ec) / max(len(e), 1) * 100, 1)
        out["conf"] = medir(ec, sessoes) if len(ec) >= 30 else None
        return out

    regra_atual = _filtrar(d, c["gat"], 1.5, True, 2.0)
    grupos = {
        "candle_qualquer": ("Candle de reversão em qualquer lugar", c["candle"]),
        "media_sem_filtro": ("Candle na média, sem filtro", media),
        "mme9_sem_filtro": ("Candle na MME 9, sem filtro", mme9),
        "mma20_sem_filtro": ("Candle na MMA 20, sem filtro", mma20),
        "media_filtros": ("Candle na média + filtros da aba", _filtrar(d, media, 1.5, True, 2.0)),
        "mme9_filtros": ("Candle na MME 9 + filtros", _filtrar(d, mme9, 1.5, True, 2.0)),
        "mma20_filtros": ("Candle na MMA 20 + filtros", _filtrar(d, mma20, 1.5, True, 2.0)),
        "media_destaque": (
            "Candle na média + filtros, volume ≥ 2,5×",
            _filtrar(d, media, 2.5, True, 2.0),
        ),
        "media_sem_espaco": (
            "Candle na média, volume e contexto, sem exigir espaço",
            _filtrar(d, media, 1.5, True, 0.0),
        ),
        "so_media_filtros": (
            "Só na média (fora do suporte horizontal) + filtros",
            _filtrar(d, media & ~c["gat"], 1.5, True, 2.0),
        ),
        "regra_atual": ("Regra atual (suporte horizontal + filtros)", regra_atual),
        "uniao": (
            "Suporte horizontal OU média + filtros",
            _filtrar(d, c["gat"] | media, 1.5, True, 2.0),
        ),
    }
    out: dict[str, object] = {}
    for gid, (nome_grupo, m) in grupos.items():
        out[gid] = {"nome": nome_grupo, **{p: resumo(m, onde) for p, onde in partes.items()}}
        b = out[gid]
        f20 = lambda x: (x["n"], (x.get("20") or {}).get("mensal"), (x.get("20") or {}).get("ic"))  # noqa: E731
        print(
            f"{gid:18} dentro {f20(b['dentro'])}  fora {f20(b['fora'])}  "
            f"R {(b['tudo'].get('r') or {}).get('exp')} -> "
            f"conf {((b['tudo'].get('conf') or {}).get('r') or {}).get('exp')}",
            flush=True,
        )
    recente = ano >= 2025
    semanas = d.loc[recente, "s"].nunique() / 5
    out["por_semana"] = {
        k: round(len(_dedup(d, grupos[k][1] & recente)) / semanas, 2)
        for k in ("regra_atual", "media_filtros", "so_media_filtros", "uniao")
    }
    print("por semana 2025-26:", out["por_semana"])
    saida.write_text(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    if sys.argv[1] == "processar":
        regras = replace(Regras(), toques_min=2)
        if len(sys.argv) > 4:
            regras = replace(regras, tol_atr=float(sys.argv[4]), pivo=int(sys.argv[5]))
        processar(Path(sys.argv[2]), Path(sys.argv[3]), regras)
    elif sys.argv[1] == "relatorio":
        relatorio(Path(sys.argv[2]), Path(sys.argv[3]))
    elif sys.argv[1] == "validar":
        validar(Path(sys.argv[2]), Path(sys.argv[3]))
    elif sys.argv[1] == "medias":
        validar_medias(Path(sys.argv[2]), Path(sys.argv[3]))
    elif sys.argv[1] == "exemplos":
        exemplos(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
