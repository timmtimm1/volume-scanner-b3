"""A suite de backtest: todo setup x toda saida, num lote de papeis.

Pedido do usuario em 05/11/2026 ("suites de backtest"), rodado na maquina sobre
o COTAHIST desde 1995; so o resultado vai para o app.

Para cada trade do setup, um trade de CONTROLE: no mesmo dia do sinal, um papel
sorteado entre os liquidos do lote, comprado na abertura seguinte, com o stop a
mesma distancia (em %) e a mesma saida. O setup so vale alguma coisa se ganhar
do controle -- senao o "ganho" e so o mercado subindo naquele periodo.

Um trade por vez por papel e setup: enquanto um trade esta aberto, sinais novos
do mesmo setup no mesmo papel sao ignorados, como faria quem opera.

Universo de cada dia sem olhar o futuro (`liquidez_historica`): mediana do
volume dos 60 pregoes anteriores acima do piso, com negocio em 48 desses 60. O
piso e o R$ 500 mil de hoje escalado pelo tamanho do mercado de cada epoca --
a mesma regra do estudo dos Setups (`scripts/gatilhos_estudo.py`).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd

from scanner.backtest.simulador import SAIDAS, Precos, Saida, entrar, simular
from scanner.config import SetupsConfig
from scanner.gatilhos.candles import padroes
from scanner.gatilhos.classicos import CENTAVO, Sinal, classicos, tendencia_de_alta
from scanner.gatilhos.contexto import atr_wilder, calcular
from scanner.gatilhos.matrizes import ajuste_acumulado, montar
from scanner.gatilhos.medias import RegrasDaMedia, toques_na_media
from scanner.gatilhos.niveis import Regras, detectar
from scanner.gatilhos.regra import Analise
from scanner.gatilhos.regra import setups as setups_da_regra

F64 = npt.NDArray[np.float64]
I64 = npt.NDArray[np.int64]
B = npt.NDArray[np.bool_]

# 0,03% de taxas da B3 + 0,05% de derrapagem, por lado.
CUSTO = 0.0008
# Risco menor que 0,2% do preco nao vira trade: o R minusculo explode o resultado.
RISCO_MIN = 0.002
PISO_HOJE = 500_000.0
JANELA_LIQUIDEZ = 60
MINIMO_DE_PREGOES = 48
# Categorias da regra dos Setups de hoje, com o nome que tem na suite.
DA_REGRA = {"reversao": "suporte", "media": "media", "forca": "forca"}


def liquidez_historica(barras: pd.DataFrame, sessoes: pd.DatetimeIndex) -> pd.DataFrame:
    """Booleano (pregao x papel): o papel era liquido naquele dia."""
    pos = pd.Series(np.arange(len(sessoes)), index=sessoes)
    datas = pd.to_datetime(barras["trade_date"])
    b = barras.assign(s=pos.loc[datas].to_numpy(), trade_date=datas)
    mercado = b.groupby("s")["volume_financial"].sum().reindex(range(len(sessoes)))
    m250 = mercado.rolling(250, min_periods=60).median().bfill()
    piso = PISO_HOJE * m250 / m250.iloc[-1]
    b = b.sort_values(["ticker", "s"])
    g = b.groupby("ticker", observed=True)
    med = g["volume_financial"].transform(
        lambda x: x.shift(1).rolling(JANELA_LIQUIDEZ, min_periods=MINIMO_DE_PREGOES).median()
    )
    cobre = (b["s"] - g["s"].shift(MINIMO_DE_PREGOES)) <= JANELA_LIQUIDEZ
    liquido = (med >= piso.to_numpy()[b["s"].to_numpy()]) & cobre
    largo = (
        pd.DataFrame({"s": b["s"], "ticker": b["ticker"].astype(str), "ok": liquido.to_numpy()})
        .pivot(index="s", columns="ticker", values="ok")
        .reindex(range(len(sessoes)))
        .fillna(False)
        .astype(bool)
    )
    largo.index = sessoes
    return largo


def sem_sobreposicao(col: I64, dia_entrada: I64, dia_saida: I64) -> B:
    """Um trade por vez por papel: descarta quem entra antes do anterior sair.

    Trade ainda aberto (`dia_saida` -1) bloqueia tudo depois dele.
    """
    n = col.size
    fica = np.zeros(n, dtype=bool)
    if n == 0:
        return fica
    ordem = np.lexsort((dia_entrada, col))
    saida = np.where(dia_saida < 0, np.iinfo(np.int64).max, dia_saida)
    ultimo_col, livre_em = -1, -1
    for i in ordem:
        if col[i] != ultimo_col:
            ultimo_col, livre_em = int(col[i]), -1
        if dia_entrada[i] > livre_em:
            fica[i] = True
            livre_em = int(saida[i])
    return fica


def sortear(ok: B, dias: I64, fora: I64, rng: np.random.Generator, bloco: int = 20_000) -> I64:
    """Para cada dia pedido, uma coluna sorteada entre as `ok` daquele dia (-1 se nenhuma).

    `fora`: a coluna que nao pode sair em cada sorteio (o proprio papel do trade).
    """
    escolha = np.full(dias.size, -1, dtype=np.int64)
    for ini in range(0, dias.size, bloco):
        d = dias[ini : ini + bloco]
        chave = rng.random((d.size, ok.shape[1]))
        validos = ok[d].copy()
        validos[np.arange(d.size), fora[ini : ini + bloco]] = False
        chave[~validos] = -1.0
        idx = np.argmax(chave, axis=1)
        escolha[ini : ini + bloco] = np.where(validos[np.arange(d.size), idx], idx, -1)
    return escolha


def _sinais_da_regra(a: Analise, cfg: SetupsConfig, tick: F64) -> dict[str, Sinal]:
    """Os Setups de hoje (suporte, na media, forca) como `Sinal` na escala ajustada."""
    linhas = setups_da_regra(a, cfg)
    forma = a.m.fechamento.shape
    pos_dia = pd.Series(np.arange(forma[0]), index=a.m.datas.date)
    pos_col = pd.Series(np.arange(forma[1]), index=a.m.tickers)
    saida: dict[str, Sinal] = {}
    for categoria, nome in DA_REGRA.items():
        parte = linhas[linhas["categoria"] == categoria]
        armado = np.zeros(forma, dtype=bool)
        gatilho = np.full(forma, np.nan)
        stop = np.full(forma, np.nan)
        if not parte.empty:
            dd = pos_dia.loc[parte["trade_date"]].to_numpy()
            tt = pos_col.loc[parte["ticker"]].to_numpy()
            escala = a.ajuste[dd, tt]
            armado[dd, tt] = True
            gatilho[dd, tt] = parte["maxima"].to_numpy(dtype=np.float64) * escala + tick[dd, tt]
            stop[dd, tt] = parte["minima"].to_numpy(dtype=np.float64) * escala - tick[dd, tt]
        saida[nome] = Sinal(armado=armado, gatilho=gatilho, stop=stop)
    return saida


def rodar_lote(
    barras: pd.DataFrame,
    tickers: list[str],
    sessoes: pd.DatetimeIndex,
    liquidez: pd.DataFrame,
    cfg: SetupsConfig,
    semente: int,
    custo: float = CUSTO,
    saidas: tuple[Saida, ...] = SAIDAS,
) -> pd.DataFrame:
    """Todos os trades (setup x saida) dos papeis do lote."""
    m = montar(barras, tickers, sessoes)
    o, h, low, c = m.abertura, m.maxima, m.minima, m.fechamento
    ajuste = ajuste_acumulado(m.fator)
    tick = CENTAVO * ajuste
    atr = atr_wilder(h, low, c)
    ctx = calcular(h, c, m.volume)
    retrato, eventos = detectar(h, low, c, atr, Regras(toques_min=cfg.toques_nivel))
    liquido = liquidez.reindex(index=sessoes, columns=tickers).fillna(False).to_numpy(dtype=bool)
    analise = Analise(
        m=m,
        ajuste=ajuste,
        atr=atr,
        contexto=ctx,
        padroes=padroes(o, h, low, c, atr),
        retrato=retrato,
        eventos=eventos,
        liquido=liquido,
        medias=toques_na_media(low, c, atr, RegrasDaMedia(medias=tuple(cfg.medias))),
    )
    sinais = classicos(o, h, low, c, tick, retrato, eventos)
    sinais.update(_sinais_da_regra(analise, cfg, tick))
    alta = tendencia_de_alta(c)
    precos = Precos.de(o, h, low, c, tick)
    rvol = np.asarray(ctx["rvol"], dtype=np.float64)
    z = np.asarray(ctx["z"], dtype=np.float64)
    rng = np.random.default_rng(semente)
    # controle: liquido no dia do sinal e com pregao no dia seguinte
    abre_amanha = np.zeros_like(liquido)
    abre_amanha[:-1] = np.isfinite(o[1:])
    pode_controle = liquido & abre_amanha
    datas = m.datas.to_numpy()
    nomes_tickers = np.asarray(m.tickers)

    partes: list[pd.DataFrame] = []
    for nome, sinal in sinais.items():
        dd, tt = np.nonzero(sinal.armado & liquido)
        if dd.size == 0:
            continue
        ent = entrar(precos, dd.astype(np.int64), tt.astype(np.int64), sinal.gatilho[dd, tt])
        stop = sinal.stop[dd, tt]
        with np.errstate(invalid="ignore"):
            risco = ent.preco - stop
            ok = ent.entrou & (risco >= RISCO_MIN * ent.preco)
        if not ok.any():
            continue
        dd, tt, stop, risco = dd[ok], tt[ok], stop[ok], risco[ok]
        dia_e, preco_e = ent.dia[ok], ent.preco[ok]
        risco_pct = risco / preco_e
        ctrl = sortear(pode_controle, dd.astype(np.int64), tt.astype(np.int64), rng)
        tem_ctrl = ctrl >= 0
        cc = np.where(tem_ctrl, ctrl, 0)
        preco_ctrl = np.where(tem_ctrl, o[np.minimum(dia_e, len(datas) - 1), cc], np.nan)
        stop_ctrl = preco_ctrl * (1 - risco_pct)
        for saida in saidas:
            res = simular(precos, dia_e, tt, preco_e, stop, saida, custo, low[dd, tt])
            fica = sem_sobreposicao(tt.astype(np.int64), dia_e, res.dia_saida)
            ctl = simular(precos, dia_e, cc, preco_ctrl, stop_ctrl, saida, custo, low[dd, cc])
            i = np.nonzero(fica)[0]
            fim = res.dia_saida[i]
            partes.append(
                pd.DataFrame(
                    {
                        "setup": nome,
                        "saida": saida.nome,
                        "ticker": nomes_tickers[tt[i]],
                        "data_sinal": datas[dd[i]],
                        "data_entrada": datas[dia_e[i]],
                        "data_saida": np.where(
                            fim >= 0, datas[np.maximum(fim, 0)], np.datetime64("NaT")
                        ),
                        # precos na escala do proprio dia da entrada (a do grafico)
                        "entrada": (preco_e[i] / ajuste[dia_e[i], tt[i]]).astype(np.float32),
                        "stop": (stop[i] / ajuste[dia_e[i], tt[i]]).astype(np.float32),
                        "risco_pct": risco_pct[i].astype(np.float32),
                        "motivo": res.motivo[i],
                        "dias": np.where(fim >= 0, fim - dia_e[i], -1).astype(np.int16),
                        "r": res.r[i].astype(np.float32),
                        "r_bruto": res.r_bruto[i].astype(np.float32),
                        "r_controle": np.where(tem_ctrl[i], ctl.r[i], np.nan).astype(np.float32),
                        "alta": alta[dd[i], tt[i]],
                        "rvol": rvol[dd[i], tt[i]].astype(np.float32),
                        "z": z[dd[i], tt[i]].astype(np.float32),
                    }
                )
            )
    if not partes:
        return pd.DataFrame()
    saida_df = pd.concat(partes, ignore_index=True)
    for col in ("setup", "saida", "ticker"):
        saida_df[col] = saida_df[col].astype("category")
    return saida_df
