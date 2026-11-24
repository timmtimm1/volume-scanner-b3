"""Cada cripto contra o Bitcoin, mes a mes e ano a ano (pedido de 24/11/2026).

O usuario quer ver quais moedas ficaram mais fortes ou mais fracas que o
Bitcoin com o passar do tempo, a sazonalidade disso (o mes costuma ser bom ou
ruim?), e o beta e a correlacao de cada uma com o Bitcoin. Aqui so a conta: as
moedas chegam como fechamentos diarios (`scanner.cripto.historico` cuida da
carga) e saem as tabelas que o site mostra na pagina Analise.

As regras:

- **Retorno do periodo** (mes ou ano civil, em dias UTC, o dia do candle da
  Binance): do ultimo fechamento ANTES do periodo ate o ultimo fechamento
  DENTRO dele. Quem estreou no meio do periodo parte do primeiro fechamento e
  fica `parcial`; quem parou antes do fim (deslistada, ou o periodo de hoje)
  tambem.
- **O Bitcoin e medido nas mesmas duas datas** da moeda, nem um dia a mais: uma
  moeda que estreou em 10 de marco e comparada com o Bitcoin de 10 de marco em
  diante.
- **Contra o BTC** = (1 + retorno da moeda) / (1 + retorno do BTC) - 1. E o
  retorno da moeda medida em bitcoin: quanto de BTC a mais (ou a menos) teria
  quem trocasse 1 BTC pela moeda no comeco do periodo. Positivo = mais forte.
- **Beta e correlacao** saem dos retornos DIARIOS (fechamento sobre o do dia
  anterior, so com os dois dias presentes na moeda e no BTC), com pelo menos 60
  dias na conta. Beta = cov(moeda, BTC) / var(BTC): beta 1,5 quer dizer que, num
  dia em que o BTC anda 1%, a moeda costuma andar 1,5% para o mesmo lado.
- **Janela movel**: o mesmo beta e a mesma correlacao com os ultimos 90 dias,
  um ponto por semana (o ultimo e sempre o dia mais recente).
- **A serie recomeca** (nenhum retorno atravessa o ponto, e o "periodo todo" e
  o trecho mais recente) em dois casos, medidos no historico de 684 moedas em
  24/11/2026:
  - buraco de mais de 30 dias sem candle (FTT parada 311 dias depois da quebra
    da FTX, CVC 154, a VEN virando VET);
  - pausa de 2 dias ou mais em que o preco volta 5 vezes maior ou menor: e
    troca de token com mudanca de escala (COCOS x1.295, DREP x108, QUICK
    /1.243, SUN /834, BNX /111, STRAX, BTCST e VIDT perto de /10), ou outra
    moeda no mesmo par (a LUNA nova em 31/05/2022, x177.400 depois de 18 dias).
  Salto de preco SEM pausa nunca e cortado: o -99,97% da LUNA em 12/05/2022
  aconteceu (e o unico do historico acima de 20 vezes num dia).

E descricao do passado, nao previsao: nao alimenta alerta, setup nem backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

BENCHMARK = "BTC"
LACUNA_MAXIMA = 30
# Pausa de 2+ dias com o preco voltando 5x maior ou menor: troca de escala.
SALTO_DE_ESCALA = 5.0
MINIMO_DE_DIAS = 60
JANELA_MOVEL = 90
MINIMO_NA_JANELA = 60
PASSO_MOVEL = 7
# O ultimo candle pode faltar um ou outro dia (manutencao da corretora): ate
# esta distancia do fim, o periodo conta como inteiro.
TOLERANCIA_NO_FIM = 6
# `ano` da linha do periodo inteiro na tabela anual.
ANO_TOTAL = 0

COLUNAS_DO_PERIODO = (
    "moeda",
    "periodo",
    "inicio",
    "fim",
    "parcial",
    "retorno",
    "retorno_btc",
    "relativo",
)
COLUNAS_ANUAIS = (
    "moeda",
    "ano",
    "inicio",
    "fim",
    "parcial",
    "retorno",
    "retorno_btc",
    "relativo",
    "beta",
    "correlacao",
    "dias",
)
COLUNAS_MENSAIS = ("moeda", "mes", "inicio", "fim", "parcial", "retorno", "retorno_btc", "relativo")
COLUNAS_MOVEIS = ("moeda", "dia", "beta", "correlacao", "dias")
COLUNAS_DO_RESUMO = ("moeda", "primeiro_dia", "ultimo_dia", "volume_12m")


@dataclass(frozen=True)
class Analise:
    """As quatro tabelas da pagina Analise."""

    anual: pd.DataFrame
    mensal: pd.DataFrame
    movel: pd.DataFrame
    resumo: pd.DataFrame


def _observacoes(fech: pd.DataFrame) -> pd.DataFrame:
    """Matriz larga -> uma linha por candle (moeda, dia, fechamento, seg).

    `seg` numera os trechos de cada moeda: comeca em 1 e sobe a cada buraco de
    mais de `LACUNA_MAXIMA` dias e a cada troca de escala depois de uma pausa.
    """
    longo = fech.rename_axis(index="dia", columns=None).reset_index()
    longo = longo.melt(id_vars="dia", var_name="moeda", value_name="fechamento")
    longo = longo.dropna(subset=["fechamento"])
    obs = longo.sort_values(["moeda", "dia"], kind="stable").reset_index(drop=True)
    por_moeda = obs.groupby("moeda")
    pausa = por_moeda["dia"].diff().dt.days
    razao = obs["fechamento"] / por_moeda["fechamento"].shift(1)
    escala = (pausa > 1) & ((razao > SALTO_DE_ESCALA) | (razao < 1.0 / SALTO_DE_ESCALA))
    novo = pausa.isna() | (pausa > LACUNA_MAXIMA) | escala
    obs["seg"] = novo.astype("int64").groupby(obs["moeda"]).cumsum()
    return obs


def _primeiro_e_ultimo(fech: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Dia do primeiro e do ultimo candle de cada moeda, e quem tem algum."""
    presente = fech.notna()
    tem = presente.any()
    primeiro = presente.idxmax()
    ultimo = presente.iloc[::-1].idxmax()
    return primeiro, ultimo, tem


