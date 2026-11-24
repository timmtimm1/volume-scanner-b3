"""Quando comprar e quando vender a cesta das criptos mais negociadas (24/11/2026).

Pedido do usuario: nao so o mapa de sazonalidade, mas a resposta -- qual o
melhor periodo do ano para operar comprado e vendido na media das principais
criptos. Escolhas dele (por perguntas): a cesta das 50 mais negociadas, venda a
descoberto com a taxa de futuros, janelas de 1 a 6 meses, e o protocolo da casa
(escolhe em 2017-2021, confere em 2022-2026).

- **A cesta**: em cada mes, as 50 moedas com mais volume em dolar nos 90 dias
  anteriores ao comeco do mes (pelo menos 60 dias com negocio), so com o que se
  sabia na epoca. O retorno do mes e a media simples dos retornos delas (o que
  ganharia quem tivesse um pouco de cada). A moeda que para no meio do mes entra
  com o retorno ate o ultimo candle; o retorno de cada moeda e o de
  `analise.retornos_por_periodo` (com os recomecos de serie).
- **As janelas**: comecam em cada mes do ano e duram de 1 a 6 meses ("mai +6" =
  maio a outubro). Compra = o produto de (1 + mes) menos a taxa a vista na
  entrada e na saida. Venda a descoberto = o produto de (1 - mes) menos a taxa
  dos futuros: o vendido refeito todo mes ganha quando a cesta cai. Sem funding
  e sem o custo de rebalancear dentro da janela.
- **O protocolo**: cada janela e julgada contra uma janela QUALQUER do mesmo
  tamanho e do mesmo lado (a media de todos os comecos possiveis), que e o
  "controle" da casa: ganhar dinheiro numa alta geral nao e merito do mes. A
  ordem e feita so com as janelas que terminam ate o fim do periodo de escolha;
  a conferencia usa as que comecam depois dele. O veredito: "repetiu" (na
  conferencia deu lucro E ganhou da janela qualquer), "em parte" (so um dos dois)
  ou "nao repetiu".

Com 4 ou 5 anos de cada lado, nenhuma janela tem significancia estatistica; o
veredito e sobre repetir o sinal, e a tela diz isso. E descricao do passado, nao
previsao: nao alimenta alerta, setup nem semaforo.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from scanner.cripto.analise import BENCHMARK, retornos_por_periodo

CESTA = 50
JANELA_DE_VOLUME = 90
MINIMO_DE_DIAS_DE_VOLUME = 60
MESES_MAXIMOS = 6
# As taxas do diario de trades (`regrasDoDiario` em web/src/lib/mercado.ts):
# 0,1% na Binance a vista (sem BNB) e 0,05% nos futuros, por lado.
TAXA_A_VISTA = 0.001
TAXA_FUTUROS = 0.0005
# Janela com menos anos que isto no periodo de escolha nao concorre.
MINIMO_DE_ANOS = 3

COMPRA = "compra"
VENDA = "venda"
ESCOLHA = "escolha"
CONFERENCIA = "conferencia"
FORA = "fora"
REPETIU = "repetiu"
EM_PARTE = "em parte"
NAO_REPETIU = "nao repetiu"
SEM_CONFERENCIA = "sem conferencia"

COLUNAS_DA_CESTA = ("mes", "retorno", "retorno_btc", "moedas")
COLUNAS_DOS_ANOS = ("lado", "inicio_mes", "meses", "ano", "periodo", "resultado")
_ESTATISTICAS = ("media", "mediana", "positivos", "anos", "controle")
COLUNAS_DAS_JANELAS = (
    "lado",
    "inicio_mes",
    "meses",
    "posicao",
    "veredito",
    *(f"{p}_{e}" for p in (ESCOLHA, CONFERENCIA) for e in _ESTATISTICAS),
    "todos_media",
    "todos_mediana",
    "todos_positivos",
    "todos_anos",
)


@dataclass(frozen=True)
class Estudo:
    """A cesta mes a mes, as janelas julgadas e o resultado de cada janela em cada ano."""

    cesta: pd.DataFrame
    janelas: pd.DataFrame
    anos: pd.DataFrame


def cesta_mensal(
    fech: pd.DataFrame, vol: pd.DataFrame, ultimo_dia: pd.Timestamp, n: int = CESTA
) -> pd.DataFrame:
    """O retorno mensal da cesta das `n` moedas com mais volume nos 90 dias anteriores.

    So meses ja fechados (o ultimo dia do mes ate `ultimo_dia`).
    """
    mensal = retornos_por_periodo(fech, "M")
    if mensal.empty:
        return pd.DataFrame(columns=list(COLUNAS_DA_CESTA))
    inicio = pd.to_datetime(mensal["periodo"])
    fechado = inicio + pd.offsets.MonthEnd(0) <= ultimo_dia
    mensal = mensal[fechado.to_numpy()]
    ret = mensal.pivot(index="periodo", columns="moeda", values="retorno")
    ret.index = pd.DatetimeIndex(ret.index)

    # Volume dos 90 dias que terminam na vespera do comeco de cada mes.
    soma = vol.rolling(JANELA_DE_VOLUME, min_periods=MINIMO_DE_DIAS_DE_VOLUME).sum()
    antes = soma.reindex(ret.index - pd.Timedelta(days=1)).reindex(columns=ret.columns)
    antes.index = ret.index
    # Concorre quem tem retorno no mes (a moeda que parou antes do mes sai).
    antes = antes.where(ret.notna())
    membro = antes.rank(axis=1, ascending=False, method="first") <= n
    dentro = ret.where(membro)
    moedas = dentro.notna().sum(axis=1)
    btc = ret[BENCHMARK] if BENCHMARK in ret.columns else pd.Series(np.nan, index=ret.index)
    cesta = pd.DataFrame(
        {
            "mes": ret.index.date,
            "retorno": dentro.mean(axis=1, skipna=True).to_numpy(dtype="float64"),
            "retorno_btc": btc.to_numpy(dtype="float64"),
            "moedas": moedas.to_numpy(dtype="int64"),
        }
    )
    return cesta[cesta["moedas"] > 0].reset_index(drop=True)


def resultado_por_ano(
    cesta: pd.DataFrame, periodos: tuple[tuple[int, int], tuple[int, int]]
) -> pd.DataFrame:
    """Cada janela (comeco x duracao) em cada ano, para os dois lados."""
    if cesta.empty:
        return pd.DataFrame(columns=list(COLUNAS_DOS_ANOS))
    serie = pd.Series(
        cesta["retorno"].to_numpy(dtype="float64"),
        index=pd.PeriodIndex(pd.to_datetime(cesta["mes"]), freq="M"),
    ).sort_index()
    # Calendario sem buraco: mes que faltar vira NaN e derruba as janelas que o cruzam.
    serie = serie.reindex(pd.period_range(serie.index.min(), serie.index.max(), freq="M"))
    valores = serie.to_numpy()
    fim_da_escolha = pd.Period(f"{periodos[0][1]}-12", freq="M")
    comeco_da_conferencia = pd.Period(f"{periodos[1][0]}-01", freq="M")

    partes: list[pd.DataFrame] = []
    meses = serie.index
    for k in range(1, MESES_MAXIMOS + 1):
        if len(valores) < k:
            break
        # Janelas de k meses: as linhas sao os comecos, as colunas os k meses.
        blocos = np.lib.stride_tricks.sliding_window_view(valores, k)
        completas = ~np.isnan(blocos).any(axis=1)
        # PeriodIndex explicito: fatiado com mascara, os tipos do pandas do CI
        # (versao do lockfile) perdem o tipo e recusam `.month` e `.year`.
        comeco = pd.PeriodIndex(meses[: len(blocos)][completas])
        fim = pd.PeriodIndex(meses[k - 1 :][completas])
        blocos = blocos[completas]
        compra = np.prod(1.0 + blocos, axis=1) * (1.0 - TAXA_A_VISTA) ** 2 - 1.0
        venda = np.prod(1.0 - blocos, axis=1) * (1.0 - TAXA_FUTUROS) ** 2 - 1.0
        periodo = np.where(
            fim <= fim_da_escolha,
            ESCOLHA,
            np.where(comeco >= comeco_da_conferencia, CONFERENCIA, FORA),
        )
        for lado, resultado in ((COMPRA, compra), (VENDA, venda)):
            partes.append(
                pd.DataFrame(
                    {
                        "lado": lado,
                        "inicio_mes": comeco.month.to_numpy(dtype="int64"),
                        "meses": k,
                        "ano": comeco.year.to_numpy(dtype="int64"),
                        "periodo": periodo,
                        "resultado": resultado,
                    }
                )
            )
    if not partes:
        return pd.DataFrame(columns=list(COLUNAS_DOS_ANOS))
    return pd.concat(partes, ignore_index=True)


def _estatisticas(anos: pd.DataFrame, chave: list[str]) -> pd.DataFrame:
    g = anos.groupby(chave)["resultado"]
    return pd.DataFrame(
        {
            "media": g.mean(),
            "mediana": g.median(),
            "positivos": g.apply(lambda s: int((s > 0).sum())),
            "anos": g.size(),
        }
    )


def julgar(anos: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por janela e lado: os numeros de cada periodo, a posicao e o veredito."""
    chave = ["lado", "inicio_mes", "meses"]
    base = anos.loc[:, chave].drop_duplicates().set_index(chave).sort_index()
    for periodo in (ESCOLHA, CONFERENCIA):
        trecho = anos[anos["periodo"] == periodo]
        est = _estatisticas(trecho, chave)
        # Controle: uma janela QUALQUER do mesmo tamanho e lado, no mesmo periodo.
        controle = trecho.groupby(["lado", "meses"])["resultado"].mean().rename("controle")
        est = est.join(controle, on=["lado", "meses"])
        base = base.join(est.add_prefix(f"{periodo}_"))
    todos = _estatisticas(anos, chave).add_prefix("todos_")
    base = base.join(todos).reset_index()

    for coluna in ("positivos", "anos"):
        for periodo in (ESCOLHA, CONFERENCIA):
            base[f"{periodo}_{coluna}"] = base[f"{periodo}_{coluna}"].fillna(0).astype("int64")
    base["todos_positivos"] = base["todos_positivos"].astype("int64")
    base["todos_anos"] = base["todos_anos"].astype("int64")

    excesso = base["escolha_media"] - base["escolha_controle"]
    concorre = base["escolha_anos"] >= MINIMO_DE_ANOS
    base["posicao"] = (
        excesso.where(concorre).groupby(base["lado"]).rank(ascending=False, method="first")
    ).astype("Int64")

    lucro = base["conferencia_media"] > 0
    bateu = base["conferencia_media"] > base["conferencia_controle"]
    veredito = np.where(lucro & bateu, REPETIU, np.where(lucro | bateu, EM_PARTE, NAO_REPETIU))
    base["veredito"] = np.where(base["conferencia_anos"] == 0, SEM_CONFERENCIA, veredito)
    return base.loc[:, list(COLUNAS_DAS_JANELAS)].sort_values(
        ["lado", "posicao", "inicio_mes", "meses"]
    )


