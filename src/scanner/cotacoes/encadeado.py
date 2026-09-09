"""Encadeamento de fornecedores com degradacao gradual."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from scanner.cotacoes.base import Cotacao, ProvedorDeCotacoes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProvedorEncadeado:
    """Tenta os fornecedores em ordem, pedindo ao seguinte so o que faltou.

    Nao e "se o primeiro falhar, use o segundo": e "o segundo completa as
    lacunas do primeiro". A diferenca importa -- a brapi pode responder 8 dos
    10 papeis e nao conhecer os outros 2. Repetir os 10 na reserva gastaria
    requisicao a toa; pedir so os 2 que faltam e o correto.

    Se todos falharem, devolve o que tiver, possivelmente nada. Quem chama
    trata a ausencia. Um fornecedor fora do ar nao pode derrubar a checagem dos
    alertas -- silencio por erro de rede seria indistinguivel de "nada rompeu".
    """

    provedores: tuple[ProvedorDeCotacoes, ...] = field(default_factory=tuple)

    @property
    def nome(self) -> str:
        return "+".join(p.nome for p in self.provedores)

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        encontradas: dict[str, Cotacao] = {}
        pendentes = list(tickers)

        for provedor in self.provedores:
            if not pendentes:
                break
            try:
                novas = provedor.cotacoes(pendentes)
            except Exception:
                # Rede de seguranca: mesmo que um adaptador deixe escapar algo
                # inesperado, a falha de UM fornecedor nao impede os seguintes.
                logger.exception("[cotacoes] provedor %s falhou", provedor.nome)
                continue
            encontradas.update(novas)
            pendentes = [t for t in pendentes if t not in encontradas]

        if pendentes:
            logger.info("[cotacoes] sem cotacao para: %s", pendentes)
        return encontradas
