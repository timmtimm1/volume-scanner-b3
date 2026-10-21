"""Media movel como suporte, em tendencia (pedido do usuario em 21/10/2026).

Num papel em alta, o recuo costuma parar na media movel em vez de num fundo
antigo. O candle de reversao que encosta nela conta como gatilho, nas mesmas
condicoes do suporte horizontal. As medias sao as do grafico do site (MME 9 e
MMA 20, `web/src/lib/medias.ts`), e "em tendencia" e:

- a media subindo: mais alta que `inclinacao` pregoes atras;
- o preco vindo de cima: dos `janela_acima` fechamentos anteriores ao candle,
  ao menos `minimo_acima` acima da media do proprio dia;
- o toque: a minima do padrao a menos de `tol_atr` ATR da media (ou furando
  ate `furo_atr` ATR) e o fechamento do candle acima dela.

A MME e a mesma do site (fator 2/(n+1)); o site semeia com a MMA dos primeiros
n fechamentos, aqui a semente e o primeiro fechamento -- depois de algumas
dezenas de pregoes as duas coincidem. Nada olha o futuro: tudo usa o dia do
candle e os anteriores.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

F64 = npt.NDArray[np.float64]
B = npt.NDArray[np.bool_]

JANELAS_DO_PADRAO = (1, 2, 3)


@dataclass(frozen=True)
class RegrasDaMedia:
    medias: tuple[tuple[str, int], ...] = (("MME", 9), ("MMA", 20))
    inclinacao: int = 10
    janela_acima: int = 5
    minimo_acima: int = 4
    tol_atr: float = 0.5
    tol_min_pct: float = 0.004
    furo_atr: float = 1.5


def nome(tipo: str, periodo: int) -> str:
    """Nome curto da media, como vai para o banco e para a tela: mme9, mma20."""
    return f"{tipo.lower()}{periodo}"


def media_movel(fechamento: F64, tipo: str, periodo: int) -> F64:
    """MMA ou MME do fechamento, papel a papel. Dia sem negocio nao entra."""
    fech = pd.DataFrame(fechamento)
    if tipo == "MMA":
        out = fech.rolling(periodo, min_periods=periodo).mean()
    else:
        out = fech.ewm(span=periodo, adjust=False, min_periods=periodo, ignore_na=True).mean()
    valores = out.to_numpy(dtype=np.float64, copy=True)
    valores[np.isnan(fechamento)] = np.nan
    return valores


def toques_na_media(
    minima: F64, fechamento: F64, atr: F64, regras: RegrasDaMedia | None = None
) -> dict[str, tuple[F64, B]]:
    """Por media: (valores, toque) -- toque e (3, dias, papeis), um por janela.

    A camada k diz que a minima dos ultimos k candles (1 para martelo, 2 para
    engolfo/piercing, 3 para estrela) encostou na media em tendencia, com o
    fechamento do dia acima dela.
    """
    r = regras or RegrasDaMedia()
    with np.errstate(invalid="ignore"):
        tol = np.fmax(r.tol_atr * atr, r.tol_min_pct * fechamento)
    minimas = [
        pd.DataFrame(minima).rolling(k, min_periods=1).min().to_numpy(dtype=np.float64)
        for k in JANELAS_DO_PADRAO
    ]
    saida: dict[str, tuple[F64, B]] = {}
    for tipo, periodo in r.medias:
        mm = media_movel(fechamento, tipo, periodo)
        quadro = pd.DataFrame(mm)
        with np.errstate(invalid="ignore"):
            sobe = mm > quadro.shift(r.inclinacao).to_numpy(dtype=np.float64)
            acima = pd.DataFrame(fechamento > mm).astype(float)
            vinha_acima = (
                acima.shift(1).rolling(r.janela_acima, min_periods=r.janela_acima).sum()
                >= r.minimo_acima
            ).to_numpy(dtype=bool)
            tendencia = sobe & vinha_acima & (fechamento >= mm)
            toque = np.stack(
                [tendencia & (low <= mm + tol) & (low >= mm - r.furo_atr * atr) for low in minimas]
            )
        saida[nome(tipo, periodo)] = (mm, np.asarray(toque, dtype=bool))
    return saida