def calcular(
    fech: pd.DataFrame,
    vol: pd.DataFrame,
    periodos: tuple[tuple[int, int], tuple[int, int]],
    n: int = CESTA,
) -> Estudo:
    """O estudo inteiro a partir dos fechamentos e volumes diarios (as moedas que entram)."""
    ultimo = pd.Timestamp(fech.index.max())
    cesta = cesta_mensal(fech.astype("float64"), vol.astype("float64"), ultimo, n)
    anos = resultado_por_ano(cesta, periodos)
    janelas = julgar(anos) if not anos.empty else pd.DataFrame(columns=list(COLUNAS_DAS_JANELAS))
    return Estudo(cesta=cesta, janelas=janelas.reset_index(drop=True), anos=anos)


MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def rotulo(inicio_mes: int, meses: int) -> str:
    """ "abr" para um mes so; "mai a out" para seis a partir de maio."""
    fim = (inicio_mes - 1 + meses - 1) % 12
    return MESES[inicio_mes - 1] if meses == 1 else f"{MESES[inicio_mes - 1]} a {MESES[fim]}"


def escolhidas(janelas: pd.DataFrame) -> list[str]:
    """Uma linha por lado com a janela escolhida e o veredito, para o log."""
    linhas: list[str] = []
    for lado in (COMPRA, VENDA):
        primeira = janelas[(janelas["lado"] == lado) & (janelas["posicao"] == 1)]
        if primeira.empty:
            linhas.append(f"{lado}: nenhuma janela com anos suficientes na escolha")
            continue
        j = primeira.iloc[0]
        linhas.append(
            f"{lado}: {rotulo(int(j['inicio_mes']), int(j['meses']))} -- {j['veredito']} "
            f"(escolha {j['escolha_media']:+.1%}, conferencia {j['conferencia_media']:+.1%} "
            f"contra {j['conferencia_controle']:+.1%} de uma janela qualquer)"
        )
    return linhas
