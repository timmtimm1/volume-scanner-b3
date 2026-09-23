"""Cotacao atual dos papeis, para os alertas de rompimento.

O pipeline do scanner vive do COTAHIST: dado oficial, fechado, do pregao
anterior. Serve para o alerta de volume. Alerta de rompimento precisa do oposto
-- o preco de agora. Sao duas fontes com contratos diferentes, e por isso esta
pasta existe separada de `ingest/`.

O desenho veio do `portfolio-api`: um contrato (`ProvedorDeCotacoes`) e um
adaptador por fornecedor. O que junta os fornecedores e `ProvedorMaisRecente`,
que pergunta a todos e fica com a cotacao de hora mais nova.
"""

from scanner.cotacoes.base import Cota, Cotacao, ProvedorDeCotacoes
from scanner.cotacoes.brapi import BrapiClient
from scanner.cotacoes.mais_recente import ProvedorMaisRecente
from scanner.cotacoes.yahoo import YahooClient

__all__ = [
    "BrapiClient",
    "Cota",
    "Cotacao",
    "ProvedorDeCotacoes",
    "ProvedorMaisRecente",
    "YahooClient",
]
