"""O historico diario de toda moeda que ja passou pela Binance, para a analise.

A pagina Analise compara cada moeda com o Bitcoin desde 2017. O banco do site
guarda so 400 dias de candles das 50 maiores (`daily_bars`); aqui fica o resto,
numa forma compacta: uma `Historico` por moeda, com uma lista de fechamentos e
outra de volumes em dolar, um valor por dia do calendario (NaN no dia sem
candle). A tabela `analise_moedas` guarda isso entre uma noite e outra.

A carga de cada noite (`atualizar`) pede a Binance so o que falta:

- moeda que o estado ainda nao tem: o historico inteiro, desde 2017;
- moeda que ainda negocia: os dias depois do ultimo candle guardado;
- moeda deslistada: nada (o passado dela nao muda).

As moedas fora da Binance (`mercado.MOEDAS_FORA_DA_BINANCE`, hoje a XMR) tem o
historico da Binance ate a suspensao e depois a Kraken. A Kraken so devolve os
ultimos 720 dias: o buraco entre as duas fontes fica como buraco (a analise
recomeca a serie nele), e e por isso que o estado precisa ser guardado -- sem
ele, a cada noite o comeco da Kraken andaria um dia para frente.

Os contratos de commodity (`commodities.CONTRATOS`) vem do arquivo publico da
Binance Futures (`scanner.cripto.futuros`), desde o primeiro candle de cada um.

Uma moeda que falha numa noite fica como estava, e a falha vai para o
relatorio. O BTC e a regua de todas: se ele falha, a carga para.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

import httpx
import numpy as np
import numpy.typing as npt
import pandas as pd

from scanner.cripto.analise import BENCHMARK
from scanner.cripto.commodities import Contrato
from scanner.semana.fontes import FonteIndisponivelError

INICIO = date(2017, 1, 1)
BINANCE = "binance"
KRAKEN = "kraken"
FUTUROS = "binance-futuros"

# (moeda, par, desde) -> barras no formato do banco (trade_date, close,
# volume_financial, ...), so com dias ja fechados.
BuscarBarras = Callable[[str, str, date], pd.DataFrame]


@dataclass(frozen=True)
class Historico:
    """Os fechamentos e volumes diarios de uma moeda, do primeiro ao ultimo candle."""

    moeda: str
    par: str
    fonte: str
    negociando: bool
    primeiro_dia: date
    fechamentos: npt.NDArray[np.float64]
    volumes: npt.NDArray[np.float64]

    @property
    def ultimo_dia(self) -> date:
        return self.primeiro_dia + timedelta(days=len(self.fechamentos) - 1)

    def dias(self) -> pd.DatetimeIndex:
        return pd.date_range(self.primeiro_dia, periods=len(self.fechamentos), freq="D")

    def serie(self) -> pd.Series:
        """Fechamento por dia do calendario (NaN no dia sem candle)."""
        return pd.Series(self.fechamentos, index=self.dias(), name=self.moeda)


def _por_dia(barras: pd.DataFrame) -> pd.DataFrame:
    """Barras -> fechamento e volume indexados pelo dia, sem dia repetido."""
    frame = pd.DataFrame(
        {
            "dia": pd.to_datetime(barras["trade_date"]).dt.normalize(),
            "close": pd.to_numeric(barras["close"], errors="coerce"),
            "volume": pd.to_numeric(barras["volume_financial"], errors="coerce"),
        }
    ).dropna(subset=["close"])
    return frame.drop_duplicates("dia", keep="last").set_index("dia").sort_index()


def de_barras(
    moeda: str, par: str, fonte: str, negociando: bool, barras: pd.DataFrame
) -> Historico | None:
    """O historico de uma moeda a partir das barras dela, ou None se nao vier nenhuma."""
    dados = _por_dia(barras)
    if dados.empty:
        return None
    dias = pd.date_range(dados.index.min(), dados.index.max(), freq="D")
    cheio = dados.reindex(dias)
    return Historico(
        moeda=moeda,
        par=par,
        fonte=fonte,
        negociando=negociando,
        primeiro_dia=dias[0].date(),
        fechamentos=cheio["close"].to_numpy(dtype="float64"),
        volumes=cheio["volume"].to_numpy(dtype="float64"),
    )


def juntar(h: Historico, barras: pd.DataFrame, *, fonte: str | None = None) -> Historico:
    """Acrescenta os dias depois do ultimo guardado; os de antes sao ignorados."""
    dados = _por_dia(barras)
    dados = dados[dados.index > pd.Timestamp(h.ultimo_dia)]
    if dados.empty:
        return h
    dias = pd.date_range(h.primeiro_dia, dados.index.max(), freq="D")
    velho = pd.DataFrame({"close": h.fechamentos, "volume": h.volumes}, index=h.dias())
    cheio = pd.concat([velho, dados.loc[:, ["close", "volume"]]]).reindex(dias)
    fontes = h.fonte if fonte is None or fonte in h.fonte.split("+") else f"{h.fonte}+{fonte}"
    return replace(
        h,
        fonte=fontes,
        fechamentos=cheio["close"].to_numpy(dtype="float64"),
        volumes=cheio["volume"].to_numpy(dtype="float64"),
    )


def matrizes(historicos: Iterable[Historico]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fechamentos e volumes lado a lado: um dia por linha, uma moeda por coluna."""
    lista = list(historicos)
    if not lista:
        vazio = pd.DataFrame(index=pd.DatetimeIndex([]), dtype="float64")
        return vazio, vazio.copy()
    inicio = min(h.primeiro_dia for h in lista)
    fim = max(h.ultimo_dia for h in lista)
    dias = pd.date_range(inicio, fim, freq="D")
    deslocamento = {h.moeda: (h.primeiro_dia - inicio).days for h in lista}
    fech = np.full((len(dias), len(lista)), np.nan)
    vol = np.full((len(dias), len(lista)), np.nan)
    for j, h in enumerate(lista):
        a = deslocamento[h.moeda]
        fech[a : a + len(h.fechamentos), j] = h.fechamentos
        vol[a : a + len(h.volumes), j] = h.volumes
    colunas = [h.moeda for h in lista]
    return (
        pd.DataFrame(fech, index=dias, columns=colunas),
        pd.DataFrame(vol, index=dias, columns=colunas),
    )


