"""Varios fornecedores, uma cotacao por papel: a de hora mais nova."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from scanner.cotacoes.base import Cota, Cotacao, ProvedorDeCotacoes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProvedorMaisRecente:
    """Fica, por papel, com a cotacao mais nova de quem tem hora confiavel.

    Duas passadas, e a ordem nao e capricho:

    1. Os fornecedores cujo `hora` e a hora do negocio disputam entre si por
       hora mais nova. Comparar horas so significa alguma coisa entre relogios
       que medem a mesma coisa.
    2. Os de hora nao confiavel sao consultados DEPOIS, e so para os papeis que
       ninguem da primeira passada soube responder. Eles nao disputam: entram
       para preencher ausencia, que e o que ainda sabem fazer bem.

    Isto substitui a versao que perguntava a todos e comparava as horas de
    todos. Aquilo pressupunha que a hora era honesta em toda parte, e em
    23/09/2026 ficou provado que nao e: a brapi carimba o relogio da resposta,
    nao o do negocio (a medicao esta em `ProvedorDeCotacoes.hora_e_do_negocio`).
    Com isso ela ganhava TODA disputa, inclusive servindo o pregao fechado da
    vespera -- e um alerta de rompimento podia disparar com o preco de ontem,
    porque `cotacoes_de_hoje` decide pela hora.

    Empate na primeira passada fica com o fornecedor que vem antes na tupla.

    A falha de um fornecedor nunca derruba os outros. Se todos falharem,
    devolve o que tiver, possivelmente nada -- quem chama trata a ausencia.
    """

    provedores: tuple[ProvedorDeCotacoes, ...] = field(default_factory=tuple)

    @property
    def nome(self) -> str:
        return "+".join(p.nome for p in self.provedores)

    @property
    def cotas(self) -> tuple[tuple[str, Cota], ...]:
        """A cota de cada fornecedor que reporta uma, por nome.

        Nao entra no Protocol: o Yahoo nao tem plano nem cota, e exigir o
        atributo de todo mundo obrigaria um fornecedor sem contrato a fingir que
        tem um. Quem reporta, reporta; quem nao reporta, some da lista.
        """
        encontradas = []
        for provedor in self.provedores:
            cota = getattr(provedor, "cota", None)
            if isinstance(cota, Cota) and not cota.vazia:
                encontradas.append((provedor.nome, cota))
        return tuple(encontradas)

    def _perguntar(
        self, provedor: ProvedorDeCotacoes, tickers: Sequence[str]
    ) -> dict[str, Cotacao]:
        """Uma consulta, com a falha contida no fornecedor que a causou."""
        if not tickers:
            return {}
        try:
            return provedor.cotacoes(tickers)
        # Rede de seguranca ampla de proposito: mesmo que um adaptador deixe
        # escapar algo inesperado, a falha de UM fornecedor nao pode impedir os
        # seguintes -- silencio por bug de parser seria indistinguivel de
        # "nada rompeu".
        except Exception:
            logger.exception("[cotacoes] provedor %s falhou", provedor.nome)
            return {}

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        escolhidas: dict[str, Cotacao] = {}

        # 1a passada: quem mede a hora do negocio disputa por hora mais nova.
        for provedor in self.provedores:
            if not provedor.hora_e_do_negocio:
                continue
            for ticker, cotacao in self._perguntar(provedor, tickers).items():
                atual = escolhidas.get(ticker)
                if atual is None or cotacao.hora > atual.hora:
                    escolhidas[ticker] = cotacao

        # 2a passada: os de hora nao confiavel, so para o que ficou sem resposta.
        # Pedir menos papeis tambem gasta menos cota, mas o motivo de estarem
        # aqui e a hora, nao o preco da requisicao.
        for provedor in self.provedores:
            if provedor.hora_e_do_negocio:
                continue
            faltando = [t for t in tickers if t not in escolhidas]
            if not faltando:
                break
            reserva = self._perguntar(provedor, faltando)
            if reserva:
                logger.info(
                    "[cotacoes] %s respondeu por %s (reserva: hora nao confiavel)",
                    provedor.nome,
                    sorted(reserva),
                )
            escolhidas.update(reserva)

        faltaram = [t for t in tickers if t not in escolhidas]
        if faltaram:
            logger.info("[cotacoes] sem cotacao para: %s", faltaram)
        return escolhidas
