"""Cotacao atual dos papeis, para os alertas de rompimento.

O pipeline do scanner vive do COTAHIST: dado oficial, fechado, do pregao
anterior. Alerta de rompimento precisa do oposto -- o preco de agora. Sao duas
fontes com contratos diferentes, e por isso esta pasta existe separada de
`ingest/`.

O desenho e portado do `portfolio-api`, que ja resolveu este problema: um
contrato (`ProvedorDeCotacoes`), um adaptador por fornecedor, e um encadeador
que completa lacunas em vez de fazer failover.
"""

from scanner.cotacoes.base import Cotacao, ProvedorDeCotacoes
from scanner.cotacoes.brapi import BrapiClient
from scanner.cotacoes.encadeado import ProvedorEncadeado
from scanner.cotacoes.yahoo import YahooClient

__all__ = [
    "BrapiClient",
    "Cotacao",
    "ProvedorDeCotacoes",
    "ProvedorEncadeado",
    "YahooClient",
]
