"""Padroes de candle de reversao para cima, sobre matrizes pregao x papel.

Cada padrao e uma regra de proporcao do proprio candle (e dos anteriores, nos
padroes de 2 e 3 candles). Nenhum olha o contexto: martelo no topo continua
sendo martelo aqui. Quem pede "no suporte" e o modulo `niveis`.

Os cortes sao os classicos dos livros de candlestick, escritos em numero:

- martelo: sombra de baixo >= 2x o corpo, sombra de cima pequena;
- doji libelula: quase sem corpo, sombra de baixo >= 70% do range;
- engolfo de alta: verde cujo corpo engole o corpo vermelho anterior, que
  precisa ter corpo de verdade (>= 0,3 ATR);
- piercing: verde que abre abaixo do fechamento vermelho anterior e fecha
  acima da metade do corpo dele;
- estrela da manha: vermelho forte, um candle pequeno, verde que fecha acima
  da metade do primeiro;
- candle de forca: verde de corpo largo (>= 1,2 ATR) fechando no quarto de cima.

Candle minusculo (range < meio ATR) nao e martelo nem libelula: e ruido.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

F64 = npt.NDArray[np.float64]
B = npt.NDArray[np.bool_]

PADROES = ("martelo", "libelula", "engolfo", "piercing", "estrela", "forca")
# Quantos candles cada padrao usa: a minima do padrao e a menor deles.
TAMANHO = {"martelo": 1, "libelula": 1, "engolfo": 2, "piercing": 2, "estrela": 3, "forca": 1}


def _antes(m: F64, n: int) -> F64:
    out = np.full_like(m, np.nan)
    out[n:] = m[:-n]
    return out


def padroes(abertura: F64, maxima: F64, minima: F64, fechamento: F64, atr: F64) -> dict[str, B]:
    """Um booleano pregao x papel por padrao. NaN em qualquer entrada = False."""
    o, h, low, c = abertura, maxima, minima, fechamento
    with np.errstate(invalid="ignore", divide="ignore"):
        rng = h - low
        corpo = np.abs(c - o)
        baixo = np.fmin(o, c) - low
        cima = h - np.fmax(o, c)
        tem_range = rng >= 0.5 * atr
        verde = c > o

        libelula = tem_range & (corpo <= 0.1 * rng) & (cima <= 0.1 * rng) & (baixo >= 0.7 * rng)
        martelo = (
            tem_range
            & (corpo > 0.1 * rng)
            & (baixo >= 2 * corpo)
            & (cima <= np.fmax(0.5 * corpo, 0.1 * rng))
        )

        o1, c1, atr1 = _antes(o, 1), _antes(c, 1), _antes(atr, 1)
        corpo1 = o1 - c1  # positivo = vermelho
        # O vermelho engolido precisa ter corpo de verdade: engolir um doji nao e engolfo.
        engolfo = (corpo1 >= 0.3 * atr1) & verde & (o <= c1) & (c >= o1) & (corpo > corpo1)
        piercing = (
            (corpo1 > 0.5 * atr1) & verde & (o < c1) & (c > c1 + corpo1 / 2) & (c < o1) & ~engolfo
        )

        o2, c2, atr2 = _antes(o, 2), _antes(c, 2), _antes(atr, 2)
        corpo2 = o2 - c2
        meio = np.abs(c1 - o1)
        estrela = (
            (corpo2 > 0.6 * atr2)
            & (meio < 0.35 * corpo2)
            & (np.fmax(o1, c1) <= c2 + 0.1 * corpo2)
            & verde
            & (c > c2 + corpo2 / 2)
        )

        forca = verde & (corpo >= 1.2 * atr) & ((c - low) >= 0.75 * rng)

    return {
        "martelo": martelo,
        "libelula": libelula,
        "engolfo": engolfo,
        "piercing": piercing,
        "estrela": estrela,
        "forca": forca,
    }
