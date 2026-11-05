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

Micro-fundos de 1 a 3 candles:

- 123 de compra: o candle do meio (`t-1`) tem a minima mais baixa dos tres
  (estrito dos dois lados). Stop na minima do candle do meio;
- PFR (preco de fechamento de reversao): minima abaixo das dos dois candles
  anteriores e fechamento acima do fechamento anterior.

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
from scanner.gatilhos.niveis import Eventos, Retrato

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
    regras: RegrasClassicas | None = None,
) -> dict[str, Sinal]:
    """Todos os setups classicos, um `Sinal` por nome de `NOMES`."""
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
        sobe = e > e1
        regras_ = {
            "9.1": ((e2 > e1) & sobe, stop_do_dia),
            "9.2": (sobe & (c < l1), stop_do_dia),
            "9.3": (sobe & (c1 < c2) & (c < c2), stop_do_dia),
            "9.4": ((e2 > e3) & (e1 < e2) & sobe & (low >= l1), l1 - tick),
            "123": ((l2 > l1) & (low > l1), l1 - tick),
            "pfr": ((low < np.fmin(l1, l2)) & (c > c1) & np.isfinite(l2), stop_do_dia),
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
