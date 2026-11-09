"""Setups classicos de compra no diario (pedido do usuario em 05/11/2026).

Os setups que o usuario opera, cada um como regra mecanica com nome. Todos
armam no fechamento do dia `t` e compram 1 centavo acima da maxima de `t` no
pregao seguinte; se o pregao seguinte nao passar da maxima, o setup nao
confirmou e acabou. O stop inicial fica 1 centavo abaixo da minima do padrao.

Larry Williams (versao Palex/TradingView, a mais documentada; decisao de
05/11/2026), todos sobre a MME 9 do fechamento:

- 9.1: a MME 9 vinha caindo e virou para cima no dia (`e[t-2] > e[t-1] < e[t]`);
- 9.2: MME 9 subindo e o fechamento abaixo da minima do candle anterior;
- 9.3: MME 9 subindo e dois fechamentos seguidos abaixo de um fechamento de
  referencia (o de `t-2`);
- 9.4: a MME 9 subia, virou para baixo em `t-1` (um 9.1 de venda) e voltou a
  subir em `t` sem o candle perder a minima de `t-1`. Stop na minima de `t-1`.

Filtros pedidos pelo usuario em 06/11/2026:

- 9.1: so com a minima do candle num suporte de 3 ou mais toques (o motor de
  `niveis`, o mesmo das linhas da ficha) e volume do dia de 1,5x a mediana dos
  20 pregoes anteriores ou mais -- a virada da MME 9 vale como fundo em suporte,
  sem exigir tendencia;
- 9.2, 9.3 e 9.4 so contam em tendencia de alta:

- a media de 80 periodos acima do valor de 20 pregoes atras (`tendencia_9x`);
  simples ou exponencial foi decidido no backtest, escolhendo com 1995-2015 e
  conferindo em 2016-2026 (secao 14 do plano);
- topos e fundos ascendentes (`pivo_9x`): o ultimo fundo conhecido acima do
  fundo anterior, e o ultimo topo acima do topo anterior. Fundo e topo sao os
  pivos do grafico (`niveis.pivos`: k pregoes de cada lado), e o pivo do dia j
  so e conhecido no dia j + k.

Fora disso, o 9.x nao arma.

Perto da media (pedido do usuario em 09/11/2026): 9.2, 9.3 e 9.4 sao setups de
correcao ATE a MME 9 -- com o candle longe dela, nao e o setup. A minima do
candle do sinal tem de estar a no maximo `perto_9x` ATR acima da MME 9 (encostar
ou furar vale). O Palex lista a "proximidade da mm9" entre as caracteristicas
desejaveis dos setups de correcao, sem numero; o 0,35 ATR saiu de 54 casos reais
de 2026 que o usuario marcou um a um ("e o setup" / "nao e"): o corte acerta 46
(aceitou 24 dos 29 ate 0,35 ATR e recusou 22 dos 25 acima disso).
A mesma marcacao NAO confirmou exigir que o candle de referencia seja o de maior
fechamento da perna (versao do blog do Palex): ele aceitou varios 9.2 e 9.3 sem
isso, entao a referencia continua sendo o candle anterior.

Micro-fundos de 1 a 3 candles:

- 123 de compra: o candle do meio (`t-1`) tem a minima mais baixa dos tres
  (estrito dos dois lados). Stop na minima do candle do meio;
- PFR (preco de fechamento de reversao): minima abaixo das dos dois candles
  anteriores e fechamento acima do fechamento anterior.

Os mesmos dois no suporte (pedido do usuario em 09/11/2026):

- 123 no suporte e PFR no suporte: a regra de cada um, com a minima do padrao
  num suporte de `toques_suporte`+ toques (o motor de `niveis`, o das linhas da
  ficha). Na conferencia de 52 casos de padroes em suporte, foram os dois
  padroes novos que o usuario aprovou (7 de 8); harami, pinca, martelo
  invertido, falso rompimento, tres por dentro e tres por fora ficaram de fora.
  Sao setups A PARTE: o 123 e o PFR de sempre continuam como estao.

Tendencia:

- MMA 20, toque simples: MMA 20 subindo (acima de 10 pregoes atras), fechamento
  acima da MMA 200, minima a ate 1% da MMA 20 e fechamento acima dela. Nao exige
  candle de reversao (a secao "Na media" de `regra` exige);
- pullback de rompimento: uma resistencia de 3+ toques rompida no fechamento
  vira suporte (motor de `niveis`); a volta ate ela em ate 20 pregoes, com o
  fechamento segurando o nivel, arma o setup.

A tendencia nao filtra nada: `tendencia_de_alta` vira etiqueta, e o backtest
mostra "em alta" e "contra a tendencia" lado a lado (decisao de 05/11/2026).

Precos nas matrizes ajustadas por desdobramento (`matrizes`). O centavo e o da
escala do proprio dia: `tick` = R$ 0,01 vezes o ajuste do dia. Nada olha o
futuro: o estado de `t` so usa `t` e os dias anteriores.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from scanner.gatilhos.medias import media_movel
from scanner.gatilhos.niveis import Eventos, Retrato, pivos

F64 = npt.NDArray[np.float64]
B = npt.NDArray[np.bool_]

CENTAVO = 0.01
# Nome curto (vai para o banco e para a tela) -> nome por extenso.
NOMES: dict[str, str] = {
    "9.1": "9.1 (MME 9 vira para cima)",
    "9.2": "9.2 (fecha abaixo da minima anterior, MME 9 subindo)",
    "9.3": "9.3 (dois fechamentos abaixo da referencia, MME 9 subindo)",
    "9.4": "9.4 (9.1 de venda desfeito)",
    "123": "123 de compra",
    "pfr": "PFR (preco de fechamento de reversao)",
    "123_suporte": "123 de compra no suporte",
    "pfr_suporte": "PFR no suporte",
    "mma20": "Toque na MMA 20 em alta",
    "pullback": "Pullback de rompimento",
}


@dataclass(frozen=True)
class RegrasClassicas:
    mme: int = 9
    mma_curta: int = 20
    mma_longa: int = 200
    # MMA 20 "subindo": acima do valor de N pregoes atras (o mesmo da "Na media").
    inclinacao_curta: int = 10
    # MMA 200 "subindo", para a etiqueta de tendencia (o mesmo de `contexto`).
    inclinacao_longa: int = 20
    toque_mma_pct: float = 0.01
    toques_rompimento: int = 3
    pullback_pregoes: int = 20
    # Filtro de tendencia dos 9.x (06/11/2026): media de 80 subindo, acima do
    # valor de `inclinacao_9x` pregoes atras. None desliga (o 9.x de antes).
    # Exponencial: escolhida no backtest de 06/11/2026 (media de 9.2-9.4 em
    # 1995-2015: MME 80 +0,28 R contra MMA 80 +0,10 R por trade).
    tendencia_9x: tuple[str, int] | None = ("MME", 80)
    inclinacao_9x: int = 20
    # Topos e fundos ascendentes nos 9.x (06/11/2026), pelos pivos de k pregoes
    # de cada lado (o mesmo k dos niveis do grafico). None desliga.
    pivo_9x: int | None = 3
    # 9.1 (06/11/2026): "suporte_volume" = minima num suporte de `toques_91`+
    # toques e volume de `volume_91`x ou mais, sem tendencia; "tendencia" = o
    # mesmo filtro dos outros 9.x; "nenhum" = o 9.1 de antes.
    regra_91: str = "suporte_volume"
    toques_91: int = 3
    volume_91: float = 1.5
    # 123 e PFR no suporte (09/11/2026): toques minimos do suporte tocado.
    toques_suporte: int = 3
    # Perto da media (09/11/2026): nos 9.2 a 9.4 a minima do candle do sinal a
    # no maximo este tanto de ATR acima da MME 9. None desliga.
    perto_9x: float | None = 0.35


@dataclass(frozen=True)
class Sinal:
    """Um setup sobre a janela inteira (pregao x papel)."""

    armado: B
    # Compra se o pregao seguinte negociar neste preco ou acima.
    gatilho: F64
    stop: F64


def _antes(m: F64, k: int) -> F64:
    """O valor de k pregoes antes (NaN nas primeiras linhas)."""
    out = np.full_like(m, np.nan)
    out[k:] = m[:-k]
    return out


def tendencia_de_alta(fechamento: F64, regras: RegrasClassicas | None = None) -> B:
    """Fechamento acima da MMA 200, com a MMA 200 acima de 20 pregoes atras."""
    r = regras or RegrasClassicas()
    mm = pd.DataFrame(fechamento).ffill().rolling(r.mma_longa, min_periods=r.mma_longa).mean()
    sobe = (mm > mm.shift(r.inclinacao_longa)).to_numpy(dtype=bool)
    with np.errstate(invalid="ignore"):
        return np.asarray((fechamento > mm.to_numpy(dtype=np.float64)) & sobe, dtype=bool)


def topos_e_fundos_ascendentes(maxima: F64, minima: F64, k: int) -> B:
    """O ultimo fundo conhecido acima do anterior, e o ultimo topo acima do anterior.

    Fundo e topo sao os pivos de `k` pregoes para cada lado; o do dia j usa os
    k pregoes seguintes, entao so vale a partir do dia j + k. Nada olha o futuro.
    """
    fundo, topo = pivos(minima, maxima, k)

    def ultimo_e_anterior(marca: B, valores: F64) -> tuple[F64, F64]:
        # o valor do pivo aparece no dia em que ele fica conhecido
        conhecido = pd.DataFrame(_antes(np.where(marca, valores, np.nan), k))
        ultimo = conhecido.ffill()
        # no dia de um pivo novo, o ultimo de ontem e o anterior a ele
        anterior = ultimo.shift(1).where(conhecido.notna()).ffill()
        return ultimo.to_numpy(dtype=np.float64), anterior.to_numpy(dtype=np.float64)

    uf, af = ultimo_e_anterior(fundo, minima)
    ut, at = ultimo_e_anterior(topo, maxima)
    with np.errstate(invalid="ignore"):
        return np.asarray((uf > af) & (ut > at), dtype=bool)


def _dias_desde_o_rompimento(retrato: Retrato, eventos: Eventos) -> F64:
    """Pregoes entre o rompimento e o toque de hoje, no suporte que era resistencia.

    O motor abre um segmento novo quando o nivel troca de papel, com `inicio` no
    dia do rompimento. NaN onde a minima de hoje nao toca um nivel que virou.
    """
    seg = retrato.toca_seg[0]
    out = np.full(seg.shape, np.nan)
    segs = eventos.segmentos
    if segs.empty:
        return out
    ids = segs["seg"].to_numpy(dtype=np.int64)
    inicio = np.full(int(ids.max()) + 1, -1, dtype=np.int64)
    inicio[ids] = segs["inicio"].to_numpy(dtype=np.int64)
    dia = np.arange(seg.shape[0])[:, None]
    tem = retrato.toca_virou[0] & (seg >= 0)
    comeco = np.where(tem, inicio[np.where(seg >= 0, seg, 0)], -1)
    ok = tem & (comeco >= 0)
    out[ok] = (dia - comeco)[ok]
    return out


def classicos(
    abertura: F64,
    maxima: F64,
    minima: F64,
    fechamento: F64,
    tick: F64,
    retrato: Retrato,
    eventos: Eventos,
    rvol: F64,
    atr: F64,
    regras: RegrasClassicas | None = None,
) -> dict[str, Sinal]:
    """Todos os setups classicos, um `Sinal` por nome de `NOMES`.

    `rvol`: volume do dia sobre a mediana dos 20 pregoes anteriores
    (`contexto.calcular`), para o filtro do 9.1. `atr`: o ATR de 14 pregoes
    (`contexto.atr_wilder`), a regua do "perto da MME 9" dos 9.2 a 9.4.
    """
    r = regras or RegrasClassicas()
    o, h, low, c = abertura, maxima, minima, fechamento
    negociou = np.isfinite(o) & np.isfinite(h) & np.isfinite(low) & np.isfinite(c)
    e = media_movel(c, "MME", r.mme)
    e1, e2, e3 = _antes(e, 1), _antes(e, 2), _antes(e, 3)
    c1, c2 = _antes(c, 1), _antes(c, 2)
    l1, l2 = _antes(low, 1), _antes(low, 2)
    mm20 = media_movel(c, "MMA", r.mma_curta)
    mm200 = media_movel(c, "MMA", r.mma_longa)
    desde = _dias_desde_o_rompimento(retrato, eventos)

    gatilho = h + tick
    stop_do_dia = low - tick
    with np.errstate(invalid="ignore"):
        tendencia = np.ones_like(negociou)
        if r.tendencia_9x is not None:
            tipo, periodo = r.tendencia_9x
            mm_t = media_movel(c, tipo, periodo)
            tendencia &= mm_t > _antes(mm_t, r.inclinacao_9x)
        if r.pivo_9x is not None:
            tendencia &= topos_e_fundos_ascendentes(h, low, r.pivo_9x)
        if r.regra_91 == "suporte_volume":
            filtro_91 = (retrato.toca_forca[0] >= r.toques_91) & (rvol >= r.volume_91)
        elif r.regra_91 == "tendencia":
            filtro_91 = tendencia
        else:
            filtro_91 = np.ones_like(negociou)
        sobe = e > e1
        um23 = (l2 > l1) & (low > l1)
        pfr = (low < np.fmin(l1, l2)) & (c > c1) & np.isfinite(l2)
        # camada 2 = a minima dos ultimos 3 candles (no 123 e a do meio);
        # camada 0 = a do dia (no PFR e a menor das tres)
        suporte_3 = retrato.toca_forca[2] >= r.toques_suporte
        suporte_1 = retrato.toca_forca[0] >= r.toques_suporte
        perto = np.ones_like(negociou)
        if r.perto_9x is not None:
            perto = low <= e + r.perto_9x * atr
        correcao = tendencia & perto
        regras_ = {
            "9.1": ((e2 > e1) & sobe & filtro_91, stop_do_dia),
            "9.2": (sobe & (c < l1) & correcao, stop_do_dia),
            "9.3": (sobe & (c1 < c2) & (c < c2) & correcao, stop_do_dia),
            "9.4": ((e2 > e3) & (e1 < e2) & sobe & (low >= l1) & correcao, l1 - tick),
            "123": (um23, l1 - tick),
            "pfr": (pfr, stop_do_dia),
            "123_suporte": (um23 & suporte_3, l1 - tick),
            "pfr_suporte": (pfr & suporte_1, stop_do_dia),
            "mma20": (
                (mm20 > _antes(mm20, r.inclinacao_curta))
                & (c > mm200)
                & (low <= mm20 * (1 + r.toque_mma_pct))
                & (c >= mm20),
                stop_do_dia,
            ),
            "pullback": (
                (retrato.toca_forca[0] >= r.toques_rompimento)
                & (desde >= 1)
                & (desde <= r.pullback_pregoes),
                stop_do_dia,
            ),
        }
    saida: dict[str, Sinal] = {}
    for nome, (armado, stop) in regras_.items():
        ok = np.asarray(armado, dtype=bool) & negociou & np.isfinite(stop) & (stop < low)
        saida[nome] = Sinal(armado=ok, gatilho=gatilho, stop=stop)
    return saida
