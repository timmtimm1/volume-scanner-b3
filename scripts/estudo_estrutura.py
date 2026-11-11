"""Padroes de estrutura com entrada clara, na suite de backtest (estudo, nao produto).

Pedido do usuario em 11/11/2026: modelos de padrao com definicao fechada e
entrada clara, testados. As ideias vem dos projetos abertos pesquisados
(TechnicalAnalysisAutomation: bandeira e quebra de estrutura;
smart-money-concepts: gap de valor justo; stock-pattern: fundo duplo e contracao
de volatilidade) e dos classicos de rompimento (Donchian, NR7, gap com volume).
Nenhum codigo deles foi copiado: cada padrao foi reescrito como regra sobre as
matrizes pregao x papel, com o que se sabe ate o fechamento do dia do sinal.

Os modelos (ATR = ATR de 14 de Wilder; pivo = topo ou fundo com 3 pregoes de
cada lado, conhecido 3 pregoes depois):

- `bandeira`: mastro de 3+ ATR em ate 10 pregoes; depois 7 pregoes de pausa que
  devolvem no maximo metade do mastro e nao passam do topo dele. Compra acima
  da maxima da pausa; stop abaixo da minima da pausa.
- `fundo_duplo`: dois fundos pivo a no maximo 0,5 ATR um do outro, separados por
  8 a 60 pregoes, com um repique de 2+ ATR entre eles. Compra acima do topo do
  repique (o pescoco), enquanto o preco esta a ate 1,5 ATR dele; stop abaixo
  do fundo mais baixo.
- `quebra_estrutura`: os dois ultimos topos pivo e os dois ultimos fundos pivo
  descendo (estrutura de baixa), e o dia fecha acima do ultimo topo pela
  primeira vez. Compra acima da maxima do dia; stop abaixo do ultimo fundo.
- `fvg`: gap de valor justo de alta (a minima de um dia acima da maxima de dois
  dias antes, com o candle do meio de corpo 1+ ATR). Nos 10 pregoes seguintes,
  o primeiro dia que volta para dentro da zona sem fura-la e fecha acima dela.
  Compra acima da maxima desse dia; stop abaixo do fundo da zona.
- `contracao`: tres blocos seguidos de 10 pregoes, cada um com amplitude menor
  que 70% do anterior, e o ultimo a ate 1 ATR da maxima de 60 pregoes. Compra
  acima da maxima do ultimo bloco; stop abaixo da minima dele.
- `nr7`: a menor amplitude dos ultimos 7 pregoes. Compra acima da maxima do
  dia; stop abaixo da minima.
- `donchian20` e `donchian55`: compra acima da maxima de 20 (ou 55) pregoes;
  stop 2 ATR abaixo.
- `gap_volume`: abre acima da maxima da vespera e nao fecha o gap, fecha acima
  da abertura, volume 2x ou mais. Compra acima da maxima; stop abaixo da minima.
- `rompe_resistencia`: fecha acima de uma resistencia de 3+ toques (o motor de
  niveis da casa), com volume 1,5x ou mais. Compra acima da maxima; stop abaixo
  da minima.

Cada modelo roda com o stop proprio (`/padrao`) e com 1 ATR abaixo da entrada
(`/atr10`): 20 combinacoes, cada uma com as cinco saidas e os tres grupos de
tendencia. Protocolo de sempre (escolher em 1995-2015, conferir em 2016-2026) e
o criterio rigido do relatorio (Bonferroni sobre as 20).

    python scripts/estudo_estrutura.py processar <barras.pkl> <pasta>
    python scripts/estudo_estrutura.py relatorio <pasta>
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
from scanner.gatilhos.classicos import CENTAVO, Sinal
from scanner.gatilhos.contexto import atr_wilder, calcular
from scanner.gatilhos.matrizes import Matrizes, ajuste_acumulado, montar
from scanner.gatilhos.niveis import Regras, detectar

F64 = npt.NDArray[np.float64]
B = npt.NDArray[np.bool_]

LOTE = int(os.environ.get("BACKTEST_LOTE", "100"))
PIVO = 3


def _f(x: pd.DataFrame) -> F64:
    return np.array(x.to_numpy(dtype=np.float64))  # copia: o pandas 3 devolve so leitura


def antes(m: F64, n: int) -> F64:
    """A matriz `n` pregoes atras (NaN no comeco)."""
    out = np.full_like(m, np.nan, dtype=np.float64)
    if n < m.shape[0]:
        out[n:] = m[:-n]
    return out


def maior(m: F64, n: int) -> F64:
    """Maior valor dos ultimos `n` pregoes, com o dia."""
    return _f(pd.DataFrame(m).rolling(n, min_periods=n).max())


def menor(m: F64, n: int) -> F64:
    return _f(pd.DataFrame(m).rolling(n, min_periods=n).min())


def pivos(m: F64, topo: bool, k: int = PIVO) -> tuple[F64, F64, F64, F64]:
    """(ultimo, anterior, dia do ultimo, dia do anterior) dos pivos, sem olhar o futuro.

    O pivo do dia j usa os k pregoes seguintes: so entra na conta do dia j + k.
    """
    janela = pd.DataFrame(m).rolling(2 * k + 1, center=True, min_periods=2 * k + 1)
    extremo = _f(janela.max() if topo else janela.min())
    with np.errstate(invalid="ignore"):
        eh = np.isfinite(m) & (m == extremo)
    dias, papeis = m.shape
    valor = np.full((dias, papeis), np.nan)
    quando = np.full((dias, papeis), np.nan)
    valor_ant = np.full((dias, papeis), np.nan)
    quando_ant = np.full((dias, papeis), np.nan)
    for j in range(papeis):
        idx = np.nonzero(eh[:, j])[0]
        idx = idx[idx + k < dias]
        if idx.size == 0:
            continue
        conhecido = idx + k
        valor[conhecido, j] = m[idx, j]
        quando[conhecido, j] = idx
        valor_ant[conhecido[1:], j] = m[idx[:-1], j]
        quando_ant[conhecido[1:], j] = idx[:-1]

    def segue(x: F64) -> F64:
        return _f(pd.DataFrame(x).ffill())

    # o "anterior" so vale junto do "ultimo" do mesmo dia: os dois andam com ffill
    tem = np.isfinite(valor)
    valor_ant = np.where(tem & ~np.isfinite(valor_ant), -np.inf, valor_ant)
    quando_ant = np.where(tem & ~np.isfinite(quando_ant), -np.inf, quando_ant)
    va, qa = segue(valor_ant), segue(quando_ant)
    va[~np.isfinite(va)] = np.nan
    qa[~np.isfinite(qa)] = np.nan
    return segue(valor), va, segue(quando), qa


def sinais_de_estrutura(m: Matrizes, cfg: SetupsConfig, tick: F64) -> dict[str, Sinal]:
    o, h, low, c = m.abertura, m.maxima, m.minima, m.fechamento
    atr = atr_wilder(h, low, c)
    ctx = calcular(h, c, m.volume)
    rvol = np.asarray(ctx["rvol"], dtype=np.float64)
    dia = np.broadcast_to(np.arange(c.shape[0], dtype=np.float64)[:, None], c.shape)
    modelos: dict[str, tuple[B, F64, F64]] = {}

    with np.errstate(invalid="ignore", divide="ignore"):
        # bandeira: 7 pregoes de pausa depois de um mastro
        w = 7
        topo_pausa, fundo_pausa = maior(h, w), menor(low, w)
        fim_mastro = antes(c, w)
        topo_mastro = antes(maior(h, 11), w)
        pe_mastro = antes(menor(low, 11), w)
        mastro = fim_mastro - pe_mastro
        atr_m = antes(atr, w)
        bandeira = (
            (mastro >= 3 * atr_m)
            & (fim_mastro >= topo_mastro - 0.5 * atr_m)
            & (fundo_pausa >= fim_mastro - 0.5 * mastro)
            & (topo_pausa <= topo_mastro + 0.25 * atr_m)
        )
        modelos["bandeira"] = (bandeira, topo_pausa + tick, fundo_pausa - tick)

        # fundo duplo
        f1, f2, q1, q2 = pivos(low, topo=False)
        # o topo entre os dois fundos: a maior maxima desde o fundo anterior ate o ultimo
        pescoco = np.full_like(c, np.nan)
        for j in range(c.shape[1]):
            a, b = q2[:, j], q1[:, j]
            ok = np.isfinite(a) & np.isfinite(b)
            if not ok.any():
                continue
            pares = np.unique(np.stack([a[ok], b[ok]], axis=1), axis=0).astype(np.int64)
            valores = {(x, y): np.nanmax(h[x : y + 1, j]) for x, y in pares}
            pescoco[ok, j] = [valores[(int(x), int(y))] for x, y in zip(a[ok], b[ok], strict=True)]
        distancia = q1 - q2
        fundo = np.fmin(f1, f2)
        fundo_duplo = (
            (np.abs(f1 - f2) <= 0.5 * atr)
            & (distancia >= 8)
            & (distancia <= 60)
            & (pescoco - fundo >= 2 * atr)
            & (h < pescoco)
            & (c >= pescoco - 1.5 * atr)
            & (menor(low, 1) > fundo)
            & (dia - q1 <= 30)
        )
        modelos["fundo_duplo"] = (fundo_duplo, pescoco + tick, fundo - tick)

        # quebra de estrutura
        t1, t2, _, _ = pivos(h, topo=True)
        fecha_acima = c > t1
        primeira = fecha_acima & ~(antes(c, 1) > antes(t1, 1))
        quebra = (t1 < t2) & (f1 < f2) & primeira
        modelos["quebra_estrutura"] = (quebra, h + tick, f1 - tick)

        # gap de valor justo, no primeiro reteste
        fvg = np.zeros_like(c, dtype=bool)
        fundo_zona = np.full_like(c, np.nan)
        for d in range(1, 11):
            teto, piso = antes(low, d), antes(h, d + 2)
            corpo_meio = antes(c, d + 1) - antes(o, d + 1)
            zona = (teto > piso) & (corpo_meio >= antes(atr, d + 1))
            intacta = zona if d == 1 else zona & (antes(menor(low, d - 1), 1) > teto)
            volta = intacta & (low <= teto) & (low >= piso) & (c > teto) & ~fvg
            fvg |= volta
            fundo_zona = np.where(volta, piso, fundo_zona)
        modelos["fvg"] = (fvg, h + tick, fundo_zona - tick)

        # contracao de volatilidade
        amp = maior(h, 10) - menor(low, 10)
        a1, a2, a3 = amp, antes(amp, 10), antes(amp, 20)
        contracao = (a1 < 0.7 * a2) & (a2 < 0.7 * a3) & (maior(h, 10) >= maior(h, 60) - atr)
        modelos["contracao"] = (contracao, maior(h, 10) + tick, menor(low, 10) - tick)

        # NR7
        amplitude = h - low
        nr7 = (amplitude > 0) & (amplitude <= menor(amplitude, 7))
        modelos["nr7"] = (nr7, h + tick, low - tick)

        # Donchian
        for n in (20, 55):
            canal = maior(h, n)
            modelos[f"donchian{n}"] = (np.isfinite(canal), canal + tick, canal + tick - 2 * atr)

        # gap de alta com volume
        vespera = antes(h, 1)
        gap = (o > vespera) & (low > vespera) & (c >= o) & (rvol >= 2.0)
        modelos["gap_volume"] = (gap, h + tick, low - tick)

        # rompimento de resistencia de 3+ toques
        ret, _ = detectar(h, low, c, atr, Regras(toques_min=cfg.toques_nivel))
        rompe = (ret.rompeu_res_forca >= cfg.toques_gatilho) & (rvol >= cfg.volume_minimo)
        modelos["rompe_resistencia"] = (np.asarray(rompe, dtype=bool), h + tick, low - tick)

    sinais: dict[str, Sinal] = {}
    for nome, (armado, gatilho, stop) in modelos.items():
        ok = np.asarray(armado, dtype=bool) & np.isfinite(gatilho) & np.isfinite(stop)
        sinais[f"{nome}/padrao"] = Sinal(armado=ok, gatilho=gatilho, stop=stop)
        sinais[f"{nome}/atr10"] = Sinal(
            armado=ok & np.isfinite(atr), gatilho=gatilho, stop=gatilho - atr
        )
    return sinais


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
        sinais = sinais_de_estrutura(m, cfg, tick)
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