def _btc_no_dia(fech: pd.DataFrame, dias: pd.Series) -> np.ndarray:
    """Fechamento do BTC em cada dia pedido (o ultimo conhecido ate ele)."""
    btc = fech[BENCHMARK].ffill()
    return btc.reindex(pd.DatetimeIndex(dias)).to_numpy(dtype="float64")


def retornos_por_periodo(fech: pd.DataFrame, freq: Literal["Y", "M"]) -> pd.DataFrame:
    """Retorno de cada moeda em cada ano (`Y`) ou mes (`M`), contra o BTC nas mesmas datas.

    `fech`: indice diario continuo (todo dia do calendario), uma coluna por
    moeda, NaN no dia sem candle. Precisa da coluna do BTC.
    """
    obs = _observacoes(fech)
    if obs.empty:
        return pd.DataFrame(columns=list(COLUNAS_DO_PERIODO))
    obs["periodo"] = obs["dia"].dt.to_period(freq)
    grupos = (
        obs.groupby(["moeda", "seg", "periodo"], sort=True)
        .agg(
            primeiro_dia=("dia", "first"),
            primeiro=("fechamento", "first"),
            fim=("dia", "last"),
            ultimo=("fechamento", "last"),
        )
        .reset_index()
    )
    # O fechamento de partida e o ultimo do periodo anterior NO MESMO TRECHO.
    anterior = grupos.groupby(["moeda", "seg"])[["fim", "ultimo"]].shift(1)
    tem_anterior = anterior["fim"].notna()
    grupos["inicio"] = anterior["fim"].where(tem_anterior, grupos["primeiro_dia"])
    grupos["partida"] = anterior["ultimo"].where(tem_anterior, grupos["primeiro"])
    grupos["parcial_no_inicio"] = ~tem_anterior
    # Um candle so (estreia no ultimo dia do periodo) nao tem retorno. Sai antes
    # da escolha abaixo, para o trecho anterior ainda valer naquele periodo.
    grupos = grupos[grupos["fim"] > grupos["inicio"]]
    # Periodo com dois trechos (o recomeco caiu dentro dele): vale o mais recente.
    grupos = grupos.loc[grupos.groupby(["moeda", "periodo"])["seg"].idxmax()].reset_index(drop=True)

    fim_do_periodo = grupos["periodo"].dt.end_time.dt.normalize()
    curto = grupos["fim"] < fim_do_periodo - pd.Timedelta(days=TOLERANCIA_NO_FIM)
    retorno = grupos["ultimo"] / grupos["partida"] - 1.0
    btc_fim = _btc_no_dia(fech, grupos["fim"])
    btc_inicio = _btc_no_dia(fech, grupos["inicio"])
    retorno_btc = btc_fim / btc_inicio - 1.0
    return pd.DataFrame(
        {
            "moeda": grupos["moeda"].astype(str),
            "periodo": grupos["periodo"].dt.start_time.dt.date,
            "inicio": grupos["inicio"].dt.date,
            "fim": grupos["fim"].dt.date,
            "parcial": (grupos["parcial_no_inicio"] | curto).to_numpy(dtype=bool),
            "retorno": retorno.to_numpy(dtype="float64"),
            "retorno_btc": retorno_btc,
            "relativo": (1.0 + retorno.to_numpy(dtype="float64")) / (1.0 + retorno_btc) - 1.0,
        }
    )


