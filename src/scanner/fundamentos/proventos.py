"""Proventos em dinheiro: de que papel e cada um, e como saber se estao certos.

Sao duas consultas na B3, com garantias diferentes:

- **Recentes** (ultimos ~12 meses): cada provento vem com o ISIN do papel, e a
  consulta e feita pelo codigo do emissor. O ISIN diz exatamente de que papel e
  o provento, entao aqui nao ha ambiguidade.
- **Historico** (o resto): a consulta e feita pelo NOME de pregao da empresa, e
  a resposta identifica a acao so pela classe (`ON`, `PN`, `PNA`, `UNT`). Nome
  e chave fraca: "KLABIN" traz 18 registros de outra empresa, e "KLABIN S.A."
  traz os 219 certos.

Por isso o historico so entra no banco depois de conferido, de uma das duas
maneiras:

1. **Contra o COTAHIST.** Cada linha do historico traz o fechamento do papel na
   data com, e esse numero tem de bater com a barra que o scanner ja tem
   daquele dia. Um historico da empresa errada erra o preco quase sempre.
2. **Contra os proventos recentes.** Quando as datas do historico sao anteriores
   as barras que o banco guarda, a primeira prova nao alcanca. Ai vale comparar
   a parte recente do historico com o que ja entrou pelo ISIN: outra companhia
   nao pagaria os mesmos centavos por acao nas mesmas datas.

Nao dando para conferir de nenhum dos dois jeitos, o historico e descartado:
preferimos ficar sem dividend yield antigo a mostrar o provento de outra
empresa.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from scanner.fundamentos.b3 import Provento

# Posicoes 7-8 do ISIN dizem o tipo do papel, e 10-11 a classe da acao.
# Medido nos ISINs reais da B3: BRUNIPACNOR7 (ON), BRUNIPACNPA0 (PNA),
# BRKLBNCDAM18 (unit, certificado de deposito) e BRBPACUNT006 (unit).
_CLASSES_DE_ACAO = {
    "OR": "ON",
    "PR": "PN",
    "PA": "PNA",
    "PB": "PNB",
    "PC": "PNC",
    "PD": "PND",
}

# Quanto o fechamento da B3 pode diferir do nosso e ainda ser o mesmo papel.
# Nao e zero porque a B3 arredonda em duas casas e o COTAHIST guarda quatro.
TOLERANCIA_DE_PRECO = Decimal("0.02")

# Quantas datas precisam ser comparaveis para a conferencia valer alguma coisa.
MINIMO_COMPARAVEL = 3

# Que fracao delas precisa bater.
FRACAO_MINIMA = 0.8


def classe_do_isin(isin: str) -> str | None:
    """A classe do papel que o ISIN descreve, ou None se o formato nao for conhecido."""
    codigo = isin.strip().upper()
    if len(codigo) < 12:
        return None
    if codigo[6:9] == "UNT" or codigo[6:8] == "CD":
        return "UNT"
    if codigo[6:8] == "AC":
        return _CLASSES_DE_ACAO.get(codigo[9:11])
    return None


@dataclass(frozen=True)
class Linha:
    """Um provento ja ligado ao papel, pronto para o banco."""

    ticker: str
    tipo: str
    valor: Decimal
    data_com: date
    data_aprovacao: date | None
    data_pagamento: date | None
    fonte: str


@dataclass(frozen=True)
class Conferencia:
    """O que a comparacao com o COTAHIST achou."""

    comparaveis: int
    batendo: int

    @property
    def aprovado(self) -> bool:
        if self.comparaveis < MINIMO_COMPARAVEL:
            return False
        return self.batendo / self.comparaveis >= FRACAO_MINIMA

    def resumo(self) -> str:
        if self.comparaveis < MINIMO_COMPARAVEL:
            return f"so {self.comparaveis} datas comparaveis"
        return f"{self.batendo} de {self.comparaveis} precos batem"


def ligar_recentes(proventos: Sequence[Provento], por_isin: Mapping[str, str]) -> list[Linha]:
    """Liga cada provento recente ao papel pelo ISIN.

    ISIN que nao e da empresa esperada nao vira linha: e assim que uma resposta
    da empresa errada (o codigo de emissor da B3 e uma chave fraca) fica de
    fora em vez de virar dado.
    """
    linhas: list[Linha] = []
    for provento in proventos:
        if provento.isin is None:
            continue
        ticker = por_isin.get(provento.isin.upper())
        if ticker is None:
            continue
        linhas.append(
            Linha(
                ticker=ticker,
                tipo=provento.tipo,
                valor=provento.valor,
                data_com=provento.data_com,
                data_aprovacao=provento.data_aprovacao,
                data_pagamento=provento.data_pagamento,
                fonte="recente",
            )
        )
    return linhas


def ligar_historicos(
    proventos: Sequence[Provento], por_classe: Mapping[str, str], *, antes_de: date | None
) -> list[Linha]:
    """Liga cada provento do historico ao papel pela classe.

    `antes_de` e a fronteira com a consulta dos recentes: o que cai dentro da
    janela dela ja foi gravado com o ISIN, que e mais confiavel.
    """
    linhas: list[Linha] = []
    for provento in proventos:
        if provento.classe is None:
            continue
        if antes_de is not None and provento.data_com >= antes_de:
            continue
        ticker = por_classe.get(provento.classe.upper())
        if ticker is None:
            continue
        linhas.append(
            Linha(
                ticker=ticker,
                tipo=provento.tipo,
                valor=provento.valor,
                data_com=provento.data_com,
                data_aprovacao=provento.data_aprovacao,
                data_pagamento=None,
                fonte="historico",
            )
        )
    return linhas


def conferir_com_recentes(
    proventos: Sequence[Provento],
    por_classe: Mapping[str, str],
    recentes: Sequence[tuple[str, date, Decimal]],
) -> Conferencia:
    """Compara o historico com o que ja veio identificado pelo ISIN.

    E a segunda maneira de provar que o historico e da empresa certa, e serve
    justamente para quem a primeira nao alcanca: empresa cujos proventos sao
    todos anteriores as barras que o banco guarda, mas que pagou algo nos
    ultimos 12 meses. Os valores por acao tem de bater papel a papel -- outra
    companhia nao pagaria os mesmos centavos nas mesmas datas.
    """
    if not recentes:
        return Conferencia(comparaveis=0, batendo=0)

    conhecidos = {(t, d, _arredondar(v)) for t, d, v in recentes}
    fronteira = min(d for _, d, _ in recentes)

    comparaveis = 0
    batendo = 0
    for provento in proventos:
        if provento.classe is None or provento.data_com < fronteira:
            continue
        ticker = por_classe.get(provento.classe.upper())
        if ticker is None:
            continue
        comparaveis += 1
        if (ticker, provento.data_com, _arredondar(provento.valor)) in conhecidos:
            batendo += 1
    return Conferencia(comparaveis=comparaveis, batendo=batendo)


def _arredondar(valor: Decimal) -> Decimal:
    """Oito casas: o bastante para distinguir proventos, sem prender a ruido."""
    return valor.quantize(Decimal("0.00000001"))


def conferir_precos(
    proventos: Sequence[Provento],
    por_classe: Mapping[str, str],
    fechamentos: Mapping[tuple[str, date], Decimal],
) -> Conferencia:
    """Compara o fechamento que a B3 diz na data com contra o do COTAHIST.

    E o que prova que o historico e mesmo da empresa que pedimos: o nome de
    pregao pode casar com outra companhia, mas o preco dela nas mesmas datas
    nao vai bater com o do nosso papel.
    """
    comparaveis = 0
    batendo = 0
    for provento in proventos:
        if provento.classe is None or provento.preco_data_com is None:
            continue
        ticker = por_classe.get(provento.classe.upper())
        if ticker is None:
            continue
        nosso = fechamentos.get((ticker, provento.data_com))
        if nosso is None or nosso <= 0:
            continue
        comparaveis += 1
        diferenca = abs(provento.preco_data_com - nosso) / nosso
        if diferenca <= TOLERANCIA_DE_PRECO:
            batendo += 1
    return Conferencia(comparaveis=comparaveis, batendo=batendo)
