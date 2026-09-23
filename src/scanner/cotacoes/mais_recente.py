"""Varios fornecedores, uma cotacao por papel: a de hora mais nova."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from scanner.cotacoes.base import Cota, Cotacao, ProvedorDeCotacoes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProvedorMaisRecente:
    """Pergunta a todos os fornecedores e fica, por papel, com a cotacao mais nova.

    Substitui o encadeamento que pedia ao segundo so o que o primeiro nao
    respondeu. Aquilo resolvia falta de dado, mas nao atraso: com a brapi na
    frente, uma resposta de 30 minutos atras ganhava de uma de 15 so por ter
    chegado primeiro na fila. Alerta de preco precisa do preco mais atual que
    se consegue, e a unica forma de saber qual e comparar as horas.

    Empate fica com o fornecedor que vem antes na tupla: e a ordem de
    preferencia, e a brapi, que tem contrato, vai na frente.

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

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        escolhidas: dict[str, Cotacao] = {}
        for provedor in self.provedores:
            try:
                novas = provedor.cotacoes(tickers)
            # Rede de seguranca ampla de proposito: mesmo que um adaptador deixe
            # escapar algo inesperado, a falha de UM fornecedor nao pode impedir
            # os seguintes -- silencio por bug de parser seria indistinguivel de
            # "nada rompeu".
            except Exception:
                logger.exception("[cotacoes] provedor %s falhou", provedor.nome)
                continue
            for ticker, cotacao in novas.items():
                atual = escolhidas.get(ticker)
                if atual is None or cotacao.hora > atual.hora:
                    escolhidas[ticker] = cotacao

        faltaram = [t for t in tickers if t not in escolhidas]
        if faltaram:
            logger.info("[cotacoes] sem cotacao para: %s", faltaram)
        return escolhidas