def retornos_diarios(fech: pd.DataFrame) -> pd.DataFrame:
    """Fechamento sobre o do dia anterior; NaN se faltar um dos dois dias."""
    return fech / fech.shift(1) - 1.0


def _beta_e_correlacao(
    x: np.ndarray, y: np.ndarray, minimo: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Beta de x contra y e a correlacao, coluna a coluna, so nos dias com os dois.

    `x` (dias x moedas), `y` (dias x 1, o BTC). Conta em duas passadas (media
    primeiro, desvio depois), que nao perde precisao com retorno pequeno.
    """
    par = ~np.isnan(x) & ~np.isnan(y)
    n = par.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mx = np.where(par, x, 0.0).sum(axis=0) / n
        my = np.where(par, y, 0.0).sum(axis=0) / n
        dx = np.where(par, x - mx, 0.0)
        dy = np.where(par, y - my, 0.0)
        cov = (dx * dy).sum(axis=0)
        vx = (dx * dx).sum(axis=0)
        vy = (dy * dy).sum(axis=0)
        beta = cov / vy
        corr = cov / np.sqrt(vx * vy)
    valido = (n >= minimo) & (vx > 0) & (vy > 0)
    return np.where(valido, beta, np.nan), np.where(valido, corr, np.nan), n


def beta_por_ano(fech: pd.DataFrame) -> pd.DataFrame:
    """Beta e correlacao diarios contra o BTC, por moeda e ano civil."""
    ret = retornos_diarios(fech)
    btc = ret[[BENCHMARK]].to_numpy(dtype="float64")
    x = ret.to_numpy(dtype="float64")
    anos = pd.DatetimeIndex(ret.index).year
    partes: list[pd.DataFrame] = []
    for ano in np.unique(anos):
        linhas = anos == ano
        beta, corr, n = _beta_e_correlacao(x[linhas], btc[linhas], MINIMO_DE_DIAS)
        partes.append(
            pd.DataFrame(
                {"moeda": ret.columns, "ano": int(ano), "beta": beta, "correlacao": corr, "dias": n}
            )
        )
    if not partes:
        return pd.DataFrame(columns=["moeda", "ano", "beta", "correlacao", "dias"])
    return pd.concat(partes, ignore_index=True)


def _trecho_mais_recente(fech: pd.DataFrame) -> pd.DataFrame:
    """A matriz so com o trecho mais recente de cada moeda (o resto vira NaN)."""
    obs = _observacoes(fech)
    ultimo = obs.groupby("moeda")["seg"].transform("max")
    recente = obs[obs["seg"] == ultimo]
    return (
        recente.pivot(index="dia", columns="moeda", values="fechamento")
        .reindex(index=fech.index, columns=fech.columns)
        .astype("float64")
    )


def periodo_todo(fech: pd.DataFrame) -> pd.DataFrame:
    """Do primeiro ao ultimo fechamento do trecho mais recente de cada moeda."""
    trecho = _trecho_mais_recente(fech)
    # O BTC entra inteiro: e a regua, e e medido nas datas de cada moeda.
    trecho[BENCHMARK] = fech[BENCHMARK]
    inicio, fim, tem = _primeiro_e_ultimo(trecho)
    moedas = trecho.columns[tem.to_numpy()]
    inicio, fim = inicio[moedas], fim[moedas]
    # O primeiro valor de cada coluna e o da primeira linha depois de puxar os
    # valores para cima (bfill); o ultimo, o da ultima depois de puxar para baixo.
    primeiro = trecho[moedas].bfill().iloc[0].to_numpy(dtype="float64")
    ultimo = trecho[moedas].ffill().iloc[-1].to_numpy(dtype="float64")
    retorno = ultimo / primeiro - 1.0
    retorno_btc = _btc_no_dia(fech, fim) / _btc_no_dia(fech, inicio) - 1.0

    ret = retornos_diarios(trecho)
    beta, corr, n = _beta_e_correlacao(
        ret[moedas].to_numpy(dtype="float64"),
        ret[[BENCHMARK]].to_numpy(dtype="float64"),
        MINIMO_DE_DIAS,
    )
    frame = pd.DataFrame(
        {
            "moeda": [str(m) for m in moedas],
            "ano": ANO_TOTAL,
            "inicio": pd.DatetimeIndex(inicio).date,
            "fim": pd.DatetimeIndex(fim).date,
            "parcial": False,
            "retorno": retorno,
            "retorno_btc": retorno_btc,
            "relativo": (1.0 + retorno) / (1.0 + retorno_btc) - 1.0,
            "beta": beta,
            "correlacao": corr,
            "dias": n,
        }
    )
    return frame[frame["fim"] > frame["inicio"]].reset_index(drop=True)


def janela_movel(fech: pd.DataFrame) -> pd.DataFrame:
    """Beta e correlacao dos ultimos 90 dias, um ponto a cada 7 dias ate o mais recente."""
    ret = retornos_diarios(fech)
    x = ret.to_numpy(dtype="float64")
    y = ret[[BENCHMARK]].to_numpy(dtype="float64")
    par = ~np.isnan(x) & ~np.isnan(y)
    xs = np.where(par, x, 0.0)
    ys = np.where(par, np.broadcast_to(y, x.shape), 0.0)

    def soma(m: np.ndarray) -> np.ndarray:
        acumulado = np.cumsum(m, axis=0)
        atras = np.zeros_like(acumulado)
        atras[JANELA_MOVEL:] = acumulado[:-JANELA_MOVEL]
        return np.asarray(acumulado - atras)

    pontos = np.arange(len(ret) - 1, -1, -PASSO_MOVEL)[::-1]
    n = soma(par.astype("float64"))[pontos]
    sx, sy = soma(xs)[pontos], soma(ys)[pontos]
    sxx, syy, sxy = soma(xs * xs)[pontos], soma(ys * ys)[pontos], soma(xs * ys)[pontos]
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = sxy - sx * sy / n
        vx = sxx - sx * sx / n
        vy = syy - sy * sy / n
        beta = cov / vy
        corr = cov / np.sqrt(vx * vy)
    # Variancia "zero" pela conta de uma passada sai como resto de arredondamento.
    valido = (n >= MINIMO_NA_JANELA) & (vx > 1e-12) & (vy > 1e-12)
    dias = np.repeat(pd.DatetimeIndex(ret.index)[pontos].date, len(ret.columns))
    frame = pd.DataFrame(
        {
            "moeda": np.tile(np.asarray(ret.columns, dtype=object), len(pontos)),
            "dia": dias,
            "beta": beta.ravel(),
            "correlacao": np.clip(corr.ravel(), -1.0, 1.0),
            "dias": n.ravel().astype("int64"),
            "valido": valido.ravel(),
        }
    )
    return (
        frame[frame["valido"]]
        .drop(columns="valido")
        .sort_values(["moeda", "dia"])
        .reset_index(drop=True)
    )


def resumo(fech: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    """Primeiro e ultimo candle de cada moeda e o volume em dolar dos ultimos 365 dias."""
    primeiro, ultimo, tem = _primeiro_e_ultimo(fech)
    recentes = vol.reindex(index=fech.index, columns=fech.columns).iloc[-365:]
    return pd.DataFrame(
        {
            "moeda": [str(m) for m in fech.columns[tem.to_numpy()]],
            "primeiro_dia": pd.DatetimeIndex(primeiro[tem]).date,
            "ultimo_dia": pd.DatetimeIndex(ultimo[tem]).date,
            "volume_12m": recentes.sum(min_count=0).to_numpy(dtype="float64")[tem.to_numpy()],
        }
    ).reset_index(drop=True)


def calcular(fech: pd.DataFrame, vol: pd.DataFrame) -> Analise:
    """As tabelas da pagina Analise a partir dos fechamentos e volumes diarios."""
    if BENCHMARK not in fech.columns:
        raise ValueError(f"sem o {BENCHMARK} nao ha regua para comparar")
    fech = fech.astype("float64")
    anos = retornos_por_periodo(fech, "Y").rename(columns={"periodo": "ano"})
    anos["ano"] = pd.to_datetime(anos["ano"]).dt.year.astype("int64")
    anual = anos.merge(beta_por_ano(fech), on=["moeda", "ano"], how="left")
    anual["dias"] = anual["dias"].fillna(0).astype("int64")
    anual = pd.concat(
        [anual.loc[:, list(COLUNAS_ANUAIS)], periodo_todo(fech).loc[:, list(COLUNAS_ANUAIS)]],
        ignore_index=True,
    )
    mensal = retornos_por_periodo(fech, "M").rename(columns={"periodo": "mes"})
    return Analise(
        anual=anual.sort_values(["moeda", "ano"]).reset_index(drop=True),
        mensal=mensal.loc[:, list(COLUNAS_MENSAIS)],
        movel=janela_movel(fech),
        resumo=resumo(fech, vol),
    )
