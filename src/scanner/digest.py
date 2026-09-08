"""Resumo diario do pregao.

Mostra os papeis que mais fugiram do proprio volume normal, tenham cruzado o
limiar ou nao. Ordena pelo mesmo `z_log` da regra da secao 4 -- a diferenca e
so a ausencia do corte.

Isto NAO e um ranking de merito. Nao ha score de confianca, nem classificacao
de padrao, nem previsao: e a mesma metrica do alerta, ordenada, para os dias em
que nada cruza 6 sigma nao virarem silencio. A leitura continua sendo do
usuario.

O piso de volume do `config.yaml` vale aqui tambem: papel morto nao interessa
no resumo pela mesma razao que nao interessa no alerta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import Engine

from scanner.config import ScannerConfig
from scanner.recompute import Contexto, carregar_contexto

RESUMO_COLUMNS = (
    "ticker",
    "z_log",
    "close",
    "volume_financial",
    "ret_day",
    "notificado",
)


@dataclass(frozen=True)
class Resumo:
    """O que o resumo de um pregao carrega."""

    trade_date: date
    linhas: pd.DataFrame
    avaliados: int
    cruzaram: int
    limiar: float
    mkt_vol_z: float | None

    @property
    def vazio(self) -> bool:
        return self.linhas.empty


def montar_resumo(
    metrics: pd.DataFrame,
    bars: pd.DataFrame,
    features: pd.DataFrame,
    config: ScannerConfig,
    trade_date: date,
) -> Resumo:
    """Os `digest.top_n` papeis com maior z_log no pregao.

    `notificado` marca quais tambem cruzaram o limiar do alerta -- para o
    resumo nao parecer que esta anunciando novidade sobre algo que ja chegou
    como alerta.
    """
    dia = pd.Timestamp(trade_date)
    janela = config.digest.window

    escopo = metrics[
        (metrics["trade_date"] == dia)
        & (metrics["window_size"] == janela)
        & metrics["z_log"].notna()
    ]
    if escopo.empty:
        return Resumo(
            trade_date,
            pd.DataFrame(columns=list(RESUMO_COLUMNS)),
            0,
            0,
            config.alert.threshold,
            None,
        )

    barras = bars.loc[:, ["ticker", "trade_date", "close", "volume_financial"]].copy()
    barras["trade_date"] = pd.to_datetime(barras["trade_date"])
    juntos = escopo.merge(barras, on=["ticker", "trade_date"], how="left")

    # Mesmo piso do alerta: papel morto nao entra.
    juntos = juntos[juntos["volume_financial"] >= config.alert.min_volume_brl]
    if juntos.empty:
        return Resumo(
            trade_date,
            pd.DataFrame(columns=list(RESUMO_COLUMNS)),
            0,
            0,
            config.alert.threshold,
            None,
        )

    contexto = features.copy()
    contexto["trade_date"] = pd.to_datetime(contexto["trade_date"])
    colunas = [c for c in ("ticker", "trade_date", "ret_day", "mkt_vol_z") if c in contexto.columns]
    juntos = juntos.merge(contexto.loc[:, colunas], on=["ticker", "trade_date"], how="left")

    juntos["notificado"] = juntos["z_log"] >= config.alert.threshold
    top = juntos.nlargest(config.digest.top_n, "z_log")

    mkt = None
    if "mkt_vol_z" in juntos.columns:
        valores = juntos["mkt_vol_z"].dropna()
        if not valores.empty:
            mkt = float(valores.iloc[0])

    faltando = [c for c in RESUMO_COLUMNS if c not in top.columns]
    for coluna in faltando:
        top[coluna] = None

    return Resumo(
        trade_date=trade_date,
        linhas=top.loc[:, list(RESUMO_COLUMNS)].reset_index(drop=True),
        avaliados=int(juntos["ticker"].nunique()),
        cruzaram=int(juntos["notificado"].sum()),
        limiar=config.alert.threshold,
        mkt_vol_z=mkt,
    )


def payload_do_resumo(resumo: Resumo) -> dict[str, Any]:
    """Converte o resumo no formato que a mensagem espera.

    Os nomes das chaves sao os do dia a dia, nao os das colunas do banco: quem
    le a mensagem nao precisa saber o que e `z_log` nem `volume_financial`.
    """

    def valor(bruto: Any) -> float | None:
        """Campo do DataFrame para float, com NaN virando None para a mensagem."""
        convertido = pd.to_numeric(bruto, errors="coerce")
        return None if pd.isna(convertido) else float(convertido)

    linhas: list[dict[str, Any]] = [
        {
            "ticker": str(linha["ticker"]),
            "desvios": valor(linha["z_log"]),
            "preco": valor(linha["close"]),
            "variacao": valor(linha["ret_day"]),
            "volume": valor(linha["volume_financial"]),
        }
        for _, linha in resumo.linhas.iterrows()
    ]
    return {"trade_date": resumo.trade_date, "linhas": linhas}


def run_resumo(
    engine: Engine,
    config: ScannerConfig,
    trade_date: date,
    *,
    notifier: Any = None,
    bars: pd.DataFrame | None = None,
    contexto: Contexto | None = None,
) -> Resumo:
    """Monta o resumo do pregao e envia.

    `bars` permite passar as barras prontas em vez de reler o banco; os testes
    usam. `contexto` vai um passo alem: o calculo ja veio pronto de fora, como
    no `scanner daily`.
    """
    ctx = carregar_contexto(engine, config, bars=bars) if contexto is None else contexto
    if ctx.vazio:
        return Resumo(
            trade_date,
            pd.DataFrame(columns=list(RESUMO_COLUMNS)),
            0,
            0,
            config.alert.threshold,
            None,
        )

    resumo = montar_resumo(ctx.metrics, ctx.bars, ctx.features, config, trade_date)

    if notifier is not None and not resumo.vazio:
        notifier.send_resumo(payload_do_resumo(resumo))
    return resumo
