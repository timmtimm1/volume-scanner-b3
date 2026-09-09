"""Alertas de rompimento de preco.

Isto NAO e deteccao: e o usuario dizendo "me avise quando este papel chegar
aqui". O scanner detecta volume anomalo e apresenta; o rompimento e a leitura
manual daquele evento virando um gatilho. Nenhum nivel e sugerido, calculado ou
recomendado pelo sistema -- ele so vigia o que foi pedido.

O nome evita confusao com `alerts.py`, que cuida do alerta de 6 sigma. Sao
coisas diferentes: aquele nasce da estatistica, este nasce de um clique.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Engine

from scanner.cotacoes.base import Cotacao, ProvedorDeCotacoes

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

    def summary(self) -> str:
        """Uma linha para log e CLI."""
        faltou = f", {self.sem_cotacao} sem cotacao" if self.sem_cotacao else ""
        return (
            f"{self.ativos} alertas ativos, {self.consultados} papeis consultados"
            f"{faltou}, {self.disparados} dispararam"
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
        "criado_em": disparo.alerta.criado_em,
        "trade_date": disparo.alerta.trade_date,
    }


def checar_rompimentos(
    engine: Engine,
    provedor: ProvedorDeCotacoes,
    *,
    notifier: Any = None,
    dry_run: bool = False,
) -> RelatorioDeChecagem:
    """Uma passada: le os ativos, consulta o preco, avisa e desativa.

    A ordem importa. O alerta so e marcado como disparado DEPOIS de a mensagem
    sair -- se o Telegram recusar, ele continua ativo e tenta de novo daqui a
    15 minutos. O contrario perderia o aviso em silencio, que e exatamente o
    que este sistema existe para nao fazer.
    """
    from scanner.storage.repository import alertas_ativos, marcar_disparado

    alertas = alertas_ativos(engine)
    if not alertas:
        return RelatorioDeChecagem(0, 0, 0, 0)

    tickers = sorted({a.ticker for a in alertas})
    cotacoes = provedor.cotacoes(tickers)
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
        sem_cotacao=len([t for t in tickers if t not in cotacoes]),
        disparados=enviados,
    )
