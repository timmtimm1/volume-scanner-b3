"""As commodities da pagina Analise: ouro tokenizado e os contratos de commodity da Binance.

Pedido do usuario em 24/11/2026: ver junto das criptos as que acompanham
commodity (ouro, prata, petroleo...), medidas contra o mesmo BTC. Ficam num
grupo proprio, "commodity": entram no retorno por ano e por mes, no beta e na
correlacao, e ficam fora da cesta das 50 do estudo sazonal e da "moeda tipica",
que continuam so cripto.

Dois tipos:

- tokens a vista lastreados em ouro (PAXG, XAUT): ja vem na carga da Binance a
  vista. No backtest de cripto continuam de fora (`filtros.EMBRULHADOS`: o
  preco deles e o do ouro); aqui entram como commodity;
- contratos perpetuos de commodity da Binance Futures, os de `underlyingType`
  COMMODITY em 24/11/2026: ouro, prata, platina, paladio, cobre, petroleo WTI e
  Brent, gas natural. A API de futuros recusa os runners do Actions (EUA), entao
  os candles vem do arquivo publico da Binance (`scanner.cripto.futuros`).

A lista e fixa porque a API que diria "este contrato e commodity" e justamente a
que o Actions nao alcanca. Contrato novo entra aqui, com o dia do primeiro
candle. Os nomes e a descricao de cada uma, para a tela, ficam em
`web/src/lib/commodities.ts` (o teste confere que as duas listas batem).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

GRUPO_CRIPTO = "cripto"
GRUPO_COMMODITY = "commodity"

# Tokens a vista com lastro em ouro (1 token = 1 onca troy).
A_VISTA = frozenset({"PAXG", "XAUT"})


@dataclass(frozen=True)
class Contrato:
    """Um contrato perpetuo da Binance Futures (USDT-M)."""

    par: str
    # O dia do primeiro candle diario no arquivo publico: a carga comeca nele.
    estreia: date


# Ticker na tela -> contrato. O ticker e o `baseAsset` da Binance (XAU e o
# ouro, como no XAUUSD); nenhum deles existe no mercado a vista.
CONTRATOS: dict[str, Contrato] = {
    "XAU": Contrato("XAUUSDT", date(2025, 12, 11)),
    "XAG": Contrato("XAGUSDT", date(2026, 1, 7)),
    "XPT": Contrato("XPTUSDT", date(2026, 1, 30)),
    "XPD": Contrato("XPDUSDT", date(2026, 1, 30)),
    "COPPER": Contrato("COPPERUSDT", date(2026, 3, 6)),
    "CL": Contrato("CLUSDT", date(2026, 4, 1)),
    "BZ": Contrato("BZUSDT", date(2026, 4, 1)),
    "NATGAS": Contrato("NATGASUSDT", date(2026, 4, 1)),
}


def grupo(moeda: str) -> str:
    """O grupo da moeda: commodity (ouro tokenizado e contratos) ou cripto (o resto)."""
    return GRUPO_COMMODITY if moeda in A_VISTA or moeda in CONTRATOS else GRUPO_CRIPTO
