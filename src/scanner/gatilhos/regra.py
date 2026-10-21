"""A regra dos Setups: candle de reversao no suporte, filtrado.

Decisoes do usuario em 21/10/2026, validadas no estudo de 30 anos de COTAHIST
(`scripts/gatilhos_estudo.py`, cortes escolhidos com 1995-2015 e conferidos em
2016-2026):

- candle de reversao (martelo, doji libelula, engolfo, piercing, estrela da
  manha) com a minima do padrao num suporte de 3 ou mais toques. Martelo no
  meio do movimento nao conta;
- volume do dia de 1,5x a mediana dos 20 pregoes anteriores ou mais (destaque
  a partir de 2,5x);
- fora de queda recente e de tendencia de baixa;
- resistencia mais proxima a pelo menos 2 vezes o risco (fechamento menos a
  minima do padrao), ou nenhuma resistencia acima.

O candle de forca (saindo do suporte ou rompendo resistencia, com os mesmos
filtros) sai como categoria a parte: passou em 1995-2015 e falhou em
2016-2026, e a aba mostra isso.

Os precos que saem daqui estao na escala do PROPRIO dia de cada linha, como o
COTAHIST os publicou: o grafico do site nao ajusta desdobramento, e o nivel tem
de cair onde o candle esta desenhado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt
import pandas as pd

from scanner.config import SetupsConfig, UniverseConfig
from scanner.gatilhos.candles import padroes
from scanner.gatilhos.contexto import atr_wilder, calcular
from scanner.gatilhos.matrizes import Matrizes, ajuste_acumulado, montar
from scanner.gatilhos.medias import RegrasDaMedia, toques_na_media
from scanner.gatilhos.niveis import ROMPEU, Eventos, Regras, Retrato, detectar

F64 = npt.NDArray[np.float64]
B = npt.NDArray[np.bool_]

REVERSAO = ("martelo", "libelula", "engolfo", "piercing", "estrela")
# Camada de toque de cada padrao: a minima de 1, 2 ou 3 candles toca o suporte.
CAMADA = {"martelo": 0, "libelula": 0, "engolfo": 1, "piercing": 1, "estrela": 2}

COLUNAS_SETUP = (
    "ticker",
    "trade_date",
    "categoria",
    "padroes",
    "toques",
    "virou",
    "furou",
    "rvol",
    "destaque",
    "contexto",
    "fechamento",
    "maxima",
    "minima",
    "suporte",
    "suporte_tipo",
    "resistencia",
    "espaco_r",
    "risco_pct",
)
COLUNAS_NIVEL = (
    "ticker",
    "lado",
    "preco",
    "de",
    "ate",
    "vale_desde",
    "rompido_em",
    "virou",
    "ativo",
    "toques",
)


@dataclass(frozen=True)
class Analise:
    """O motor rodado uma vez sobre a janela; setups e niveis saem daqui."""

    m: Matrizes
    # Multiplicador de cada dia para a escala do ultimo dia da janela.
    ajuste: F64
    atr: F64
    contexto: dict[str, F64 | B]
    padroes: dict[str, B]
    retrato: Retrato
    eventos: Eventos
    liquido: B
    # Por media (mme9, mma20): valores e toque em tendencia, (3, dias, papeis).
    medias: dict[str, tuple[F64, B]]


def liquidez(volume: F64, universo: UniverseConfig) -> B:
    """Papel liquido em cada dia, sem olhar o futuro (os N pregoes ANTERIORES).

    A mesma regra do universo do scanner (`universe.py`), so que dia a dia:
    mediana do volume acima do piso e negocio em ao menos a fracao minima dos
    pregoes da janela.
    """
    n = universo.lookback_sessions
    minimo = int(np.ceil(n * universo.min_session_coverage))
    janela = pd.DataFrame(volume).shift(1).rolling(n, min_periods=minimo)
    mediana = janela.median().to_numpy(dtype=np.float64)
    with np.errstate(invalid="ignore"):
        return np.asarray(mediana >= universo.min_median_volume_brl, dtype=bool)


def analisar(barras: pd.DataFrame, cfg: SetupsConfig, universo: UniverseConfig) -> Analise:
    """Roda candles, contexto e niveis sobre todas as barras de uma vez."""
    m = montar(barras)
    atr = atr_wilder(m.maxima, m.minima, m.fechamento)
    ctx = calcular(m.maxima, m.fechamento, m.volume)
    pad = padroes(m.abertura, m.maxima, m.minima, m.fechamento, atr)
    retrato, eventos = detectar(
        m.maxima, m.minima, m.fechamento, atr, Regras(toques_min=cfg.toques_nivel)
    )
    return Analise(
        m=m,
        ajuste=ajuste_acumulado(m.fator),
        atr=atr,
        contexto=ctx,
        padroes=pad,
        retrato=retrato,
        eventos=eventos,
        liquido=liquidez(m.volume, universo),
        medias=toques_na_media(
            m.minima, m.fechamento, atr, RegrasDaMedia(medias=tuple(cfg.medias))
        ),
    )


def _janela_min(m: F64, n: int) -> F64:
    return pd.DataFrame(m).rolling(n, min_periods=1).min().to_numpy(dtype=np.float64)


def setups(a: Analise, cfg: SetupsConfig) -> pd.DataFrame:
    """Todos os setups da janela, um por (papel, dia, categoria)."""
    m, ret, pad, ctx = a.m, a.retrato, a.padroes, a.contexto
    c = m.fechamento
    toca = [ret.toca_forca[k] >= cfg.toques_gatilho for k in range(3)]
    em = {p: pad[p] & toca[CAMADA[p]] for p in REVERSAO}
    reversao = np.logical_or.reduce([em[p] for p in REVERSAO])
    rompe = ret.rompeu_res_forca >= cfg.toques_gatilho
    # na media: o mesmo candle, encostando numa media em tendencia de alta
    nomes_media = list(a.medias)
    toca_media = [
        np.logical_or.reduce([a.medias[n][1][k] for n in nomes_media])
        if nomes_media
        else np.zeros_like(toca[k])
        for k in range(3)
    ]
    em_media = {p: pad[p] & toca_media[CAMADA[p]] for p in REVERSAO}
    na_media = np.logical_or.reduce([em_media[p] for p in REVERSAO]) & ~reversao
    forca = pad["forca"] & (toca[0] | rompe) & ~na_media

    # Stop = minima do padrao (o tamanho vem do padrao do dia, como no estudo).
    tam = np.where(pad["estrela"], 3, np.where(pad["engolfo"] | pad["piercing"], 2, 1))
    stop = np.where(
        tam == 3, _janela_min(m.minima, 3), np.where(tam == 2, _janela_min(m.minima, 2), m.minima)
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        risco = c - stop
        espaco = (ret.res_preco - c) / risco
        rvol = np.asarray(ctx["rvol"], dtype=np.float64)
        filtro = (
            a.liquido
            & (rvol >= cfg.volume_minimo)
            & ~np.asarray(ctx["queda"], dtype=bool)
            & ~np.asarray(ctx["baixa"], dtype=bool)
            & ((espaco >= cfg.espaco_minimo_r) | np.isnan(ret.res_preco))
            & (risco > 0)
        )

    partes = []
    for categoria, sinal in (
        ("reversao", reversao),
        ("media", na_media),
        ("forca", forca & ~reversao),
    ):
        dd, tt = np.nonzero(sinal & filtro)
        if dd.size == 0:
            continue
        # camada do toque: a do maior padrao no suporte (estrela > engolfo/piercing > martelo)
        if categoria == "reversao":
            camada = np.where(
                em["estrela"][dd, tt], 2, np.where((em["engolfo"] | em["piercing"])[dd, tt], 1, 0)
            )
            nomes = [[p for p in REVERSAO if em[p][d, t]] for d, t in zip(dd, tt, strict=True)]
            sup = ret.toca_preco[camada, dd, tt]
            toques = ret.toca_forca[camada, dd, tt]
            virou = ret.toca_virou[camada, dd, tt]
            furou = ret.toca_furou[camada, dd, tt]
            tipo = ["nivel"] * dd.size
        elif categoria == "media":
            camada = np.where(
                em_media["estrela"][dd, tt],
                2,
                np.where((em_media["engolfo"] | em_media["piercing"])[dd, tt], 1, 0),
            )
            nomes = [
                [p for p in REVERSAO if em_media[p][d, t]] for d, t in zip(dd, tt, strict=True)
            ]
            # a media tocada (as duas, quando o candle encosta nas duas)
            tocadas = np.stack([a.medias[n][1][camada, dd, tt] for n in nomes_media])
            valores = np.stack([a.medias[n][0][dd, tt] for n in nomes_media])
            # das tocadas, a mais perto da minima do padrao vira o "suporte"
            dist = np.where(tocadas, np.abs(valores - stop[dd, tt]), np.inf)
            sup = valores[np.argmin(dist, axis=0), np.arange(dd.size)]
            tipo = [
                ",".join(n for n, t in zip(nomes_media, tocadas[:, i], strict=True) if t)
                for i in range(dd.size)
            ]
            toques = np.zeros(dd.size, dtype=int)
            virou = np.zeros(dd.size, dtype=bool)
            tol = np.fmax(0.5 * a.atr[dd, tt], 0.004 * c[dd, tt])
            furou = stop[dd, tt] < sup - tol
        else:
            no_suporte = toca[0][dd, tt]
            nomes = [["forca"]] * dd.size
            sup = np.where(no_suporte, ret.toca_preco[0, dd, tt], ret.rompeu_res_preco[dd, tt])
            toques = np.where(no_suporte, ret.toca_forca[0, dd, tt], ret.rompeu_res_forca[dd, tt])
            virou = np.where(no_suporte, ret.toca_virou[0, dd, tt], False)
            furou = np.where(no_suporte, ret.toca_furou[0, dd, tt], False)
            tipo = ["nivel"] * dd.size
        escala = a.ajuste[dd, tt]  # volta cada preco para a escala do proprio dia
        lateral = ~np.isnan(ret.caixa_altura[dd, tt])
        correcao = np.asarray(ctx["correcao"], dtype=bool)[dd, tt]
        partes.append(
            pd.DataFrame(
                {
                    "ticker": np.asarray(m.tickers)[tt],
                    "trade_date": m.datas[dd].date,
                    "categoria": categoria,
                    "padroes": nomes,
                    "toques": toques.astype(int),
                    "virou": virou.astype(bool),
                    "furou": furou.astype(bool),
                    "rvol": rvol[dd, tt],
                    "destaque": rvol[dd, tt] >= cfg.volume_destaque,
                    "contexto": [
                        [n for n, f in (("lateral", la), ("correcao", co)) if f]
                        for la, co in zip(lateral, correcao, strict=True)
                    ],
                    "fechamento": c[dd, tt] / escala,
                    "maxima": m.maxima[dd, tt] / escala,
                    "minima": stop[dd, tt] / escala,
                    "suporte": sup / escala,
                    "suporte_tipo": tipo,
                    "resistencia": ret.res_preco[dd, tt] / escala,
                    "espaco_r": espaco[dd, tt],
                    "risco_pct": risco[dd, tt] / c[dd, tt] * 100,
                }
            )
        )
    if not partes:
        return pd.DataFrame({k: pd.Series(dtype="object") for k in COLUNAS_SETUP})
    saida = pd.concat(partes, ignore_index=True)
    return saida.sort_values(["trade_date", "ticker"]).reset_index(drop=True)


def niveis(a: Analise, cfg: SetupsConfig) -> pd.DataFrame:
    """Segmentos de suporte e resistencia para desenhar na ficha.

    Um segmento por nivel e papel (suporte e resistencia sao segmentos
    diferentes do mesmo nivel quando ele troca de papel). Entra quem chegou a
    `toques_nivel` contando o lado anterior. `vale_desde` e o dia em que chegou
    a `toques_gatilho` -- antes disso a linha e pontilhada. Segmento que
    atravessa um desdobramento fica de fora: nao ha uma escala so para ele.
    """
    seg = a.eventos.segmentos
    tq = a.eventos.toques
    vazio = pd.DataFrame({k: pd.Series(dtype="object") for k in COLUNAS_NIVEL})
    if seg.empty:
        return vazio
    ultimo = len(a.m.datas) - 1
    tq = tq.sort_values(["col", "seg", "conf", "dia"])
    tq = tq.assign(ordem=tq.groupby(["col", "seg"]).cumcount() + 1)
    proprios = tq.groupby(["col", "seg"]).agg(
        n=("dia", "size"), primeiro=("dia", "min"), preco_atual=("preco_nivel", "last")
    )
    s = seg.join(proprios, on=["col", "seg"])
    s["n"] = s["n"].fillna(0).astype(int)
    hist = proprios["n"].rename("hist")
    s = s.join(hist, on=["col", "origem"])
    s["hist"] = s["hist"].fillna(0).astype(int)
    s = s[(s["n"] + s["hist"] >= cfg.toques_nivel) & (s["motivo"] != 4)]
    if s.empty:
        return vazio

    # dia em que passou a valer: o toque (n - hist) que completou toques_gatilho
    falta = (cfg.toques_gatilho - s["hist"]).clip(lower=0)
    chave = tq.set_index(["col", "seg", "ordem"])["conf"]
    idx = pd.MultiIndex.from_arrays([s["col"], s["seg"], falta.where(falta > 0, 1)])
    conf_k = pd.Series(chave.reindex(idx).to_numpy(), index=s.index)
    s["vale"] = np.where(falta == 0, s["inicio"], conf_k)

    de = np.where(s["origem"] < 0, s["primeiro"].fillna(s["inicio"]), s["inicio"]).astype(int)
    ate = s["fim"].fillna(ultimo).astype(int).to_numpy()
    col = s["col"].astype(int).to_numpy()
    escala_de, escala_ate = a.ajuste[de, col], a.ajuste[ate, col]
    preco = np.where(
        s["motivo"].notna(), s["preco_final"], s["preco_atual"].fillna(s["preco_inicial"])
    )
    ok = np.isclose(escala_de, escala_ate)
    datas = a.m.datas
    toques_lista = tq.groupby(["col", "seg"])[["dia", "furo"]].apply(
        lambda g: [
            [str(datas[int(d)].date()), bool(f)] for d, f in zip(g["dia"], g["furo"], strict=True)
        ]
    )
    lista = toques_lista.reindex(pd.MultiIndex.from_arrays([s["col"], s["seg"]]))
    vale = s["vale"].to_numpy(dtype=np.float64)
    out = pd.DataFrame(
        {
            "ticker": np.asarray(a.m.tickers)[col],
            "lado": np.where(s["lado"] > 0, "suporte", "resistencia"),
            "preco": preco / escala_ate,
            "de": datas[de].date,
            "ate": datas[ate].date,
            "vale_desde": [
                datas[int(v)].date() if np.isfinite(v) and v <= u else None
                for v, u in zip(vale, ate, strict=True)
            ],
            "rompido_em": [
                datas[int(f)].date() if mo == ROMPEU else None
                for f, mo in zip(s["fim"].fillna(-1), s["motivo"], strict=True)
            ],
            "virou": (s["origem"] >= 0).to_numpy(),
            "ativo": s["motivo"].isna().to_numpy(),
            "toques": [x if isinstance(x, list) else [] for x in lista.to_numpy()],
        }
    )
    return cast(pd.DataFrame, out[ok].reset_index(drop=True))
