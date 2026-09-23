"""Alertas de rompimento de preco.

Isto NAO e deteccao: e o usuario dizendo "me avise quando este papel chegar
aqui". O scanner detecta volume anomalo e apresenta; o rompimento e a leitura
manual daquele evento virando um gatilho. Nenhum nivel e sugerido, calculado ou
recomendado pelo sistema -- ele so vigia o que foi pedido.

O nome evita confusao com `alerts.py`, que cuida do alerta de 6 sigma. Sao
coisas diferentes: aquele nasce da estatistica, este nasce de um clique.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Engine

from scanner.calendar import hoje_na_b3
from scanner.cotacoes.base import Cota, Cotacao, ProvedorDeCotacoes

Direcao = Literal["acima", "abaixo"]
DIRECOES: tuple[Direcao, ...] = ("acima", "abaixo")


@dataclass(frozen=True)
class Alerta:
    """Um alerta como o resto do sistema o enxerga, sem ORM vazando."""

    id: int
    ticker: str
    trade_date: date
    preco: Decimal
    direcao: Direcao
    criado_em: datetime
    disparado_em: datetime | None = None
    preco_disparo: Decimal | None = None
    fonte_disparo: str | None = None

    @property
    def ativo(self) -> bool:
        return self.disparado_em is None


@dataclass(frozen=True)
class Disparo:
    """Um alerta que rompeu, com a cotacao que causou isso."""

    alerta: Alerta
    cotacao: Cotacao


@dataclass(frozen=True)
class RelatorioDeChecagem:
    """O que a passada de checagem fez."""

    ativos: int
    consultados: int
    sem_cotacao: int
    disparados: int
    # Cotacoes que chegaram mas nao sao do pregao de hoje, e por isso nao valem.
    velhas: int = 0
    # De qual fornecedor veio cada cotacao usada, ex.: {"yahoo": 3, "brapi": 1}.
    # E o que deixa visivel um fornecedor que parou de responder: sem isto, a
    # brapi recusou todas as checagens por dias e o log so dizia "0 dispararam".
    fontes: tuple[tuple[str, int], ...] = ()
    # Quanto sobrou do plano de cada fornecedor que diz, ex.: (("brapi", Cota),).
    # O `fontes` acima mostra quem parou de responder; este mostra quem esta
    # PRESTES a parar. Sao 36 passadas por pregao contra 15 mil requisicoes por
    # mes no plano gratuito da brapi: a conta fica apertada sem ninguem avisar,
    # e a brapi manda o numero em toda resposta.
    cotas: tuple[tuple[str, Cota], ...] = ()

    def summary(self) -> str:
        """Uma linha para log e CLI."""
        faltou = f", {self.sem_cotacao} sem cotacao" if self.sem_cotacao else ""
        velhas = f", {self.velhas} de outro dia ignoradas" if self.velhas else ""
        fontes = (
            " (" + ", ".join(f"{nome} {n}" for nome, n in self.fontes) + ")" if self.fontes else ""
        )
        cotas = (
            "; cota " + ", ".join(f"{nome} {c.resumo()}" for nome, c in self.cotas)
            if self.cotas
            else ""
        )
        return (
            f"{self.ativos} alertas ativos, {self.consultados} papeis consultados{fontes}"
            f"{faltou}{velhas}, {self.disparados} dispararam{cotas}"
        )


def rompeu(alerta: Alerta, cotacao: Cotacao) -> bool:
    """Se a cotacao alcancou o nivel pedido.

    Comparacao simples e inclusiva: tocar o nivel conta. A escolha e do usuario
    -- "tocou o nivel, a qualquer momento", e nao "fechou alem dele". Com
    checagem de 15 em 15 minutos isso significa que um pavio pode disparar; e
    por isso que o disparo grava o preco que o causou.
    """
    if alerta.direcao == "acima":
        return cotacao.preco >= alerta.preco
    return cotacao.preco <= alerta.preco


def cotacoes_de_hoje(cotacoes: dict[str, Cotacao], hoje: date) -> dict[str, Cotacao]:
    """So as cotacoes do pregao de hoje, no fuso da B3.

    Antes da abertura, num feriado ou quando o fornecedor trava, a "ultima
    cotacao" e o fechamento de um dia anterior. Esse preco pode estar alem do
    nivel sem que o papel tenha ido la hoje -- e o alerta dispararia por um
    movimento que ja aconteceu. Cotacao de outro dia nao dispara nem cancela: o
    alerta segue ativo para a proxima passada.

    Nao ha corte por idade dentro do dia. Um preco de 30 minutos atras que tocou
    o nivel e um toque que de fato aconteceu hoje; a hora vai na mensagem para
    quem le saber de quando e.
    """
    return {t: c for t, c in cotacoes.items() if hoje_na_b3(c.hora) == hoje}


def selecionar_disparos(alertas: list[Alerta], cotacoes: dict[str, Cotacao]) -> list[Disparo]:
    """Quais alertas romperam, dadas as cotacoes desta passada.

    Papel sem cotacao simplesmente nao e avaliado: a ausencia de dado nunca
    vira disparo, nem cancela o alerta. Ele continua ativo para a proxima.
    """
    return [
        Disparo(alerta, cotacoes[alerta.ticker])
        for alerta in alertas
        if alerta.ativo and alerta.ticker in cotacoes and rompeu(alerta, cotacoes[alerta.ticker])
    ]


def payload_do_disparo(disparo: Disparo) -> dict[str, Any]:
    """O que a mensagem do Telegram precisa saber."""
    return {
        "ticker": disparo.alerta.ticker,
        "direcao": disparo.alerta.direcao,
        "nivel": float(disparo.alerta.preco),
        "preco": float(disparo.cotacao.preco),
        "fonte": disparo.cotacao.fonte,
        "hora": disparo.cotacao.hora,
        "criado_em": disparo.alerta.criado_em,
        "trade_date": disparo.alerta.trade_date,
    }


def checar_rompimentos(
    engine: Engine,
    provedor: ProvedorDeCotacoes,
    *,
    notifier: Any = None,
    dry_run: bool = False,
    hoje: date | None = None,
) -> RelatorioDeChecagem:
    """Uma passada: le os ativos, consulta o preco, avisa e desativa.

    A ordem importa. O alerta so e marcado como disparado DEPOIS de a mensagem
    sair -- se o Telegram recusar, ele continua ativo e tenta de novo daqui a
    15 minutos. O contrario perderia o aviso em silencio, que e exatamente o
    que este sistema existe para nao fazer.

    `hoje` existe para os testes fixarem o dia; em producao e o dia em Sao Paulo.
    """
    from scanner.storage.repository import alertas_ativos, marcar_disparado

    alertas = alertas_ativos(engine)
    if not alertas:
        return RelatorioDeChecagem(0, 0, 0, 0)

    tickers = sorted({a.ticker for a in alertas})
    recebidas = provedor.cotacoes(tickers)
    cotacoes = cotacoes_de_hoje(recebidas, hoje if hoje is not None else hoje_na_b3())
    disparos = selecionar_disparos(alertas, cotacoes)

    enviados = 0
    for disparo in disparos:
        if notifier is not None and not notifier.send_rompimento(payload_do_disparo(disparo)):
            continue
        if not dry_run:
            marcar_disparado(
                engine,
                disparo.alerta.id,
                preco=disparo.cotacao.preco,
                fonte=disparo.cotacao.fonte,
            )
        enviados += 1

    return RelatorioDeChecagem(
        ativos=len(alertas),
        consultados=len(tickers),
        sem_cotacao=len([t for t in tickers if t not in recebidas]),
        disparados=enviados,
        velhas=len(recebidas) - len(cotacoes),
        fontes=tuple(sorted(Counter(c.fonte for c in cotacoes.values()).items())),
        # Lido DEPOIS da consulta: e a cota que sobrou por causa desta passada.
        # `getattr` e nao atributo direto porque `ProvedorDeCotacoes` e um
        # Protocol e nem todo fornecedor tem plano -- o Yahoo nao tem.
        cotas=tuple(getattr(provedor, "cotas", ())),
    )
