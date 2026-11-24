"""O que fica de fora das contas de cripto: o que nao e "cripto que se mexe".

A mesma regra vale para o backtest (`scripts/cripto_historico.py`) e para a
analise contra o Bitcoin (`scanner.cripto.analise`):

- tokens alavancados da Binance: os de nome longo (BTCUP, ETHDOWN, ...) ja saem
  na lista de pares (`binance.pares_em_dolar`); BULL e BEAR, os de 2020 sobre o
  BTC, tem quatro letras e escapavam da regra do nome (24/11/2026);
- stablecoins e moeda estatal tokenizada (USDC, EUR, ...) saem pelo proprio
  preco: quem passou a vida a menos de 10% de distancia da propria mediana em
  95% dos dias nao e ativo de risco, tenha o nome que tiver;
- ouro e bitcoin embrulhados (PAXG, WBTC, ...) saem por lista: o preco deles e
  o de outro ativo;
- acoes e fundos americanos tokenizados (NVDAB, TSLAB, SQQQB, ...): a Binance
  listou 93 de 11/06 a 28/10/2026, todos com o ticker da bolsa mais um "B". Nao
  ha campo na API que os separe, entao a regra e o nome com a data: termina em
  "B" e estreou a partir de 01/06/2026. As criptos que terminam em B estrearam
  todas antes (BNB, SHIB, ARB, CKB, TRB, ..., a ultima foi a YB em 10/2025).
  Uma cripto nova com esse final cairia aqui por engano: por isso a carga lista
  quem ficou de fora e por que.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

# Preco de outro ativo: ouro, bitcoin e ether embrulhados.
EMBRULHADOS = frozenset({"PAXG", "XAUT", "WBTC", "WBETH", "BETH", "BNSOL"})
# Tokens alavancados de quatro letras (os de nome longo saem em `binance`).
ALAVANCADOS_CURTOS = frozenset({"BULL", "BEAR"})
# Stablecoin: a 95% dos dias a menos de 10% da propria mediana.
FAIXA_ESTAVEL = 0.10
DIAS_ESTAVEIS = 0.95
MINIMO_DE_DIAS = 30
# Acoes tokenizadas da Binance: ticker + "B", desde junho de 2026.
SUFIXO_DE_ACAO = "B"
ESTREIA_DAS_ACOES = date(2026, 6, 1)


def e_estavel(fechamento: pd.Series) -> bool:
    """Preco que nao se mexe: stablecoin, pelo comportamento e nao pelo nome."""
    precos = fechamento.dropna()
    if len(precos) < MINIMO_DE_DIAS:
        return False
    mediana = float(precos.median())
    perto = ((precos / mediana - 1).abs() < FAIXA_ESTAVEL).mean()
    return bool(perto >= DIAS_ESTAVEIS)


def e_acao_tokenizada(moeda: str, fechamento: pd.Series) -> bool:
    """Ticker de bolsa + "B" listado pela Binance a partir de junho de 2026."""
    if len(moeda) < 3 or not moeda.endswith(SUFIXO_DE_ACAO):
        return False
    presentes = fechamento.dropna()
    if presentes.empty:
        return False
    return bool(pd.DatetimeIndex(presentes.index).min().date() >= ESTREIA_DAS_ACOES)


def motivo_de_fora(moeda: str, fechamento: pd.Series) -> str | None:
    """Por que a moeda fica de fora das contas, ou None se ela entra.

    `fechamento` e a serie diaria da moeda, indexada pela data.
    """
    if moeda in EMBRULHADOS:
        return "embrulhado"
    if moeda in ALAVANCADOS_CURTOS:
        return "alavancado"
    if e_acao_tokenizada(moeda, fechamento):
        return "acao tokenizada"
    if e_estavel(fechamento):
        return "estavel"
    return None
