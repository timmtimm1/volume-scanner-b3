"""Os dois setups do estudo de 17/11/2026 que entraram na aba Cripto.

O estudo rodou os 6 setups do crypto-trader-skill (MIT,
github.com/syedishaq7262-svg/crypto-trader-skill) em timeframe maior, no motor
PyBacktestPro, em 684 moedas desde 2017 (diario) e nas 80 mais negociadas (4h).
Dois entraram no app, por decisao do usuario, com a nota do proprio estudo:

- **Reversao no RSI, compra, diario** (`rsi_reversao`): o RSI(14) esteve em 25
  ou menos nos 4 candles anteriores, voltou a 30 ou mais e o candle fechou em
  alta. Stop na minima dos ultimos 6. Nota: fraco (escolha 2017-2021 +0,08 R,
  conferencia 2022-2026 +0,12 R, intervalo cruzando o zero).
- **Rompimento de compressao, venda, 4h** (`compressao_venda`): a largura das
  Bandas de Bollinger (20, 2) esteve entre as 10% menores dos 180 candles
  anteriores em algum dos 12 anteriores, e o candle fechou abaixo da banda de
  baixo (o anterior nao). Stop na media de 20. Nota: firme (+0,13 R e +0,16 R;
  intervalo [+0,005; +0,29]), mas sem passar na correcao por 24 testes.
  Venda: precisa de futuros ou margem.

Diferente dos setups da aba Setups, a entrada e a ABERTURA do candle seguinte
(ordem a mercado), e nao "acima da maxima". Saida como no estudo: stop do
setup, alvo de 3R a partir do fechamento do sinal, e prazo maximo (20 candles
no diario, 42 no 4h), o que vier primeiro; stop antes do alvo quando os dois
cabem no mesmo candle.

As regras sao as mesmas do `backtest_cripto.py` do estudo, linha a linha (la em
Polars, aqui em pandas); `tests/test_cripto_estudo.py` confere os casos.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import numpy as np
import pandas as pd

from scanner.semana.fontes import TIMEOUT_SEGUNDOS, FonteIndisponivelError, baixar

# --------------------------------------------------------------------------
# Os setups e a nota do estudo
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SetupDoEstudo:
    nome: str
    titulo: str
    tf: str
    lado: str  # "compra" ou "venda"
    alvo_r: float
    prazo: int  # candles
    nivel: str  # firme, fraco ou falhou
    escolha_r: float
    conferencia_r: float
    ic: tuple[float, float]
    trades: int


SETUPS: dict[str, SetupDoEstudo] = {
    "rsi_reversao": SetupDoEstudo(
        "rsi_reversao",
        "Reversão no RSI",
        "1d",
        "compra",
        3.0,
        20,
        "fraco",
        0.079,
        0.116,
        (-0.100, 0.360),
        1622,
    ),
    "compressao_venda": SetupDoEstudo(
        "compressao_venda",
        "Compressão na venda",
        "4h",
        "venda",
        3.0,
        42,
        "firme",
        0.127,
        0.155,
        (0.005, 0.293),
        6432,
    ),
}

# Custos do estudo, por lado: 0,10% de taxa da Binance e 0,05% de derrapagem.
TAXA = 0.001
DERRAPAGEM = 0.0005
LIQUIDEZ_MINIMA = 1_000_000.0  # mediana do volume diario em dolar, 30 dias
BARRAS_POR_DIA = {"1d": 1, "4h": 6}
MS_POR = {"1d": 86_400_000, "4h": 14_400_000}

# --------------------------------------------------------------------------
# As regras (iguais as do estudo)
# --------------------------------------------------------------------------


def _liquido(v: pd.Series, tf: str) -> pd.Series:
    b = BARRAS_POR_DIA[tf]
    liq = v.shift(1).rolling(30 * b, min_periods=10 * b).median() * b
    return liq >= LIQUIDEZ_MINIMA


def _rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    ganho = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    perda = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rsi = 100 - 100 / (1 + ganho / perda)
    rsi[perda == 0] = 100.0
    return rsi.where(perda.notna())


def _rank_na_janela(x: np.ndarray, n: int, minimo: int) -> np.ndarray:
    """Posicao percentual do ultimo valor entre os `n` ultimos (rank medio / validos)."""
    if len(x) == 0:
        return np.full(0, np.nan)
    cheio = np.concatenate([np.full(n - 1, np.nan), x])
    w = np.lib.stride_tricks.sliding_window_view(cheio, n)
    ultimo = w[:, -1:]
    cont = (~np.isnan(w)).sum(1)
    menor = (w < ultimo).sum(1)
    igual = (w == ultimo).sum(1)
    rank = (menor + (igual + 1) / 2) / np.where(cont > 0, cont, 1)
    rank[(cont < minimo) | np.isnan(ultimo[:, 0])] = np.nan
    return np.asarray(rank, dtype=float)


def sinal_rsi_reversao(df: pd.DataFrame) -> pd.Series:
    """Stop no candle do sinal (NaN = sem sinal). `df` diario, em ordem."""
    c, low, v = df["Close"], df["Low"], df["VolUSD"]
    r = _rsi(c)
    cond = (r.shift(1).rolling(4).min() <= 25) & (r >= 30) & (c > c.shift())
    stop = low.rolling(6).min()
    ok = cond.fillna(False) & _liquido(v, "1d") & (stop < c)
    return stop.where(ok)


def sinal_compressao_venda(df: pd.DataFrame) -> pd.Series:
    """Stop no candle do sinal (NaN = sem sinal). `df` de 4h, em ordem."""
    c, v = df["Close"], df["VolUSD"]
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std(ddof=0)
    dn = mid - 2 * sd
    largura = ((mid + 2 * sd) - dn) / mid
    rank = pd.Series(_rank_na_janela(largura.to_numpy(dtype=float), 180, 90), index=df.index)
    comprimido = rank.shift(1).rolling(12).min() <= 0.10
    cond = comprimido & (c < dn) & (c.shift() >= dn.shift())
    ok = cond.fillna(False) & _liquido(v, "4h") & (mid > c)
    return mid.where(ok)


REGRAS: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    "rsi_reversao": sinal_rsi_reversao,
    "compressao_venda": sinal_compressao_venda,
}

# --------------------------------------------------------------------------
# O trade de cada sinal
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Trade:
    estado: str  # aguardando, aberto, alvo, stop, prazo
    entrada: float | None
    saida: float | None
    saida_em: datetime | None
    resultado_r: float | None  # encerrado: o final; aberto: ate o ultimo fechamento


def acompanhar(
    setup: SetupDoEstudo,
    fechamento: float,
    stop: float,
    candles: pd.DataFrame,
) -> Trade:
    """O trade de um sinal, nos candles DEPOIS dele (o primeiro e o da entrada).

    `candles`: Open/High/Low/Close, indice = abertura de cada candle. O ultimo
    pode estar em andamento (`fechado` False): ele da a entrada e o resultado
    parcial, mas nao encerra por prazo.
    """
    if candles.empty:
        return Trade("aguardando", None, None, None, None)
    venda = setup.lado == "venda"
    sinal = -1.0 if venda else 1.0
    risco_plano = sinal * (fechamento - stop)
    alvo = fechamento + sinal * setup.alvo_r * risco_plano
    o = candles["Open"].to_numpy(dtype=float)
    h = candles["High"].to_numpy(dtype=float)
    lo = candles["Low"].to_numpy(dtype=float)
    c = candles["Close"].to_numpy(dtype=float)
    fechado = candles["fechado"].to_numpy(dtype=bool)
    datas = list(candles.index)
    # entrada na abertura, com a derrapagem contra
    e = o[0] * (1 + sinal * DERRAPAGEM)
    risco = sinal * (e - stop)
    if risco <= 0:  # abriu do outro lado do stop: perda maior que 1R
        risco = abs(e - stop) or e * 1e-4

    def r_de(x: float) -> float:
        return float(sinal * (x - e) / risco - TAXA * (e + x) / risco)

    for i in range(len(o)):
        if i > setup.prazo:
            # saiu a mercado na abertura do candle depois do prazo
            x = o[i] * (1 - sinal * DERRAPAGEM)
            return Trade("prazo", e, x, datas[i], r_de(x))
        bateu_stop = h[i] >= stop if venda else lo[i] <= stop
        if bateu_stop:
            x = (max(stop, o[i]) if venda else min(stop, o[i])) * (1 - sinal * DERRAPAGEM)
            return Trade("stop", e, x, datas[i], r_de(x))
        bateu_alvo = lo[i] <= alvo if venda else h[i] >= alvo
        if bateu_alvo:
            x = min(alvo, o[i]) if venda else max(alvo, o[i])
            return Trade("alvo", e, x, datas[i], r_de(x))
        if not fechado[i]:
            break
    return Trade("aberto", e, None, None, r_de(c[len(c) - 1]))


# --------------------------------------------------------------------------
# Dados da Binance e a passada de 15 em 15 minutos
# --------------------------------------------------------------------------

URLS = ("https://data-api.binance.vision/api/v3", "https://api.binance.com/api/v3")
CANDLES_POR_TF = {"1d": 120, "4h": 400}


def candles_da_binance(dados: Any, agora_ms: int) -> pd.DataFrame:
    """Resposta de `klines` -> candles com a coluna `fechado` (o ultimo pode estar aberto)."""
    if not isinstance(dados, list) or not dados:
        return pd.DataFrame()
    bruto = pd.DataFrame(
        [x[:8] for x in dados],
        columns=["t", "Open", "High", "Low", "Close", "Vol", "fecha", "VolUSD"],
    )
    for col in ("Open", "High", "Low", "Close", "VolUSD"):
        bruto[col] = bruto[col].astype(float)
    bruto["fechado"] = bruto["fecha"].astype("int64") < agora_ms
    bruto.index = pd.to_datetime(bruto["t"].astype("int64"), unit="ms", utc=True)
    return bruto[["Open", "High", "Low", "Close", "VolUSD", "fechado"]]


def buscar_candles(par: str, tf: str, cliente: httpx.Client | None = None) -> pd.DataFrame:
    """Os ultimos candles do par: no Actions o espelho; o principal se o espelho falhar."""
    agora_ms = int(time.time() * 1000)
    ultimo_erro: Exception | None = None
    for base in URLS:
        try:
            r = baixar(
                "binance",
                f"{base}/klines?symbol={par}&interval={tf}&limit={CANDLES_POR_TF[tf]}",
                cliente=cliente,
            )
            return candles_da_binance(r.json(), agora_ms)
        except (FonteIndisponivelError, ValueError) as exc:
            ultimo_erro = exc
    raise FonteIndisponivelError("binance", f"{par} {tf}: {ultimo_erro}")


@dataclass(frozen=True)
class Novo:
    moeda: str
    setup: SetupDoEstudo
    sinal_em: datetime
    fechamento: float
    stop: float


def sinais_novos(
    moeda: str, setup: SetupDoEstudo, candles: pd.DataFrame, ultimos: int = 3
) -> list[Novo]:
    """Sinais nos `ultimos` candles FECHADOS (pega uma passada perdida)."""
    fechados = candles[candles["fechado"]]
    if len(fechados) < 30:
        return []
    stops = REGRAS[setup.nome](fechados).iloc[-ultimos:]
    fech = fechados["Close"]
    return [
        Novo(moeda, setup, pd.Timestamp(ts).to_pydatetime(), float(fech.loc[ts]), float(s))
        for ts, s in zip(stops.index, stops.to_numpy(dtype=float), strict=True)
        if np.isfinite(s)
    ]


def rodar(
    engine: Any,
    moedas: dict[str, str],
    *,
    avisar: Callable[[Novo, Trade], bool] | None = None,
    cliente: httpx.Client | None = None,
) -> str:
    """Uma passada: sinais novos dos dois setups e o acompanhamento dos abertos."""
    from scanner.storage.repository import gravar_sinais_estudo, sinais_estudo_abertos

    if cliente is None:
        with httpx.Client(timeout=TIMEOUT_SEGUNDOS) as proprio:
            return rodar(engine, moedas, avisar=avisar, cliente=proprio)

    pedidos = [(m, p, tf) for m, p in moedas.items() for tf in ("1d", "4h")]
    candles: dict[tuple[str, str], pd.DataFrame] = {}
    falhas = 0

    def um(pedido: tuple[str, str, str]) -> None:
        nonlocal falhas
        moeda, par, tf = pedido
        try:
            candles[(moeda, tf)] = buscar_candles(par, tf, cliente)
        except FonteIndisponivelError:
            falhas += 1

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(um, pedidos))

    # sinais novos (o banco ignora os que ja existem)
    novos: list[Novo] = []
    for setup in SETUPS.values():
        for moeda in moedas:
            c = candles.get((moeda, setup.tf))
            if c is not None and not c.empty:
                novos.extend(sinais_novos(moeda, setup, c))
    abertos = sinais_estudo_abertos(engine)
    chaves_abertas = {(a["moeda"], a["setup"], _utc(a["sinal_em"])) for a in abertos}
    # Um trade por vez por moeda e setup, como no estudo: sinal novo numa moeda
    # que ja tem um aberto do mesmo setup fica de fora.
    ocupadas = {(a["moeda"], a["setup"]) for a in abertos}
    novos = [
        n
        for n in sorted(novos, key=lambda x: x.sinal_em)
        if (n.moeda, n.setup.nome) not in ocupadas
        or (n.moeda, n.setup.nome, _utc(n.sinal_em)) in chaves_abertas
    ]
    # e dois sinais novos na mesma passada: so o mais antigo
    vistos: set[tuple[str, str]] = set()
    unicos = []
    for n in novos:
        if (n.moeda, n.setup.nome) in vistos:
            continue
        vistos.add((n.moeda, n.setup.nome))
        unicos.append(n)
    novos = [n for n in unicos if (n.moeda, n.setup.nome, _utc(n.sinal_em)) not in chaves_abertas]
    linhas = []
    for n in novos:
        linhas.append(_linha(n, candles.get((n.moeda, n.setup.tf))))
    # acompanhamento dos que ja estavam no banco
    for a in abertos:
        do_banco = SETUPS.get(a["setup"])
        c = candles.get((a["moeda"], do_banco.tf)) if do_banco else None
        if do_banco is None or c is None or c.empty:
            continue
        novo = Novo(a["moeda"], do_banco, a["sinal_em"], float(a["fechamento"]), float(a["stop"]))
        linhas.append(_linha(novo, c))
    inseridos = gravar_sinais_estudo(engine, linhas)
    avisados = 0
    if avisar is not None:
        for n, linha in zip(novos, linhas[: len(novos)], strict=True):
            chave = (n.moeda, n.setup.nome, _utc(n.sinal_em))
            # Sinal que ja encerrou quando foi visto (primeira passada, ou uma
            # falha longa) entra no banco, mas nao vira aviso: nao ha o que fazer.
            vivo = linha["_trade"].estado in ("aguardando", "aberto")
            if chave in inseridos and vivo and avisar(n, linha["_trade"]):
                avisados += 1
    estados = [linha["estado"] for linha in linhas[len(novos) :]]
    return (
        f"sinais do estudo: {len(inseridos)} novos ({avisados} avisados), "
        f"{len(abertos)} acompanhados ({estados.count('aberto')} abertos, "
        f"{len(estados) - estados.count('aberto') - estados.count('aguardando')} encerrados agora)"
        + (f"; {falhas} consultas falharam" if falhas else "")
    )


def _utc(quando: datetime) -> pd.Timestamp:
    ts = pd.Timestamp(quando)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _linha(n: Novo, c: pd.DataFrame | None) -> dict[str, Any]:
    """O sinal com o trade dele ate agora, no formato da tabela `sinais_estudo`."""
    depois = c[c.index > _utc(n.sinal_em)] if c is not None else pd.DataFrame()
    t = acompanhar(n.setup, n.fechamento, n.stop, depois)
    venda = n.setup.lado == "venda"
    risco = (n.stop - n.fechamento) if venda else (n.fechamento - n.stop)
    return {
        "moeda": n.moeda,
        "setup": n.setup.nome,
        "timeframe": n.setup.tf,
        "lado": n.setup.lado,
        "sinal_em": n.sinal_em,
        "fechamento": n.fechamento,
        "stop": n.stop,
        "alvo": n.fechamento + (-1 if venda else 1) * n.setup.alvo_r * risco,
        "prazo_candles": n.setup.prazo,
        "estado": t.estado,
        "entrada": t.entrada,
        "saida": t.saida,
        "saida_em": t.saida_em,
        "resultado_r": t.resultado_r,
        "_trade": t,
    }


def agora_utc() -> datetime:
    return datetime.now(UTC)
