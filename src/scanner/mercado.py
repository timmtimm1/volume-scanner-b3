"""Qual mercado este processo opera: a B3 (padrao) ou as criptos.

Pedido do usuario em 16/11/2026: uma aba de criptos com os mesmos setups. Em vez
de misturar moedas e acoes nas mesmas tabelas (o universo, o z-score, a media do
mercado e o sorteio do controle passariam a enxergar os dois), o pipeline
inteiro roda uma segunda vez, num schema proprio do mesmo banco. Quem escolhe e
a variavel de ambiente `SCANNER_MERCADO`:

- `b3` (ou ausente): tudo como sempre, schema `volume_scanner`, `config.yaml`;
- `cripto`: schema `cripto_scanner`, `config-cripto.yaml`, calendario sem
  feriado nem fim de semana, candles da Binance em dolar (USDT).

E variavel de ambiente de verdade, e nao linha do `.env`: o `.env` da maquina
vale para os dois mercados, e trocar de mercado tem de ser explicito em cada
comando (`SCANNER_MERCADO=cripto scanner daily`).

O que muda de um mercado para o outro mora aqui, para o resto do codigo nao
espalhar `if cripto`: o schema, o menor passo de preco (`tick`), o custo por
lado do backtest, o piso de liquidez e como se escreve a quantidade de um trade.
"""

from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING

# Este modulo e importado por `scanner.calendar`, que o passo "Hoje e pregao?"
# do workflow `rompimentos` roda com o Python do runner, SEM as dependencias
# instaladas. Por isso nada de fora da biblioteca padrao no nivel do modulo: o
# numpy entra so dentro de `tick`, que trabalha com matriz. Em 17/11/2026 o
# `import numpy` aqui em cima derrubou todas as passadas do pregao.
if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    F64 = npt.NDArray[np.float64]

B3 = "b3"
CRIPTO = "cripto"
VARIAVEL = "SCANNER_MERCADO"

_SCHEMAS = {B3: "volume_scanner", CRIPTO: "cripto_scanner"}
_CONFIGS = {B3: "config.yaml", CRIPTO: "config-cripto.yaml"}
# Por lado. B3: 0,03% de taxas + 0,05% de derrapagem. Cripto: 0,10% de taxa da
# Binance (spot, sem desconto) + 0,05% de derrapagem.
_CUSTOS = {B3: 0.0008, CRIPTO: 0.0015}
# Mediana de volume diario para o papel contar como liquido no backtest, na
# moeda do mercado: R$ 500 mil na B3, US$ 5 milhoes em cripto (o volume das
# moedas e muito maior, e abaixo disso o livro e raso demais para o stop valer).
_PISOS = {B3: 500_000.0, CRIPTO: 5_000_000.0}
_MOEDAS = {B3: "R$", CRIPTO: "US$"}
# Backtest: os anos em que a saida de cada setup e ESCOLHIDA e os anos em que
# ela e CONFERIDA (que nao podem ser usados para escolher). A B3 tem COTAHIST
# desde 1995; a Binance abriu em agosto de 2017, e a divisao de cripto deixa
# nos dois lados um ciclo inteiro de alta e de queda (2017-2021 e 2022-2026).
_PERIODOS = {B3: ((1995, 2015), (2016, 2026)), CRIPTO: ((2017, 2021), (2022, 2026))}

CENTAVO = 0.01
# Em cripto nao existe centavo: uma moeda vale 65 mil dolares e outra 0,00001.
# O passo e relativo -- a quinta casa significativa do preco (1 para o BTC a
# 65.000, 0,00001 para uma moeda a 0,52), que e de 1 a 10 pontos-base.
CASAS_SIGNIFICATIVAS = 4


class MercadoInvalidoError(ValueError):
    """`SCANNER_MERCADO` com um valor que nao e mercado nenhum."""


