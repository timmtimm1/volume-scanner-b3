"""O trade de cada setup, pregao a pregao, sem olhar o futuro.

Entrada (igual para todos os setups): o setup arma no fechamento de `t`; a ordem
de compra vale so no pregao seguinte, no gatilho. Se o pregao abre acima do
gatilho, compra na abertura. Se nao chega no gatilho, nao houve trade.

Risco (1R) = entrada menos stop inicial. Resultado em R: (saida - entrada) / R.

Saidas da suite (decisao do usuario em 05/11/2026), todas com o stop inicial:

- `alvo1`, `alvo2`, `alvo3`: alvo fixo a 1, 2 ou 3 R;
- `minimas`: stop movel na menor minima dos 2 ultimos candles (so sobe);
- `mme9`: sai na abertura seguinte ao fechamento que virou a MME 9 para baixo.

Toda saida tem um teto de `TETO` pregoes: chegou la aberto, sai no fechamento.

Como a ordem dos precos dentro do dia nao e conhecida, as escolhas sao as
conservadoras:

- no dia da entrada, minima no stop conta como stop, mesmo que tenha vindo antes;
- abertura abaixo do stop sai na abertura (pior que -1R); abertura acima do alvo
  sai na abertura;
- stop e alvo no mesmo dia: conta o stop.

Custos: `custo` por lado, como fracao do preco (taxas da B3 + derrapagem),
cobrado na compra e na venda.

Laco sobre os pregoes do trade (ate `TETO`), vetorizado entre os trades.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from scanner.gatilhos.medias import media_movel

F64 = npt.NDArray[np.float64]
I64 = npt.NDArray[np.int64]
I8 = npt.NDArray[np.int8]
B = npt.NDArray[np.bool_]

TETO = 60

# Motivo da saida (int8 no resultado).
ABERTO = 0  # chegou no fim dos dados ainda posicionado
STOP = 1  # stop inicial
MOVEL = 2  # stop movel (pelas minimas)
ALVO = 3
MEDIA = 4  # MME 9 virou para baixo
PRAZO = 5  # chegou ao teto
MOTIVOS = {
    ABERTO: "aberto",
    STOP: "stop",
    MOVEL: "movel",
    ALVO: "alvo",
    MEDIA: "mme9",
    PRAZO: "teto",
}


@dataclass(frozen=True)
class Saida:
    nome: str
    alvo_r: float | None = None
    movel: str | None = None  # "minimas" | "mme9"


SAIDAS: tuple[Saida, ...] = (
    Saida("alvo1", alvo_r=1.0),
    Saida("alvo2", alvo_r=2.0),
    Saida("alvo3", alvo_r=3.0),
    Saida("minimas", movel="minimas"),
    Saida("mme9", movel="mme9"),
)


@dataclass(frozen=True)
class Precos:
    """Matrizes (pregao x papel) que o simulador consulta."""

    abertura: F64
    maxima: F64
    minima: F64
    fechamento: F64
    tick: F64
    # A MME 9 fechou abaixo da MME 9 do pregao negociado anterior.
    vira_baixo: B

    @classmethod
    def de(cls, abertura: F64, maxima: F64, minima: F64, fechamento: F64, tick: F64) -> Precos:
        mme = pd.DataFrame(media_movel(fechamento, "MME", 9)).ffill()
        anterior = mme.shift(1).to_numpy(dtype=np.float64)
        with np.errstate(invalid="ignore"):
            vira = (mme.to_numpy(dtype=np.float64) < anterior) & np.isfinite(fechamento)
        return cls(abertura, maxima, minima, fechamento, tick, np.asarray(vira, dtype=bool))


@dataclass(frozen=True)
class Entradas:
    entrou: B
    dia: I64  # pregao da entrada (t + 1)
    preco: F64


def entrar(p: Precos, dia_sinal: I64, col: I64, gatilho: F64) -> Entradas:
    """Compra no pregao seguinte ao sinal, se ele passar do gatilho."""
    dia = dia_sinal + 1
    fora = dia >= p.abertura.shape[0]
    d = np.where(fora, 0, dia)
    o, h = p.abertura[d, col], p.maxima[d, col]
    with np.errstate(invalid="ignore"):
        entrou = ~fora & np.isfinite(o) & (h >= gatilho)
    preco = np.where(entrou, np.fmax(o, gatilho), np.nan)
    return Entradas(entrou=entrou, dia=dia, preco=preco)


@dataclass(frozen=True)
class Resultado:
    dia_saida: I64  # -1 enquanto aberto
    preco_saida: F64
    motivo: I8
    r_bruto: F64
    r: F64  # liquido de custos


def simular(
    p: Precos,
    dia_entrada: I64,
    col: I64,
    entrada: F64,
    stop: F64,
    saida: Saida,
    custo: float = 0.0,
    dia_anterior_minima: F64 | None = None,
) -> Resultado:
    """Leva cada trade ate a saida. `stop` e o stop inicial de cada um.

    `dia_anterior_minima`: minima do candle sinal, que entra na conta do stop
    movel (os 2 ultimos candles) no dia seguinte a entrada. Sem ela, o primeiro
    passo usa so a minima do dia da entrada.
    """
    n_dias = p.abertura.shape[0]
    n = dia_entrada.size
    stop_atual = stop.astype(np.float64, copy=True)
    risco = entrada - stop
    alvo = entrada + saida.alvo_r * risco if saida.alvo_r is not None else np.full(n, np.inf)
    preco_saida = np.full(n, np.nan)
    dia_saida = np.full(n, -1, dtype=np.int64)
    motivo = np.zeros(n, dtype=np.int8)
    aberto = np.isfinite(entrada) & (risco > 0) & (dia_entrada < n_dias)

    def fecha(mask: B, preco: F64, dia: I64, por: int | I8) -> None:
        preco_saida[mask] = preco[mask]
        dia_saida[mask] = dia[mask]
        motivo[mask] = por if isinstance(por, int) else por[mask]
        aberto[mask] = False

    def motivo_do_stop() -> I8:
        return np.where(stop_atual > stop, MOVEL, STOP).astype(np.int8)

    # dia da entrada: so o stop inicial e o alvo
    d = np.where(aberto, dia_entrada, 0)
    low, high = p.minima[d, col], p.maxima[d, col]
    with np.errstate(invalid="ignore"):
        fecha(aberto & (low <= stop_atual), stop_atual, d, STOP)
        fecha(aberto & (high >= alvo), alvo, d, ALVO)
    # estado para as saidas moveis
    ultima = np.where(aberto, low, np.nan)
    penultima = (
        dia_anterior_minima.astype(np.float64, copy=True)
        if dia_anterior_minima is not None
        else np.full(n, np.nan)
    )
    pendente = aberto & p.vira_baixo[d, col]
    ultimo_fech = np.where(aberto, p.fechamento[d, col], np.nan)

    for k in range(1, TETO + 1):
        dia = dia_entrada + k
        dentro = dia < n_dias
        d = np.where(dentro, dia, 0)
        o, h, low, c = p.abertura[d, col], p.maxima[d, col], p.minima[d, col], p.fechamento[d, col]
        if not (aberto & dentro).any():
            break
        vivo = aberto & dentro & np.isfinite(c)
        if saida.movel == "minimas":
            novo = np.fmin(ultima, penultima) - p.tick[d, col]
            stop_atual = np.where(vivo & np.isfinite(novo), np.fmax(stop_atual, novo), stop_atual)
        with np.errstate(invalid="ignore"):
            if saida.movel == "mme9":
                fecha(vivo & pendente, o, d, MEDIA)
                vivo &= aberto
            fecha(vivo & (o <= stop_atual), o, d, motivo_do_stop())
            vivo &= aberto
            fecha(vivo & (low <= stop_atual), stop_atual, d, motivo_do_stop())
            vivo &= aberto
            fecha(vivo & (o >= alvo), o, d, ALVO)
            vivo &= aberto
            fecha(vivo & (h >= alvo), alvo, d, ALVO)
            vivo &= aberto
        penultima = np.where(vivo, ultima, penultima)
        ultima = np.where(vivo, low, ultima)
        pendente = np.where(vivo, p.vira_baixo[d, col], pendente)
        ultimo_fech = np.where(vivo, c, ultimo_fech)
        if k == TETO:
            # quem nao negociou no ultimo dia do prazo sai pelo ultimo fechamento
            fecha(aberto & dentro, ultimo_fech, d, PRAZO)

    with np.errstate(invalid="ignore", divide="ignore"):
        r_bruto = (preco_saida - entrada) / risco
        r = (preco_saida * (1 - custo) - entrada * (1 + custo)) / risco
    return Resultado(
        dia_saida=dia_saida, preco_saida=preco_saida, motivo=motivo, r_bruto=r_bruto, r=r
    )