@dataclass
class RelatorioDaCarga:
    """O que a carga da noite fez, para o log do workflow."""

    novas: int = 0
    atualizadas: int = 0
    em_dia: int = 0
    paradas: int = 0
    chamadas: int = 0
    falhas: list[str] = field(default_factory=list)

    def summary(self) -> str:
        texto = (
            f"{self.novas} nova(s), {self.atualizadas} atualizada(s), {self.em_dia} ja em dia, "
            f"{self.paradas} parada(s) (deslistadas), {self.chamadas} pedido(s)"
        )
        if self.falhas:
            texto += f"; {len(self.falhas)} falha(s): {', '.join(sorted(self.falhas))}"
        return texto


_FALHAS_DE_REDE = (FonteIndisponivelError, httpx.HTTPError)


def atualizar(
    estado: Mapping[str, Historico],
    pares: Mapping[str, str],
    negociando: set[str],
    ontem: date,
    *,
    binance: BuscarBarras,
    kraken: BuscarBarras,
    fora_da_binance: Mapping[str, str],
    futuros: BuscarBarras | None = None,
    contratos: Mapping[str, Contrato] | None = None,
) -> tuple[dict[str, Historico], RelatorioDaCarga]:
    """O estado da noite: o de ontem mais os candles que faltam, sem tocar o resto.

    `pares`: moeda -> par na Binance, inclusive os deslistados. `negociando`:
    as moedas com o par em TRADING hoje. `fora_da_binance`: moeda -> par na
    Kraken. `contratos`: ticker -> contrato perpetuo, buscado por `futuros`.
    """
    contratos = contratos or {}
    novo: dict[str, Historico] = dict(estado)
    rel = RelatorioDaCarga()

    # O BTC primeiro: sem ele nada mais faz sentido, e a falha aparece cedo.
    ordem = sorted(pares, key=lambda m: (m != BENCHMARK, m))
    for moeda in ordem:
        par = pares[moeda]
        vivo = moeda in negociando
        h = novo.get(moeda)
        try:
            if h is None:
                rel.chamadas += 1
                criado = de_barras(moeda, par, BINANCE, vivo, binance(moeda, par, INICIO))
                if criado is not None:
                    novo[moeda] = criado
                    rel.novas += 1
                continue
            if not vivo:
                novo[moeda] = replace(h, negociando=False)
                rel.paradas += 1
                continue
            if h.ultimo_dia >= ontem:
                novo[moeda] = replace(h, negociando=True)
                rel.em_dia += 1
                continue
            rel.chamadas += 1
            barras = binance(moeda, par, h.ultimo_dia + timedelta(days=1))
            novo[moeda] = replace(juntar(h, barras, fonte=BINANCE), negociando=True)
            rel.atualizadas += 1
        except _FALHAS_DE_REDE:
            if moeda == BENCHMARK:
                raise
            rel.falhas.append(moeda)

    for moeda, par_kraken in fora_da_binance.items():
        h = novo.get(moeda)
        desde = INICIO if h is None else h.ultimo_dia + timedelta(days=1)
        if desde > ontem:
            if h is not None:
                novo[moeda] = replace(h, negociando=True)
            continue
        try:
            rel.chamadas += 1
            barras = kraken(moeda, par_kraken, desde)
        except _FALHAS_DE_REDE:
            rel.falhas.append(moeda)
            continue
        if h is None:
            criado = de_barras(moeda, par_kraken, KRAKEN, True, barras)
            if criado is not None:
                novo[moeda] = criado
                rel.novas += 1
        else:
            novo[moeda] = replace(juntar(h, barras, fonte=KRAKEN), negociando=True)
            rel.atualizadas += 1

    for moeda, contrato in contratos.items():
        # Um ticker do contrato que passe a existir tambem a vista misturaria as
        # duas series: o contrato fica parado, e o log avisa.
        if moeda in pares or moeda in fora_da_binance:
            rel.falhas.append(f"{moeda} (ticker repetido no mercado a vista)")
            continue
        h = novo.get(moeda)
        desde = max(INICIO, contrato.estreia) if h is None else h.ultimo_dia + timedelta(days=1)
        if desde > ontem:
            if h is not None:
                novo[moeda] = replace(h, negociando=True)
                rel.em_dia += 1
            continue
        if futuros is None:
            raise ValueError("contratos sem a busca de futuros")
        try:
            rel.chamadas += 1
            barras = futuros(moeda, contrato.par, desde)
        except _FALHAS_DE_REDE:
            rel.falhas.append(moeda)
            continue
        if h is None:
            criado = de_barras(moeda, contrato.par, FUTUROS, True, barras)
            if criado is not None:
                novo[moeda] = criado
                rel.novas += 1
        else:
            novo[moeda] = replace(juntar(h, barras, fonte=FUTUROS), negociando=True)
            rel.atualizadas += 1

    # Moeda que sumiu da lista da Binance continua com o historico que tem.
    for moeda, h in novo.items():
        fora_das_listas = (
            moeda not in pares and moeda not in fora_da_binance and moeda not in contratos
        )
        if fora_das_listas and h.negociando:
            novo[moeda] = replace(h, negociando=False)

    btc = novo.get(BENCHMARK)
    if btc is None or btc.ultimo_dia < ontem:
        visto = "nenhum" if btc is None else btc.ultimo_dia.isoformat()
        raise FonteIndisponivelError(
            BINANCE, f"o {BENCHMARK} nao chegou ate {ontem} (ultimo: {visto}): sem regua"
        )
    return novo, rel
