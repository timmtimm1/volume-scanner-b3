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
    """Preco de um papel agora, e de onde ele veio.

    `fonte` nao e enfeite: quando um alerta disparar em preco que parece
    estranho, a primeira pergunta e "qual fornecedor disse isso?".
    """

    ticker: str
    preco: Decimal
    fonte: str


class ProvedorDeCotacoes(Protocol):
    """O que todo fornecedor precisa saber fazer."""

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
        """Preco atual dos tickers pedidos.

        Devolve so o que conseguiu. Ticker ausente do resultado significa "nao
        sei", nunca "nao existe" -- e quem chama decide o que fazer com isso.
        Nunca levanta excecao por falha do fornecedor.
        """
        ...
