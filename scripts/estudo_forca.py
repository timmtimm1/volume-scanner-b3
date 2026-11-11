"""Variacoes do setup Forca: mais sinais e stop mais curto (estudo, nao produto).

Pedido do usuario em 11/11/2026. O Forca e o unico setup firme, mas arma pouco
(uns 40 trades por ano no mercado inteiro) e o stop na minima do candle fica
longe, o que deixa o lote pequeno com pouco capital. Duas perguntas:

1. Existe uma versao do sinal que arme mais sem perder a vantagem?
2. Um stop mais curto mantem o resultado?

Sete sinais (todos com o candle de forca: verde, corpo largo, fechando no
quarto de cima):

- `casa`: a regra de hoje (corpo >= 1,2 ATR, saindo de suporte ou rompendo
  resistencia de 3+ toques, volume >= 1,5x, fora de queda e de baixa, espaco);
- `casa_2toques`: a de hoje com nivel de 2+ toques;
- `casa_corpo10`: a de hoje com corpo >= 1,0 ATR;
- `livre`: sem exigir nivel (so o candle, o volume e o contexto);
- `livre_sem_volume`: `livre` sem o filtro de volume;
- `livre_corpo15`: `livre` com corpo >= 1,5 ATR;
- `maxima20`: `livre` fechando acima da maxima dos 20 pregoes anteriores.

Quatro stops: `min` (minima do candle, o de hoje), `meio` (meio do candle),
`atr10` (1 ATR abaixo da entrada) e `atr05` (0,5 ATR abaixo da entrada).

Sao 28 combinacoes, cada uma com as cinco saidas e os tres grupos de tendencia.
Protocolo de sempre: a melhor saida e tendencia de cada combinacao e escolhida
so com 1995-2015 e conferida uma vez em 2016-2026; o relatorio traz o criterio
rigido (Bonferroni sobre as 28).

    python scripts/estudo_forca.py processar <barras.pkl> <pasta>
    python scripts/estudo_forca.py relatorio <pasta>
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from estudo_candles import SEMENTE, por_mes, relatorio

from scanner.backtest.suite import liquidez_historica, trades_dos_sinais
from scanner.config import SetupsConfig, load_config
from scanner.gatilhos.candles import padroes
from scanner.gatilhos.classicos import CENTAVO, Sinal
from scanner.gatilhos.contexto import atr_wilder, calcular
from scanner.gatilhos.matrizes import Matrizes, ajuste_acumulado, montar
from scanner.gatilhos.medias import RegrasDaMedia, toques_na_media
from scanner.gatilhos.niveis import Regras, detectar
from scanner.gatilhos.regra import CAMADA, REVERSAO

F64 = npt.NDArray[np.float64]
B = npt.NDArray[np.bool_]

LOTE = int(os.environ.get("BACKTEST_LOTE", "100"))


def candle_de_forca(o: F64, h: F64, low: F64, c: F64, atr: F64, corpo_min: float) -> B:
    """Verde, corpo >= `corpo_min` ATR, fechando no quarto de cima (como em `candles.py`)."""
    with np.errstate(invalid="ignore"):
        return np.asarray(
            (c > o) & ((c - o) >= corpo_min * atr) & ((c - low) >= 0.75 * (h - low)), dtype=bool
        )


def sinais_do_forca(m: Matrizes, cfg: SetupsConfig, tick: F64) -> dict[str, Sinal]:
    o, h, low, c = m.abertura, m.maxima, m.minima, m.fechamento
    atr = atr_wilder(h, low, c)
    ctx = calcular(h, c, m.volume)
    pad = padroes(o, h, low, c, atr)
    ret, _ = detectar(h, low, c, atr, Regras(toques_min=cfg.toques_nivel))
    medias = toques_na_media(low, c, atr, RegrasDaMedia(medias=tuple(cfg.medias)))

    # as mesmas pecas de `regra.setups`
    def do_nivel(toques: int) -> tuple[B, B]:
        toca = [ret.toca_forca[k] >= toques for k in range(3)]
        reversao = np.logical_or.reduce([pad[p] & toca[CAMADA[p]] for p in REVERSAO])
        toca_media = [np.logical_or.reduce([medias[n][1][k] for n in medias]) for k in range(3)]
        na_media = np.logical_or.reduce([pad[p] & toca_media[CAMADA[p]] for p in REVERSAO])
        na_media &= ~reversao
        nivel = (toca[0] | (ret.rompeu_res_forca >= toques)) & ~na_media & ~reversao
        return np.asarray(nivel, dtype=bool), reversao

    with np.errstate(invalid="ignore", divide="ignore"):
        risco = c - low
        espaco = (ret.res_preco - c) / risco
        rvol = np.asarray(ctx["rvol"], dtype=np.float64)
        volume = rvol >= cfg.volume_minimo
        contexto = (
            ~np.asarray(ctx["queda"], dtype=bool) & ~np.asarray(ctx["baixa"], dtype=bool)
        ) & (risco > 0)
        tem_espaco = (espaco >= cfg.espaco_minimo_r) | np.isnan(ret.res_preco)
        topo20 = pd.DataFrame(h).shift(1).rolling(20, min_periods=20).max().to_numpy()
        acima = c > topo20

    f10, f12, f15 = (candle_de_forca(o, h, low, c, atr, k) for k in (1.0, 1.2, 1.5))
    nivel3, _ = do_nivel(cfg.toques_gatilho)
    nivel2, _ = do_nivel(2)
    armados = {
        "casa": f12 & nivel3 & volume & contexto & tem_espaco,
        "casa_2toques": f12 & nivel2 & volume & contexto & tem_espaco,
        "casa_corpo10": f10 & nivel3 & volume & contexto & tem_espaco,
        "livre": f12 & volume & contexto,
        "livre_sem_volume": f12 & contexto,
        "livre_corpo15": f15 & volume & contexto,
        "maxima20": f12 & volume & contexto & acima,
    }
    gatilho = h + tick
    stops = {
        "min": low - tick,
        "meio": (h + low) / 2,
        "atr10": gatilho - 1.0 * atr,
        "atr05": gatilho - 0.5 * atr,
    }
    return {
        f"{nome}/{s}": Sinal(armado=np.asarray(a, dtype=bool), gatilho=gatilho, stop=stop)
        for nome, a in armados.items()
        for s, stop in stops.items()
    }


def processar(barras_pkl: Path, pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    cfg = load_config(Path(__file__).resolve().parents[1] / "config.yaml").setups
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
        sinais = sinais_do_forca(m, cfg, tick)
        ctx = calcular(m.maxima, m.fechamento, m.volume)
        partes = []
        for i, (nome, sinal) in enumerate(sinais.items()):
            rng = np.random.default_rng([SEMENTE, k, i])
            trades = trades_dos_sinais(m, {nome: sinal}, liquido, tick, ajuste, ctx, rng)
            if not trades.empty:
                partes.append(por_mes(trades))
        pd.concat(partes, ignore_index=True).to_pickle(destino)
        print(f"lote {k + 1}/{len(lotes)}: {time.time() - t1:.0f}s", flush=True)


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
