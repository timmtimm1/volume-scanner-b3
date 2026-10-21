"""Contexto recente e volume, sobre matrizes pregao x papel.

- queda recente: retorno dos 20 pregoes ate a vespera (o dia do candle fica de
  fora, como o `ret_prior_20` do scanner);
- tendencia de baixa: fechamento abaixo da MM200, com a MM200 menor que 20
  pregoes atras;
- correcao em alta: acima da MM200 subindo, e X% abaixo da maxima de 60 pregoes;
- volume: rvol (volume sobre a mediana dos 20 pregoes ANTERIORES) e o z do log
  do volume na janela de 30 anteriores -- o mesmo `shift(1)` da secao 1 do plano.

Lateralizacao depende de suporte e resistencia e mora em `niveis`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

F64 = npt.NDArray[np.float64]
B = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class RegrasDeContexto:
    queda_pct: float = 0.10
    queda_janela: int = 20
    mm_longa: int = 200
    inclinacao: int = 20
    correcao_pct: float = 0.07
    correcao_janela: int = 60
    rvol_janela: int = 20
    z_janela: int = 30


def atr_wilder(maxima: F64, minima: F64, fechamento: F64, n: int = 14) -> F64:
    """ATR de Wilder. Dia sem negocio nao entra na media (fica NaN)."""
    anterior = pd.DataFrame(fechamento).ffill().shift(1).to_numpy(dtype=np.float64)
    tr = np.fmax(maxima - minima, np.fmax(np.abs(maxima - anterior), np.abs(minima - anterior)))
    tr[np.isnan(fechamento)] = np.nan
    atr = (
        pd.DataFrame(tr)
        .ewm(alpha=1 / n, adjust=False, min_periods=n, ignore_na=True)
        .mean()
        .to_numpy(dtype=np.float64, copy=True)
    )
    atr[np.isnan(fechamento)] = np.nan
    return atr


def calcular(
    maxima: F64, fechamento: F64, volume: F64, regras: RegrasDeContexto | None = None
) -> dict[str, F64 | B]:
    """Contextos (booleanos) e medidas (float) por pregao x papel."""
    r = regras or RegrasDeContexto()
    fech = pd.DataFrame(fechamento).ffill()
    vespera = fech.shift(1)
    ret_ant = (vespera / fech.shift(1 + r.queda_janela) - 1).to_numpy(dtype=np.float64)

    mm = fech.rolling(r.mm_longa, min_periods=r.mm_longa).mean()
    sobe = (mm > mm.shift(r.inclinacao)).to_numpy()
    desce = (mm < mm.shift(r.inclinacao)).to_numpy()
    mm_np = mm.to_numpy(dtype=np.float64)
    maxj = (
        pd.DataFrame(maxima)
        .rolling(r.correcao_janela, min_periods=r.correcao_janela // 3)
        .max()
        .to_numpy(dtype=np.float64)
    )

    with np.errstate(invalid="ignore", divide="ignore"):
        recuo = fechamento / maxj - 1
        queda = ret_ant <= -r.queda_pct
        baixa = (fechamento < mm_np) & desce
        correcao = (fechamento > mm_np) & sobe & (recuo <= -r.correcao_pct)

    vol = pd.DataFrame(volume)
    mediana = vol.shift(1).rolling(r.rvol_janela, min_periods=r.rvol_janela * 3 // 4).median()
    rvol = (vol / mediana).to_numpy(dtype=np.float64)
    with np.errstate(divide="ignore"):
        lv = pd.DataFrame(np.log(volume))
    base = lv.shift(1).rolling(r.z_janela, min_periods=r.z_janela)
    z = ((lv - base.mean()) / base.std()).to_numpy(dtype=np.float64)

    return {
        "ret_ant": ret_ant,
        "recuo": recuo,
        "queda": queda,
        "baixa": baixa,
        "correcao": correcao,
        "rvol": rvol,
        "z": z,
    }
