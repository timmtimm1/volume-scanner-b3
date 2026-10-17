"""Variacao semanal das acoes, ajustada por proventos e eventos em acoes.

O COTAHIST traz o preco NOMINAL do pregao: o fechamento de um papel que
desdobrou na semana nao e comparavel ao da semana anterior, e um que pagou
dividendo cai o valor do dividendo no dia ex sem ter perdido nada. A variacao
bruta (`preco_fim / preco_inicio`) mentiria nos dois casos. Aqui a variacao e a
de uma carteira de UMA acao comprada no `preco_inicio`: desdobramento e
bonificacao multiplicam as acoes, o provento em dinheiro vai para o caixa
(sem reinvestir), e o retorno e (acoes x preco_fim + caixa) / preco_inicio - 1.

Quando o evento nao tem razao por acao (cisao), nao ha ajuste honesto: o papel
sai do ranking e aparece em `fora`, com a variacao bruta a vista.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import numpy as np
import pandas as pd
from sqlalchemy import Engine

from scanner.calendar import sessions_before
from scanner.fundamentos.b3 import B3IndisponivelError, suplemento
from scanner.semana.periodo import Semana
from scanner.storage import repository

logger = logging.getLogger(__name__)

# Quantos pregoes para tras vale procurar o preco-base. Papel que nao negocia
# ha mais de 5 pregoes antes da semana tem preco velho demais para medir variacao.
PREGOES_DE_BASE = 5

# Os eventos que, no proprio papel, se ajustam pelo fator da B3.
TIPOS_COM_FATOR = ("DESDOBRAMENTO", "GRUPAMENTO", "BONIFICACAO")

COLUNAS_SAIDA = (
    "ticker",
    "data_inicio",
    "preco_inicio",
    "data_fim",
    "preco_fim",
    "variacao_bruta",
    "variacao",
    "proventos_por_acao",
    "multiplicador",
    "ajustado",
    "comparavel",
    "conferido",
    "eventos_sem_ajuste",
)


def _vazio() -> pd.DataFrame:
    return pd.DataFrame({coluna: pd.Series(dtype="object") for coluna in COLUNAS_SAIDA})


def _ultimo_preco(
    barras: pd.DataFrame, desde: pd.Timestamp, ate: pd.Timestamp, prefixo: str
) -> pd.DataFrame:
    """Ultimo fechamento de cada ticker em [desde, ate]: ticker, data_*, preco_*."""
    janela = barras[(barras["data"] >= desde) & (barras["data"] <= ate)]
    ultimo = janela.sort_values(["ticker", "data"]).groupby("ticker", as_index=False).tail(1)
    return ultimo.rename(columns={"data": f"data_{prefixo}", "close": f"preco_{prefixo}"})[
        ["ticker", f"data_{prefixo}", f"preco_{prefixo}"]
    ]


def _juntar_tipos(tipos: pd.Series) -> str | None:
    """Os tipos distintos de um papel, em ordem, num texto so ("CIS RED CAP")."""
    distintos = sorted({str(t) for t in tipos.dropna()})
    return ", ".join(distintos) if distintos else None


def _acoes_do_ajuste(
    proventos: pd.DataFrame, eventos: pd.DataFrame, inicio: pd.Timestamp, fim: pd.Timestamp
) -> pd.DataFrame:
    """Proventos e eventos na janela [inicio, fim), numa tabela so, em ordem de aplicacao.

    Colunas: ticker, data_com, ordem (0 provento, 1 evento), valor, mult, sem_razao,
    tipo_sem_razao. `mult` e o multiplicador de acoes (1 no provento; 1 tambem
    no evento sem razao, que so marca o papel como nao comparavel).
    """
    pedacos: list[pd.DataFrame] = []
    if not proventos.empty:
        p = proventos[["ticker", "data_com", "valor"]].copy()
        p["data_com"] = pd.to_datetime(p["data_com"])
        p["ordem"] = 0
        p["mult"] = 1.0
        p["sem_razao"] = False
        p["tipo_sem_razao"] = None
        pedacos.append(p)
    if not eventos.empty:
        e = eventos[["ticker", "data_com", "tipo", "multiplicador"]].copy()
        e["data_com"] = pd.to_datetime(e["data_com"])
        e["multiplicador"] = e["multiplicador"].astype(float)
        e["sem_razao"] = e["multiplicador"].isna()
        e["tipo_sem_razao"] = e["tipo"].where(e["sem_razao"])
        e["mult"] = e["multiplicador"].fillna(1.0)
        e["valor"] = 0.0
        e["ordem"] = 1
        pedacos.append(e.drop(columns=["multiplicador", "tipo"]))
    if not pedacos:
        return pd.DataFrame(
            {
                "ticker": pd.Series(dtype="object"),
                "data_com": pd.Series(dtype="datetime64[ns]"),
                "ordem": pd.Series(dtype="int64"),
                "valor": pd.Series(dtype="float64"),
                "mult": pd.Series(dtype="float64"),
                "sem_razao": pd.Series(dtype="bool"),
                "tipo_sem_razao": pd.Series(dtype="object"),
            }
        )
    tudo = pd.concat(pedacos, ignore_index=True)
    # Data com no pregao-base: a data ex cai dentro da semana. Data com no
    # ultimo pregao: a data ex e na semana seguinte, o preco_fim ainda e "com".
    tudo = tudo[(tudo["data_com"] >= inicio) & (tudo["data_com"] < fim)]
    return tudo.sort_values(["ticker", "data_com", "ordem"], kind="stable").reset_index(drop=True)


def variacoes_da_semana(
    barras: pd.DataFrame,
    universo: Sequence[str],
    semana: Semana,
    proventos: pd.DataFrame,
    eventos: pd.DataFrame,
    conferidos: Collection[str],
) -> pd.DataFrame:
    """Variacao de cada papel do universo na semana, ajustada por proventos e eventos.

    `barras`: ticker, trade_date, close. `proventos`: ticker, data_com, valor
    (R$ por acao). `eventos`: ticker, data_com, tipo, multiplicador (NaN = nao
    se ajusta por fator). `conferidos`: tickers cujo suplemento da B3 foi lido
    com sucesso -- sem isso, "nao houve evento" e "nao sei se houve" ficariam
    iguais na tela.
    """
    if barras.empty or not len(universo):
        return _vazio()

    b = barras[barras["ticker"].isin(list(universo))][["ticker", "trade_date", "close"]].copy()
    b["data"] = pd.to_datetime(b["trade_date"])
    b["close"] = b["close"].astype(float)

    base = sessions_before(semana.inicio, PREGOES_DE_BASE, inclusive=True)
    ini = _ultimo_preco(b, pd.Timestamp(base[0]), pd.Timestamp(semana.inicio), "inicio")
    fim = _ultimo_preco(b, pd.Timestamp(semana.pregoes[0]), pd.Timestamp(semana.fim), "fim")
    df = ini.merge(fim, on="ticker", how="inner")
    if df.empty:
        return _vazio()

    ajuste = _acoes_do_ajuste(
        proventos, eventos, pd.Timestamp(semana.inicio), pd.Timestamp(semana.fim)
    )
    ajuste = ajuste[ajuste["ticker"].isin(df["ticker"])]
    if ajuste.empty:
        por_ticker = pd.DataFrame(
            {
                "ticker": pd.Series(dtype="object"),
                "proventos_por_acao": pd.Series(dtype="float64"),
                "multiplicador": pd.Series(dtype="float64"),
                "sem_razao": pd.Series(dtype="bool"),
                "eventos_sem_ajuste": pd.Series(dtype="object"),
            }
        )
    else:
        # Acoes que o investidor tinha ANTES de cada linha: o produto acumulado
        # dos multiplicadores anteriores. O provento incide sobre essas acoes, e
        # no mesmo dia vem antes do evento (ordem 0 < 1): a data com vale para
        # as acoes de antes do desdobramento.
        acumulado = ajuste.groupby("ticker")["mult"].cumprod()
        antes = acumulado.groupby(ajuste["ticker"]).shift(1).fillna(1.0)
        ajuste = ajuste.assign(caixa=antes * ajuste["valor"], acumulado=acumulado)
        por_ticker = ajuste.groupby("ticker", as_index=False).agg(
            proventos_por_acao=("caixa", "sum"),
            multiplicador=("acumulado", "last"),
            sem_razao=("sem_razao", "any"),
            # O motivo de ficar fora do ranking, para a tela dizer qual foi o evento.
            eventos_sem_ajuste=("tipo_sem_razao", _juntar_tipos),
        )

    df = df.merge(por_ticker, on="ticker", how="left")
    df["eventos_sem_ajuste"] = (
        df["eventos_sem_ajuste"].astype(object).where(df["eventos_sem_ajuste"].notna(), None)
    )
    df["ajustado"] = df["multiplicador"].notna()
    df["proventos_por_acao"] = df["proventos_por_acao"].fillna(0.0)
    df["multiplicador"] = df["multiplicador"].fillna(1.0)
    df["comparavel"] = ~df["sem_razao"].fillna(False).astype(bool)
    df["variacao_bruta"] = df["preco_fim"] / df["preco_inicio"] - 1
    df["variacao"] = (df["multiplicador"] * df["preco_fim"] + df["proventos_por_acao"]) / df[
        "preco_inicio"
    ] - 1
    df["conferido"] = df["ticker"].isin(set(conferidos))

    df["data_inicio"] = df["data_inicio"].dt.date
    df["data_fim"] = df["data_fim"].dt.date
    return df[list(COLUNAS_SAIDA)].sort_values("ticker").reset_index(drop=True)


def ranking(variacoes: pd.DataFrame, n: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(altas, quedas, fora): as `n` maiores e menores variacoes entre os comparaveis.

    Empate desempata por ticker, para o resultado nao depender da ordem de entrada.
    `fora` sao os papeis que nao se comparam (cisao), todos, por ticker.
    """
    if variacoes.empty:
        return variacoes, variacoes, variacoes
    comparaveis = variacoes[variacoes["comparavel"]]
    altas = comparaveis.sort_values(["variacao", "ticker"], ascending=[False, True]).head(n)
    quedas = comparaveis.sort_values(["variacao", "ticker"], ascending=[True, True]).head(n)
    fora = variacoes[~variacoes["comparavel"]].sort_values("ticker")
    return (
        altas.reset_index(drop=True),
        quedas.reset_index(drop=True),
        fora.reset_index(drop=True),
    )


