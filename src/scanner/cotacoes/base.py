"""Contrato dos fornecedores de cotacao.

O dominio fala "PETR4". Cada fornecedor tem sua convencao -- o Yahoo quer
"PETR4.SA", a brapi quer "PETR4" -- e traduzir isso e trabalho do adaptador,
nunca do resto do sistema. Trocar de fornecedor e trocar um arquivo desta
pasta, nao uma migration.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

# Ticker da B3: quatro letras, um ou dois digitos, as vezes uma letra de classe
# (BPAC11, PETR4, TAEE11B). Os tickers vao no CAMINHO da URL dos fornecedores,
# entao isto nao e capricho de formato: e o que impede que um valor vindo da
# API do site altere a rota chamada. SSRF por interpolacao de caminho e falha
# real, e o alerta e a primeira funcionalidade em que o usuario digita um
# ticker que chega ate aqui.
TICKER = re.compile(r"^[A-Z]{4}\d{1,2}[A-Z]?$")


def ticker_valido(valor: str) -> bool:
    """Se o ticker tem a forma de um papel da B3."""
    return bool(TICKER.match(valor))


@dataclass(frozen=True)
class Cotacao:
    """Preco de um papel, de quando e de onde ele veio.

    `fonte` nao e enfeite: quando um alerta disparar em preco que parece
    estranho, a primeira pergunta e "qual fornecedor disse isso?".

    `hora` e o momento da cotacao segundo o fornecedor, com fuso. Nenhum dos
    dois e tempo real -- a brapi gratuita atrasa cerca de 30 minutos, o Yahoo
    cerca de 15 -- e sem a hora nao da para saber se o preco e de agora ou do
    fechamento de ontem. Cotacao sem hora nao entra no sistema.
    """

    ticker: str
    preco: Decimal
    fonte: str
    hora: datetime


@dataclass(frozen=True)
class Cota:
    """Quanto sobrou do plano do fornecedor, quando ele diz nos cabecalhos.

    A brapi manda isto em TODA resposta -- inclusive nas que recusa. Ate agora
    o codigo jogava fora, e o unico jeito de saber que a cota tinha acabado era
    o alerta parar de chegar. `RelatorioDeChecagem` agora carrega isto para o
    log da checagem.

    Os dois numeros sao independentes e nem sempre vem juntos: `restantes` sem
    `limite` ainda serve, e o contrario tambem.
    """

    restantes: int | None = None
    limite: int | None = None

    @property
    def vazia(self) -> bool:
        return self.restantes is None and self.limite is None

    def resumo(self) -> str:
        """`14.231/15.000`, `14.231` ou `?`, conforme o que o fornecedor disse."""
        if self.restantes is None:
            return "?" if self.limite is None else f"?/{self.limite:,}".replace(",", ".")
        if self.limite is None:
            return f"{self.restantes:,}".replace(",", ".")
        return f"{self.restantes:,}/{self.limite:,}".replace(",", ".")


class ProvedorDeCotacoes(Protocol):
    """O que todo fornecedor precisa saber fazer."""

    @property
    def hora_e_do_negocio(self) -> bool:
        """Se `Cotacao.hora` e a hora do ultimo negocio, e nao a de agora.

        Isto nao e detalhe de implementacao, e o que decide se a cotacao pode
        ser comparada com outra ou usada para dizer "este preco e de hoje".

        Medido em 23/09/2026, com o mercado aberto: PETR4, VALE3 e ITUB4 pedidos
        a brapi as 10:23:30 voltaram os tres com `regularMarketTime` de
        13:23:30.000Z -- identico ao segundo, igual ao instante da resposta. No
        mesmo momento, VIVA3 voltou com abertura, maxima, minima, fechamento e
        volume EXATAMENTE iguais ao pregao ja fechado de 22/09, carimbado como
        23/09 as 10:19. O Yahoo, no mesmo instante, deu 10:10:14 -- a hora do
        ultimo negocio de verdade -- e o parcial correto.

        Ou seja: a brapi carimba o relogio da resposta, nao o do negocio. Em
        papel liquido o dado esta fresco e isso nao faz mal; em papel de giro
        menor, antes da abertura, no fim de semana e no feriado, ela serve dado
        velho dizendo que e de agora.

        Fornecedor que responde `False` aqui nao entra na disputa por hora mais
        nova: ele so e consultado para o que os outros nao souberam responder.
        """
        ...

    @property
    def nome(self) -> str:
        """Como o fornecedor se identifica nos logs e no aviso de disparo.

        Declarado como property, e nao como atributo: atributo em Protocol
        exige que a implementacao permita ESCRITA, e os adaptadores sao
        dataclasses congeladas. Somente leitura e o que eles oferecem, e o que
        basta aqui.
        """
        ...

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        """Ultima cotacao conhecida dos tickers pedidos.

        Devolve so o que conseguiu. Ticker ausente do resultado significa "nao
        sei", nunca "nao existe" -- e quem chama decide o que fazer com isso.
        Nunca levanta excecao por falha do fornecedor.
        """
        ...
