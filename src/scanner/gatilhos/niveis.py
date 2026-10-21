"""Suporte e resistencia, vetorizado entre papeis.

Definicao do usuario (21/10/2026): nivel e o preco onde o preco bate varias
vezes e nao rompe, ate romper.

Como o codigo enxerga isso:

1. Toque = fundo (ou topo) local: a menor minima de `pivo` pregoes para cada
   lado. Um fundo no dia j so e conhecido no dia j + pivo, e so entao entra.
2. O fundo vai para o nivel do mesmo papel mais perto, dentro da tolerancia
   (`tol_atr` ATR, com piso de `tol_min_pct` do preco). Sem nivel perto, nasce
   um nivel com 1 toque.
3. Furou e voltou: a sombra passou do nivel (ate `furo_atr` ATR), mas o
   fechamento daquele dia voltou para dentro. Conta como toque e nao mexe no
   preco do nivel.
4. Preco do nivel = media dos toques conhecidos ate o dia. Nada do futuro.
5. Rompimento = `rompe_fech` fechamentos seguidos alem do nivel, passando da
   tolerancia. Se o nivel valia, troca de papel UMA vez (suporte rompido vira
   resistencia) e guarda os toques do lado anterior em `historico`. Nivel que
   ainda nao valia some; nivel que ja trocou e rompe de novo tambem some. Sem
   isso, o meio de um mercado de lado juntava toques dos dois lados a cada vai e
   vem e virava "suporte forte" -- o contrario de "bate e nao rompe".
6. Nivel valendo = toques do lado atual + historico >= `toques_min`.
7. Nivel sem toque ha `validade` pregoes e esquecido.
8. Dois niveis do mesmo papel que ficam a menos de uma tolerancia se fundem.

Implementacao: um laco sobre os PREGOES, nunca sobre papeis. Em cada pregao
todos os papeis andam juntos; cada papel tem `vagas` niveis, guardados em
matrizes papel x vaga. Vaga cheia despeja primeiro o nivel que ainda nao vale e
esta ha mais tempo sem toque.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

F64 = npt.NDArray[np.float64]
F32 = npt.NDArray[np.float32]
I32 = npt.NDArray[np.int32]
I16 = npt.NDArray[np.int16]
B = npt.NDArray[np.bool_]

SUPORTE = 1
RESISTENCIA = -1

ROMPEU = 1
ESQUECIDO = 2
FUNDIDO = 3
DESPEJADO = 4

# Janelas dos padroes de candle: a minima de 1, 2 ou 3 candles toca o suporte.
JANELAS_DE_TOQUE = (1, 2, 3)


@dataclass(frozen=True)
class Regras:
    pivo: int = 3
    tol_atr: float = 0.5
    tol_min_pct: float = 0.004
    furo_atr: float = 1.5
    toques_min: int = 3
    rompe_fech: int = 1
    validade: int = 250
    vagas: int = 48
    caixa_toques: int = 2
    caixa_max_pct: float = 0.20
    caixa_pregoes: int = 30


@dataclass
class Retrato:
    """O que se sabia de cada papel no fechamento de cada pregao (pregao x papel)."""

    tol: F32
    sup_preco: F32
    sup_forca: I16
    sup_seg: I32
    sup_virou: B
    res_preco: F32
    res_forca: I16
    res_seg: I32
    # Uma camada por janela de JANELAS_DE_TOQUE: a minima dos ultimos 1, 2 ou 3
    # candles tocou um suporte valendo (que ja existia antes do dia).
    toca_preco: F32
    toca_forca: I16
    toca_seg: I32
    toca_furou: B
    toca_virou: B
    rompeu_res: B
    rompeu_res_preco: F32
    rompeu_res_forca: I16
    rompeu_sup: B
    caixa_altura: F32


@dataclass
class Eventos:
    """Historia de cada segmento (um nivel com um papel) e de cada toque.

    `col` e a coluna do papel nas matrizes; `dia`, `inicio`, `fim` sao posicoes
    de pregao. Um nivel que troca de papel vira um segmento novo, com `origem`
    apontando o anterior e o mesmo `nivel`.
    """

    segmentos: pd.DataFrame
    toques: pd.DataFrame
    despejos: int = 0
    resumo: dict[str, int] = field(default_factory=dict)


def pivos(minima: F64, maxima: F64, k: int) -> tuple[B, B]:
    """Fundos e topos locais: menor minima (maior maxima) de k pregoes de cada lado.

    Empate fica com o primeiro dia (estrito a esquerda, nao estrito a direita),
    para um fundo duplo no mesmo preco nao virar dois toques no mesmo lugar.
    """
    low = pd.DataFrame(minima)
    high = pd.DataFrame(maxima)
    esq_min = low.shift(1).rolling(k, min_periods=1).min()
    dir_min = low.iloc[::-1].shift(1).rolling(k, min_periods=1).min().iloc[::-1]
    esq_max = high.shift(1).rolling(k, min_periods=1).max()
    dir_max = high.iloc[::-1].shift(1).rolling(k, min_periods=1).max().iloc[::-1]
    fundo = ((low < esq_min) & (low <= dir_min)).to_numpy(dtype=bool, copy=True)
    topo = ((high > esq_max) & (high >= dir_max)).to_numpy(dtype=bool, copy=True)
    for m in (fundo, topo):
        m[:k] = False
        m[len(m) - k :] = False
    return fundo, topo


def _rolling(m: F64, n: int, como: str) -> F64:
    janela = pd.DataFrame(m).rolling(n, min_periods=1)
    out = janela.min() if como == "min" else janela.max()
    return out.to_numpy(dtype=np.float64)


class _Motor:
    def __init__(self, n_papeis: int, regras: Regras) -> None:
        t, k = n_papeis, regras.vagas
        self.r = regras
        self.papel = np.zeros((t, k), dtype=np.int8)
        self.preco = np.full((t, k), np.nan)
        self.soma = np.zeros((t, k))
        self.npre = np.zeros((t, k), dtype=np.int32)
        self.toques = np.zeros((t, k), dtype=np.int32)
        self.hist = np.zeros((t, k), dtype=np.int32)
        self.inicio = np.zeros((t, k), dtype=np.int32)
        self.primeiro = np.zeros((t, k), dtype=np.int32)
        self.ultimo = np.zeros((t, k), dtype=np.int32)
        self.seguidos = np.zeros((t, k), dtype=np.int16)
        self.seg = np.full((t, k), -1, dtype=np.int32)
        self.nivel = np.full((t, k), -1, dtype=np.int32)
        self.prox_seg = 0
        self.prox_nivel = 0
        self.despejos = 0
        self.log_seg: list[tuple[I32, I32, I32, npt.NDArray[np.int8], I32, I32, F64]] = []
        self.log_fim: list[tuple[I32, I32, I32, F64, I32]] = []
        self.log_toque: list[tuple[I32, I32, I32, I32, F64, B, F64]] = []

    def abrir(
        self, rr: npt.NDArray[np.intp], kk: npt.NDArray[np.intp], origem: I32 | None, dia: int
    ) -> None:
        """Da id novo aos segmentos nas vagas (rr, kk), ja preenchidas."""
        n = len(rr)
        ids = np.arange(self.prox_seg, self.prox_seg + n, dtype=np.int32)
        self.prox_seg += n
        self.seg[rr, kk] = ids
        if origem is None:
            niveis = np.arange(self.prox_nivel, self.prox_nivel + n, dtype=np.int32)
            self.prox_nivel += n
            self.nivel[rr, kk] = niveis
            orig = np.full(n, -1, dtype=np.int32)
        else:
            orig = origem
        self.log_seg.append(
            (
                ids,
                self.nivel[rr, kk].copy(),
                rr.astype(np.int32),
                self.papel[rr, kk].copy(),
                self.inicio[rr, kk].copy(),
                orig,
                self.preco[rr, kk].copy(),
            )
        )

    def fechar(
        self,
        rr: npt.NDArray[np.intp],
        kk: npt.NDArray[np.intp],
        dia: int,
        motivo: int,
        destino: I32 | None = None,
    ) -> None:
        n = len(rr)
        self.log_fim.append(
            (
                self.seg[rr, kk].copy(),
                np.full(n, dia, dtype=np.int32),
                np.full(n, motivo, dtype=np.int32),
                self.preco[rr, kk].copy(),
                destino if destino is not None else np.full(n, -1, dtype=np.int32),
            )
        )


def detectar(
    maxima: F64,
    minima: F64,
    fechamento: F64,
    atr: F64,
    regras: Regras | None = None,
) -> tuple[Retrato, Eventos]:
    """Roda o motor do primeiro ao ultimo pregao e devolve o retrato de cada dia."""
    r = regras or Regras()
    n_dias, n_papeis = fechamento.shape
    with np.errstate(invalid="ignore"):
        tol = np.fmax(r.tol_atr * atr, r.tol_min_pct * fechamento)
    tol[np.isnan(fechamento)] = np.nan
    tol_ff = pd.DataFrame(tol).ffill().to_numpy(dtype=np.float64)
    atr_ff = pd.DataFrame(atr).ffill().to_numpy(dtype=np.float64)
    fundo, topo = pivos(minima, maxima, r.pivo)
    min_janela = [_rolling(minima, m, "min") for m in JANELAS_DE_TOQUE]
    cmin = _rolling(fechamento, r.caixa_pregoes, "min")
    cmax = _rolling(fechamento, r.caixa_pregoes, "max")

    ret = _retrato_vazio(n_dias, n_papeis)
    ret.tol[:] = tol
    mo = _Motor(n_papeis, r)
    ar = np.arange(n_papeis)
    vagas = np.arange(r.vagas)

    for i in range(n_dias):
        c = fechamento[i]
        ti = tol_ff[i]
        negociou = ~np.isnan(c)

        # 1. esquecer nivel sem toque ha muito tempo
        velho = (mo.papel != 0) & (i - mo.ultimo > r.validade)
        if velho.any():
            rr, kk = np.nonzero(velho)
            mo.fechar(rr, kk, i, ESQUECIDO)
            mo.papel[rr, kk] = 0
            mo.seg[rr, kk] = -1

        # 2. rompimento pelo fechamento do dia
        cand = (mo.papel != 0) & (mo.inicio < i) & negociou[:, None]
        with np.errstate(invalid="ignore"):
            alem = np.where(
                mo.papel == SUPORTE,
                c[:, None] < mo.preco - ti[:, None],
                c[:, None] > mo.preco + ti[:, None],
            )
        mo.seguidos = np.where(cand, np.where(alem, mo.seguidos + 1, 0), mo.seguidos).astype(
            np.int16
        )
        quebra = cand & (mo.seguidos >= r.rompe_fech)
        mudou_r: list[npt.NDArray[np.intp]] = []
        mudou_k: list[npt.NDArray[np.intp]] = []
        if quebra.any():
            rr, kk = np.nonzero(quebra)
            forca = mo.toques[rr, kk] + mo.hist[rr, kk]
            valia = forca >= r.toques_min
            eh_res = mo.papel[rr, kk] == RESISTENCIA
            sobe = eh_res & valia
            ret.rompeu_res[i, rr[sobe]] = True
            ret.rompeu_res_preco[i, rr[sobe]] = mo.preco[rr[sobe], kk[sobe]]
            ret.rompeu_res_forca[i, rr[sobe]] = forca[sobe]
            ret.rompeu_sup[i, rr[~eh_res & valia]] = True
            mo.fechar(rr, kk, i, ROMPEU)
            # So troca de papel o nivel que valia e que nunca trocou. Nivel fraco
            # rompido nao era nivel; nivel que ja trocou e rompeu de novo morreu.
            vira = valia & (mo.hist[rr, kk] == 0)
            morre_r, morre_k = rr[~vira], kk[~vira]
            mo.papel[morre_r, morre_k] = 0
            mo.seg[morre_r, morre_k] = -1
            rr, kk = rr[vira], kk[vira]
            origem = mo.seg[rr, kk].copy()
            mo.hist[rr, kk] += mo.toques[rr, kk]
            mo.toques[rr, kk] = 0
            mo.papel[rr, kk] = -mo.papel[rr, kk]
            mo.inicio[rr, kk] = i
            mo.ultimo[rr, kk] = i
            mo.soma[rr, kk] = mo.preco[rr, kk]
            mo.npre[rr, kk] = 1
            mo.seguidos[rr, kk] = 0
            mo.abrir(rr, kk, origem, i)
            mudou_r.append(rr)
            mudou_k.append(kk)

        # 3. fundos e topos que ficam conhecidos hoje (aconteceram em j = i - pivo)
        j = i - r.pivo
        if j >= 0:
            for lado, marca, precos in ((SUPORTE, fundo, minima), (RESISTENCIA, topo, maxima)):
                rows = np.nonzero(marca[j])[0]
                if rows.size == 0:
                    continue
                p = precos[j, rows]
                tj = tol_ff[j, rows]
                aj = atr_ff[j, rows]
                cj = fechamento[j, rows]
                pr = mo.preco[rows]
                eleg = (mo.papel[rows] == lado) & (mo.inicio[rows] <= j)
                with np.errstate(invalid="ignore"):
                    d = np.abs(p[:, None] - pr)
                    dentro = d <= tj[:, None]
                    if lado == SUPORTE:
                        furo = (p[:, None] < pr) & (cj[:, None] >= pr - tj[:, None])
                    else:
                        furo = (p[:, None] > pr) & (cj[:, None] <= pr + tj[:, None])
                    furo &= (d <= r.furo_atr * aj[:, None]) & ~dentro
                ok = eleg & (dentro | furo)
                dd = np.where(ok, d, np.inf)
                kb = np.argmin(dd, axis=1)
                acha = np.isfinite(dd[np.arange(rows.size), kb])

                # toque num nivel que ja existe
                if acha.any():
                    r1 = rows[acha]
                    k1 = kb[acha]
                    f1 = furo[np.nonzero(acha)[0], k1]
                    p1 = p[acha]
                    mo.toques[r1, k1] += 1
                    conta = ~f1
                    mo.soma[r1[conta], k1[conta]] += p1[conta]
                    mo.npre[r1[conta], k1[conta]] += 1
                    mo.preco[r1, k1] = mo.soma[r1, k1] / mo.npre[r1, k1]
                    mo.ultimo[r1, k1] = j
                    mo.log_toque.append(
                        (
                            mo.seg[r1, k1].copy(),
                            r1.astype(np.int32),
                            np.full(r1.size, j, dtype=np.int32),
                            np.full(r1.size, i, dtype=np.int32),
                            p1,
                            f1,
                            mo.preco[r1, k1].copy(),
                        )
                    )
                    mudou_r.append(r1)
                    mudou_k.append(k1)

                # nivel novo
                if (~acha).any():
                    r2 = rows[~acha]
                    p2 = p[~acha]
                    livre = mo.papel[r2] == 0
                    tem_livre = livre.any(axis=1)
                    vale = (mo.toques[r2] + mo.hist[r2]) >= r.toques_min
                    prioridade = np.where(vale, mo.ultimo[r2] + n_dias + 1, mo.ultimo[r2])
                    k2 = np.where(
                        tem_livre, np.argmax(livre, axis=1), np.argmin(prioridade, axis=1)
                    )
                    desp = ~tem_livre
                    if desp.any():
                        mo.despejos += int(desp.sum())
                        mo.fechar(r2[desp], k2[desp], i, DESPEJADO)
                    mo.papel[r2, k2] = lado
                    mo.preco[r2, k2] = p2
                    mo.soma[r2, k2] = p2
                    mo.npre[r2, k2] = 1
                    mo.toques[r2, k2] = 1
                    mo.hist[r2, k2] = 0
                    mo.inicio[r2, k2] = j
                    mo.primeiro[r2, k2] = j
                    mo.ultimo[r2, k2] = j
                    mo.seguidos[r2, k2] = 0
                    mo.abrir(r2, k2, None, j)
                    mo.log_toque.append(
                        (
                            mo.seg[r2, k2].copy(),
                            r2.astype(np.int32),
                            np.full(r2.size, j, dtype=np.int32),
                            np.full(r2.size, i, dtype=np.int32),
                            p2,
                            np.zeros(r2.size, dtype=bool),
                            p2.copy(),
                        )
                    )
                    mudou_r.append(r2)
                    mudou_k.append(k2)

        # 4. fusao: so quem mudou hoje pode ter encostado em outro nivel
        if mudou_r:
            _fundir(mo, np.concatenate(mudou_r), np.concatenate(mudou_k), ti, i, vagas)

        # 5. retrato do fim do dia
        _retratar(mo, ret, i, c, ti, atr_ff[i], min_janela, cmin[i], cmax[i], r, ar)

    return ret, _eventos(mo)


def _fundir(
    mo: _Motor,
    rr: npt.NDArray[np.intp],
    kk: npt.NDArray[np.intp],
    ti: F64,
    dia: int,
    vagas: npt.NDArray[np.intp],
) -> None:
    pares = np.unique(np.stack([rr, kk], axis=1), axis=0)
    rr, kk = pares[:, 0], pares[:, 1]
    ocupado = mo.papel[rr, kk] != 0
    rr, kk = rr[ocupado], kk[ocupado]
    if rr.size == 0:
        return
    lado = mo.papel[rr, kk]
    mesmo = (mo.papel[rr] == lado[:, None]) & (vagas[None, :] != kk[:, None])
    with np.errstate(invalid="ignore"):
        d = np.abs(mo.preco[rr] - mo.preco[rr, kk][:, None])
        perto = mesmo & (d <= ti[rr][:, None])
    tem = perto.any(axis=1)
    if not tem.any():
        return
    parceiro = np.argmin(np.where(perto, d, np.inf), axis=1)
    # Fusoes sao raras (dezenas por pregao no universo inteiro): o laco e sobre
    # elas, nao sobre papeis.
    for r_, k_a, k_b in zip(rr[tem], kk[tem], parceiro[tem], strict=True):
        if mo.papel[r_, k_a] == 0 or mo.papel[r_, k_b] == 0:
            continue
        fa = mo.toques[r_, k_a] + mo.hist[r_, k_a]
        fb = mo.toques[r_, k_b] + mo.hist[r_, k_b]
        fica, sai = (
            (k_a, k_b) if (fa, -mo.primeiro[r_, k_a]) >= (fb, -mo.primeiro[r_, k_b]) else (k_b, k_a)
        )
        mo.fechar(
            np.array([r_]),
            np.array([sai]),
            dia,
            FUNDIDO,
            np.array([mo.seg[r_, fica]], dtype=np.int32),
        )
        mo.toques[r_, fica] += mo.toques[r_, sai]
        mo.hist[r_, fica] += mo.hist[r_, sai]
        mo.soma[r_, fica] += mo.soma[r_, sai]
        mo.npre[r_, fica] += mo.npre[r_, sai]
        mo.preco[r_, fica] = mo.soma[r_, fica] / mo.npre[r_, fica]
        mo.primeiro[r_, fica] = min(mo.primeiro[r_, fica], mo.primeiro[r_, sai])
        mo.ultimo[r_, fica] = max(mo.ultimo[r_, fica], mo.ultimo[r_, sai])
        mo.inicio[r_, fica] = min(mo.inicio[r_, fica], mo.inicio[r_, sai])
        mo.papel[r_, sai] = 0
        mo.seg[r_, sai] = -1


def _mais_perto(ok: B, preco: F64, acima: bool) -> tuple[npt.NDArray[np.intp], B]:
    if acima:
        idx = np.argmin(np.where(ok, preco, np.inf), axis=1)
    else:
        idx = np.argmax(np.where(ok, preco, -np.inf), axis=1)
    return np.asarray(idx, dtype=np.intp), np.asarray(ok.any(axis=1), dtype=bool)


def _retratar(
    mo: _Motor,
    ret: Retrato,
    i: int,
    c: F64,
    ti: F64,
    atr_i: F64,
    min_janela: list[F64],
    cmin_i: F64,
    cmax_i: F64,
    r: Regras,
    ar: npt.NDArray[np.intp],
) -> None:
    forca = mo.toques + mo.hist
    ocupado = mo.papel != 0
    valido = ocupado & (forca >= r.toques_min)
    ci = c[:, None]
    tcol = ti[:, None]
    with np.errstate(invalid="ignore"):
        sup_ok = valido & (mo.papel == SUPORTE) & (mo.preco <= ci + tcol)
        res_ok = valido & (mo.papel == RESISTENCIA) & (mo.preco >= ci - tcol)
    idx, tem = _mais_perto(sup_ok, mo.preco, acima=False)
    ret.sup_preco[i] = np.where(tem, mo.preco[ar, idx], np.nan)
    ret.sup_forca[i] = np.where(tem, forca[ar, idx], 0)
    ret.sup_seg[i] = np.where(tem, mo.seg[ar, idx], -1)
    ret.sup_virou[i] = tem & (mo.hist[ar, idx] > 0)
    idx, tem = _mais_perto(res_ok, mo.preco, acima=True)
    ret.res_preco[i] = np.where(tem, mo.preco[ar, idx], np.nan)
    ret.res_forca[i] = np.where(tem, forca[ar, idx], 0)
    ret.res_seg[i] = np.where(tem, mo.seg[ar, idx], -1)

    base = valido & (mo.papel == SUPORTE) & (mo.inicio < i)
    for camada, mj in enumerate(min_janela):
        low = mj[i][:, None]
        with np.errstate(invalid="ignore"):
            ok = (
                base
                & (low <= mo.preco + tcol)
                & (low >= mo.preco - r.furo_atr * atr_i[:, None])
                & (ci >= mo.preco - tcol)
            )
        idx = np.argmax(np.where(ok, forca, -1), axis=1)
        tem = ok.any(axis=1)
        p = mo.preco[ar, idx]
        ret.toca_preco[camada, i] = np.where(tem, p, np.nan)
        ret.toca_forca[camada, i] = np.where(tem, forca[ar, idx], 0)
        ret.toca_seg[camada, i] = np.where(tem, mo.seg[ar, idx], -1)
        with np.errstate(invalid="ignore"):
            ret.toca_furou[camada, i] = tem & (mj[i] < p - ti)
        ret.toca_virou[camada, i] = tem & (mo.hist[ar, idx] > 0)

    # lateralizacao: caixa entre suporte e resistencia com toques suficientes
    v2 = ocupado & (forca >= r.caixa_toques)
    with np.errstate(invalid="ignore"):
        s2 = v2 & (mo.papel == SUPORTE) & (mo.preco <= ci + tcol)
        r2 = v2 & (mo.papel == RESISTENCIA) & (mo.preco >= ci - tcol)
    ks, ts = _mais_perto(s2, mo.preco, acima=False)
    kr, tr = _mais_perto(r2, mo.preco, acima=True)
    sp = mo.preco[ar, ks]
    rp = mo.preco[ar, kr]
    prim = np.minimum(mo.primeiro[ar, ks], mo.primeiro[ar, kr])
    with np.errstate(invalid="ignore", divide="ignore"):
        altura = (rp - sp) / sp
        caixa = (
            ts
            & tr
            & (altura <= r.caixa_max_pct)
            & (cmin_i >= sp - ti)
            & (cmax_i <= rp + ti)
            & (prim <= i - r.caixa_pregoes + 1)
        )
    ret.caixa_altura[i] = np.where(caixa, altura, np.nan)


def _retrato_vazio(n_dias: int, n_papeis: int) -> Retrato:
    def f32(*forma: int) -> F32:
        return np.full(forma, np.nan, dtype=np.float32)

    def i16(*forma: int) -> I16:
        return np.zeros(forma, dtype=np.int16)

    def i32(*forma: int) -> I32:
        return np.full(forma, -1, dtype=np.int32)

    def bo(*forma: int) -> B:
        return np.zeros(forma, dtype=bool)

    d, t, j = n_dias, n_papeis, len(JANELAS_DE_TOQUE)
    return Retrato(
        tol=f32(d, t),
        sup_preco=f32(d, t),
        sup_forca=i16(d, t),
        sup_seg=i32(d, t),
        sup_virou=bo(d, t),
        res_preco=f32(d, t),
        res_forca=i16(d, t),
        res_seg=i32(d, t),
        toca_preco=f32(j, d, t),
        toca_forca=i16(j, d, t),
        toca_seg=i32(j, d, t),
        toca_furou=bo(j, d, t),
        toca_virou=bo(j, d, t),
        rompeu_res=bo(d, t),
        rompeu_res_preco=f32(d, t),
        rompeu_res_forca=i16(d, t),
        rompeu_sup=bo(d, t),
        caixa_altura=f32(d, t),
    )


def _eventos(mo: _Motor) -> Eventos:
    def junta(partes: Sequence[tuple[npt.NDArray[Any], ...]], nomes: list[str]) -> pd.DataFrame:
        if not partes:
            return pd.DataFrame({n: pd.Series(dtype="float64") for n in nomes})
        colunas = list(zip(*partes, strict=True))
        return pd.DataFrame({n: np.concatenate(c) for n, c in zip(nomes, colunas, strict=True)})

    seg = junta(mo.log_seg, ["seg", "nivel", "col", "lado", "inicio", "origem", "preco_inicial"])
    fim = junta(mo.log_fim, ["seg", "fim", "motivo", "preco_final", "fundido_em"])
    toques = junta(
        mo.log_toque,
        ["seg", "col", "dia", "conf", "preco", "furo", "preco_nivel"],
    )
    segmentos = seg.merge(fim, on="seg", how="left")
    resumo = {
        "segmentos": len(segmentos),
        "toques": len(toques),
        "rompidos": int((fim["motivo"] == ROMPEU).sum()) if len(fim) else 0,
        "fundidos": int((fim["motivo"] == FUNDIDO).sum()) if len(fim) else 0,
        "esquecidos": int((fim["motivo"] == ESQUECIDO).sum()) if len(fim) else 0,
    }
    return Eventos(segmentos=segmentos, toques=toques, despejos=mo.despejos, resumo=resumo)