@dataclass(frozen=True)
class EventosDaSemana:
    """O que a B3 disse sobre proventos e eventos em acoes, por ticker."""

    proventos: pd.DataFrame
    eventos: pd.DataFrame
    conferidos: frozenset[str]
    falhas: tuple[str, ...]  # emissores que a B3 nao respondeu


def buscar_eventos_da_semana(
    engine: Engine,
    tickers: Sequence[str],
    semana: Semana,
    cliente: Any,
    *,
    pausa: float = 0.0,
) -> EventosDaSemana:
    """Consulta o suplemento da B3 de cada emissor e casa os itens ao ticker pelo ISIN.

    A ligacao ticker -> emissor vem de `empresa_tickers`, nunca do prefixo do
    ticker (EMBR e a EMBRAST, nao a Embraer). Uma chamada por emissor distinto;
    o que falha vai para `falhas` e seus tickers ficam fora de `conferidos`.
    Os itens sao recortados a janela de ajuste [inicio, fim) ja aqui.
    """
    papeis = pd.DataFrame(
        repository.papeis_com_emissor(engine, tickers),
        columns=["ticker", "isin", "emissor_b3"],
    )
    linhas_prov: list[dict[str, Any]] = []
    linhas_ev: list[dict[str, Any]] = []
    falhas: list[str] = []
    ok: set[str] = set()

    # Loop sobre emissores, nao sobre tickers: e I/O HTTP, uma chamada cada.
    for emissor in sorted(papeis["emissor_b3"].unique()):
        try:
            sup = suplemento(cliente, str(emissor))
        except (B3IndisponivelError, httpx.HTTPError) as exc:
            logger.warning("[semana] B3 nao respondeu para %s: %s", emissor, exc)
            falhas.append(str(emissor))
            continue
        ok.add(str(emissor))
        linhas_prov += [
            {"isin": p.isin, "data_com": p.data_com, "valor": float(p.valor), "tipo": p.tipo}
            for p in sup.proventos
        ]
        linhas_ev += [
            {
                "isin": e.isin,
                "data_com": e.data_com,
                # "BONIFICACAO" sozinho, fora do ranking, parece engano: o motivo
                # e ter sido paga em outro papel.
                "tipo": f"{e.tipo} EM OUTRO PAPEL"
                if e.em_outro_papel and e.tipo in TIPOS_COM_FATOR
                else e.tipo,
                "fator": float(e.fator),
                "multiplicador": np.nan if e.multiplicador is None else float(e.multiplicador),
            }
            for e in sup.eventos_em_acoes
        ]
        if pausa:
            time.sleep(pausa)

    def casar(
        linhas: list[dict[str, Any]], colunas: list[str], *, unicos: bool = False
    ) -> pd.DataFrame:
        vazio = pd.DataFrame({c: pd.Series(dtype="object") for c in ["ticker", *colunas]})
        if not linhas:
            return vazio
        f = pd.DataFrame(linhas)
        f = f[(f["data_com"] >= semana.inicio) & (f["data_com"] < semana.fim)]
        if unicos:
            # A cisao lista um item por papel emitido, todos com o mesmo ISIN de
            # quem sofre o evento (ITUB em 17/10/2026: 2 itens por ISIN). Evento
            # repetido nao pode multiplicar as acoes duas vezes. Provento NAO
            # passa por aqui: parcela repetida e pagamento de verdade.
            f = f.drop_duplicates(subset=["isin", "data_com", *colunas])
        casado = f.merge(papeis[["ticker", "isin"]], on="isin", how="inner")
        return casado[["ticker", *colunas]] if not casado.empty else vazio

    proventos = casar(linhas_prov, ["data_com", "valor", "tipo"])
    eventos = casar(linhas_ev, ["data_com", "tipo", "multiplicador"], unicos=True)
    conferidos = frozenset(papeis.loc[papeis["emissor_b3"].isin(ok), "ticker"])
    return EventosDaSemana(proventos, eventos, conferidos, tuple(falhas))