def atual() -> str:
    """O mercado deste processo, lido do ambiente a cada chamada."""
    valor = os.environ.get(VARIAVEL, B3).strip().lower() or B3
    if valor not in _SCHEMAS:
        raise MercadoInvalidoError(f"{VARIAVEL}={valor!r} nao existe; use {B3!r} ou {CRIPTO!r}")
    return valor


def e_cripto() -> bool:
    return atual() == CRIPTO


def schema() -> str:
    """Schema do Postgres onde vivem as tabelas deste mercado."""
    return _SCHEMAS[atual()]


def arquivo_de_config() -> str:
    return _CONFIGS[atual()]


def custo() -> float:
    """Custo por lado de um trade, como fracao do preco."""
    return _CUSTOS[atual()]


def piso_de_liquidez() -> float:
    return _PISOS[atual()]


def moeda() -> str:
    """Simbolo da moeda em que o mercado e cotado."""
    return _MOEDAS[atual()]


def periodos() -> tuple[tuple[int, int], tuple[int, int]]:
    """Os anos de escolha e os de conferencia do backtest deste mercado."""
    return _PERIODOS[atual()]


def rotulos_de_periodo() -> tuple[str, ...]:
    """Todos os rotulos de periodo que a grade do backtest pode ter, em qualquer mercado."""
    rotulos = {f"{a}-{b}" for par in _PERIODOS.values() for a, b in par}
    return (*sorted(rotulos), "tudo")


def tick_do_preco(preco: float) -> float:
    """O menor passo de preco em torno de `preco`.

    B3: sempre 1 centavo. Cripto: a quinta casa significativa.
    """
    if not e_cripto():
        return CENTAVO
    if not math.isfinite(preco) or preco <= 0:
        return float("nan")
    return float(10.0 ** (math.floor(math.log10(preco)) - CASAS_SIGNIFICATIVAS))


def tick(fechamento: F64, ajuste: F64) -> F64:
    """Matriz (pregao x papel) do menor passo de preco, na escala ajustada.

    B3: 1 centavo do dia, levado para a escala ajustada por desdobramento (o
    que o codigo fazia com `CENTAVO * ajuste`). Cripto: relativo ao fechamento
    do proprio dia; dia sem negocio herda o passo do ultimo dia negociado.
    """
    import numpy as np

    if not e_cripto():
        return CENTAVO * ajuste
    with np.errstate(divide="ignore", invalid="ignore"):
        passo = 10.0 ** (np.floor(np.log10(fechamento)) - CASAS_SIGNIFICATIVAS)
    passo[~np.isfinite(passo)] = np.nan
    # ffill por coluna sem pandas: indice do ultimo valor valido ate cada linha.
    linhas = np.arange(passo.shape[0])[:, None]
    ultimo = np.maximum.accumulate(np.where(np.isnan(passo), -1, linhas), axis=0)
    cheio = np.take_along_axis(passo, np.maximum(ultimo, 0), axis=0)
    cheio[ultimo < 0] = np.nan
    return np.asarray(cheio, dtype=np.float64)


def quantidade_curta(quantidade: float) -> str:
    """A posicao de um trade em poucos caracteres, para a tabela do Telegram.

    B3: acoes inteiras, como sempre ("70"). Cripto: fracionada, em no maximo 7
    caracteres -- tres algarismos significativos abaixo de 1, ate cinco casas
    ("0,0153", "0,00077"), duas casas ate mil ("12,5"), milhar com ponto
    ("123.456") e, acima de um milhao, "1,2mi".
    """
    if not e_cripto():
        return str(round(quantidade))
    q = abs(quantidade)
    if q >= 1_000_000:
        texto = f"{quantidade / 1_000_000:.1f}".replace(".", ",") + "mi"
    elif q >= 1_000:
        texto = f"{quantidade:,.0f}".replace(",", ".")
    elif q >= 1:
        texto = f"{quantidade:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    elif q > 0:
        casas = min(5, 2 - int(np.floor(np.log10(q))))
        texto = f"{quantidade:.{casas}f}".rstrip("0").rstrip(".").replace(".", ",")
    else:
        texto = "0"
    return texto
