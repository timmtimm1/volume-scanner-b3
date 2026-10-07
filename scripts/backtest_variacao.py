"""Variacao de preco depois de um pico de volume, contra dias comuns.

Script de analise, fora do pipeline: nao grava no banco, nao entra no alerta e
nao muda o que o scanner detecta. Le o Postgres local (`daily_bars`,
`volume_metrics`, `events`) e responde uma pergunta so: depois de um evento de
6 sigma na janela de 30, o preco anda mais do que num dia comum do mesmo
universo? Nao diz para que lado, nem se da para operar.

Para cada evento no pregao t e cada horizonte N:

    var_abs        = |close(t+N) / close(t) - 1|
    amplitude      = (max high - min low entre t+1 e t+N) / close(t)
    *_norm         = as duas acima / desvio-padrao dos retornos diarios dos 60
                     pregoes anteriores a t (retornos de t-60 ate t-1)

Regras:

- So dados anteriores a t normalizam. O desvio usa `shift(1)`, como o z-score.
- Evento sem N pregoes a frente sai daquele horizonte (e so dele).
- Dias seguidos de evento no mesmo papel contam como um evento, no primeiro dia.
- `mkt_vol_z` alto (o mercado inteiro negociou muito) e separado.
- Controle: dias do mesmo universo com z_log < 2, sorteados com semente fixa.

Tres versoes:

    a_corte              so precos ate DATA_CORTE; t+N <= DATA_CORTE
    b_sem_corte          tudo o que esta no banco
    c_corte_sem_mkt_alto (a) sem os dias de mkt_vol_z alto
    d_corte_so_mkt_alto  (a) so com eles -- o que (c) deixou de fora

Uso:

    uv run python scripts/backtest_variacao.py
    uv run python scripts/backtest_variacao.py --data-corte 2026-10-02 --saida data/backtest
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from scanner.metrics import market_volume_z
from scanner.storage.models import SCHEMA

DATA_CORTE = date(2026, 10, 2)
HORIZONTES: tuple[int, ...] = (1, 5, 10, 20, 30)
METRICAS: tuple[str, ...] = ("var_abs", "amplitude", "var_abs_norm", "amplitude_norm")
SAIDA_PADRAO = Path("data/backtest_variacao")


@dataclass(frozen=True)
class Parametros:
    """Tudo que muda o resultado, num lugar so."""

    data_corte: date | None = DATA_CORTE
    horizontes: tuple[int, ...] = HORIZONTES
    janela_evento: int = 30
    limiar_evento: float = 6.0
    limiar_controle: float = 2.0
    janela_sigma: int = 60
    # Retornos validos exigidos dentro dos 60: papel que ficou dias sem negociar
    # tem desvio pouco confiavel, e o evento sai em vez de virar ruido.
    min_retornos_sigma: int = 50
    # Janela do mkt_vol_z: a mesma do `daily_features` (a maior do alerta).
    janela_mkt: int = 60
    limiar_mkt_alto: float = 2.0
    # Piso de volume do alerta (`alert.min_volume_brl`), aplicado tambem ao
    # controle: comparar evento de papel liquido com dia de papel morto distorce.
    min_volume_brl: float = 500_000.0
    n_controle: int = 20_000
    semente: int = 20261002


@dataclass(frozen=True)
class Dados:
    """O que vem do banco. `bars` ja vem cortada quando ha DATA_CORTE."""

    bars: pd.DataFrame  # ticker, trade_date, close, high, low, volume_financial
    z: pd.DataFrame  # ticker, trade_date, z_log (so a janela do evento)
    eventos_tabela: pd.DataFrame  # ticker, trade_date (a tabela `events`)


@dataclass(frozen=True)
class Matrizes:
    """Matrizes pregao x ticker sobre o calendario de pregoes do banco."""

    calendario: pd.DatetimeIndex
    tickers: pd.Index
    close: np.ndarray
    sigma: np.ndarray
    mkt_vol_z: np.ndarray
    # Por horizonte: max(high) e min(low) de t+1 ate t+N, ja alinhados em t.
    max_high: dict[int, np.ndarray]
    min_low: dict[int, np.ndarray]


# --------------------------------------------------------------------------- banco


def carregar(engine: Engine, janela_evento: int, data_corte: date | None) -> Dados:
    """Le as tres tabelas. Com corte, nada posterior a ele sai do banco."""
    filtro = "AND trade_date <= :corte" if data_corte is not None else ""
    params: dict[str, int | date] = {"janela": janela_evento}
    if data_corte is not None:
        params["corte"] = data_corte

    with engine.connect() as conn:
        bars = pd.read_sql(
            text(
                f"SELECT ticker, trade_date, close, high, low, volume_financial "
                f"FROM {SCHEMA}.daily_bars WHERE true {filtro}"
            ),
            conn,
            params=params,
        )
        z = pd.read_sql(
            text(
                f"SELECT ticker, trade_date, z_log FROM {SCHEMA}.volume_metrics "
                f"WHERE window_size = :janela AND z_log IS NOT NULL {filtro}"
            ),
            conn,
            params=params,
        )
        eventos = pd.read_sql(
            text(f"SELECT ticker, trade_date FROM {SCHEMA}.events WHERE true {filtro}"),
            conn,
            params=params,
        )

    for frame in (bars, z, eventos):
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    for coluna in ("close", "high", "low", "volume_financial"):
        bars[coluna] = bars[coluna].astype(float)
    z["z_log"] = z["z_log"].astype(float)
    return Dados(bars=bars, z=z, eventos_tabela=eventos)


# --------------------------------------------------------------------------- calculo


def montar_matrizes(bars: pd.DataFrame, p: Parametros) -> Matrizes:
    """Desvio, mkt_vol_z e extremos futuros, tudo vetorizado sobre a matriz."""
    largo = bars.pivot(index="trade_date", columns="ticker").sort_index()
    close = largo["close"]
    # Barra sem high/low (raro no COTAHIST) usa o fechamento: e o unico preco do dia.
    high = largo["high"].fillna(close)
    low = largo["low"].fillna(close)

    # Retorno do dia: NaN se o papel nao negociou na vespera (sem preencher buraco).
    retorno = close / close.shift(1) - 1.0
    # shift(1): o desvio que normaliza t usa os retornos de t-60 ate t-1.
    sigma = retorno.shift(1).rolling(p.janela_sigma, min_periods=p.min_retornos_sigma).std()

    mkt = market_volume_z(bars, p.janela_mkt).reindex(close.index)

    max_high: dict[int, np.ndarray] = {}
    min_low: dict[int, np.ndarray] = {}
    for n in p.horizontes:
        # Rolling ao contrario cobre t..t+N-1; o shift(-1) leva para t+1..t+N.
        max_high[n] = high[::-1].rolling(n, min_periods=1).max()[::-1].shift(-1).to_numpy()
        min_low[n] = low[::-1].rolling(n, min_periods=1).min()[::-1].shift(-1).to_numpy()

    return Matrizes(
        calendario=pd.DatetimeIndex(close.index),
        tickers=close.columns,
        close=close.to_numpy(),
        sigma=sigma.to_numpy(),
        mkt_vol_z=mkt.to_numpy(dtype=float),
        max_high=max_high,
        min_low=min_low,
    )


def _com_volume(pontos: pd.DataFrame, bars: pd.DataFrame, piso: float) -> pd.DataFrame:
    volume = bars.loc[:, ["ticker", "trade_date", "volume_financial"]]
    juntos = pontos.merge(volume, on=["ticker", "trade_date"], how="inner")
    return juntos[juntos["volume_financial"] >= piso].drop(columns="volume_financial")


def selecionar_eventos(dados: Dados, m: Matrizes, p: Parametros) -> pd.DataFrame:
    """Um evento por bloco de pregoes seguidos do mesmo papel, no primeiro dia.

    Devolve ticker, trade_date, z_log e `dias_no_bloco`.
    """
    acima = dados.z[dados.z["z_log"] >= p.limiar_evento].loc[:, ["ticker", "trade_date", "z_log"]]
    acima = _com_volume(acima, dados.bars, p.min_volume_brl)
    if acima.empty:
        return acima.assign(dias_no_bloco=pd.Series(dtype="int64"))

    acima = acima.assign(pos=m.calendario.get_indexer(pd.DatetimeIndex(acima["trade_date"])))
    acima = acima.sort_values(["ticker", "pos"]).reset_index(drop=True)
    # Novo bloco quando muda o papel ou ha pelo menos um pregao sem evento no meio.
    novo = (acima["ticker"] != acima["ticker"].shift(1)) | (acima["pos"].diff() != 1)
    acima["bloco"] = novo.cumsum()
    tamanho = acima.groupby("bloco")["pos"].transform("size")
    primeiros = acima[novo].assign(dias_no_bloco=tamanho[novo].astype("int64"))
    return primeiros.loc[:, ["ticker", "trade_date", "z_log", "dias_no_bloco"]].reset_index(
        drop=True
    )


def amostrar_controle(dados: Dados, p: Parametros) -> pd.DataFrame:
    """Dias comuns (z_log < limiar) do mesmo universo, sorteados com semente fixa."""
    base = dados.z[dados.z["z_log"] < p.limiar_controle].loc[:, ["ticker", "trade_date", "z_log"]]
    base = _com_volume(base, dados.bars, p.min_volume_brl)
    # Ordena antes de sortear: o sorteio nao pode depender da ordem do SELECT.
    base = base.sort_values(["trade_date", "ticker"]).reset_index(drop=True)
    if len(base) <= p.n_controle:
        return base.assign(dias_no_bloco=1)
    rng = np.random.default_rng(p.semente)
    escolhidos = np.sort(rng.choice(len(base), size=p.n_controle, replace=False))
    return base.iloc[escolhidos].reset_index(drop=True).assign(dias_no_bloco=1)


def medir(pontos: pd.DataFrame, m: Matrizes, p: Parametros) -> pd.DataFrame:
    """Uma linha por (ponto, horizonte) que tem N pregoes a frente e desvio valido."""
    colunas = [
        "ticker", "trade_date", "z_log", "dias_no_bloco", "mkt_vol_z", "sigma60",
        "N", "data_fim", *METRICAS,
    ]  # fmt: skip
    if pontos.empty:
        return pd.DataFrame(columns=colunas)

    i = m.calendario.get_indexer(pd.DatetimeIndex(pontos["trade_date"]))
    j = m.tickers.get_indexer(pd.Index(pontos["ticker"]))
    dentro = (i >= 0) & (j >= 0)
    pontos, i, j = pontos[dentro].reset_index(drop=True), i[dentro], j[dentro]

    c0 = m.close[i, j]
    sigma = m.sigma[i, j]
    base_ok = np.isfinite(c0) & (c0 > 0) & np.isfinite(sigma) & (sigma > 0)

    total = len(m.calendario)
    partes = []
    for n in p.horizontes:
        fim = i + n
        tem_fim = fim < total
        fim_seguro = np.where(tem_fim, fim, 0)
        data_fim = m.calendario[fim_seguro]
        if p.data_corte is not None:
            tem_fim &= np.asarray(data_fim <= pd.Timestamp(p.data_corte))

        cn = m.close[fim_seguro, j]
        hi = m.max_high[n][i, j]
        lo = m.min_low[n][i, j]
        ok = base_ok & tem_fim & np.isfinite(cn) & np.isfinite(hi) & np.isfinite(lo)

        var_abs = np.abs(cn / c0 - 1.0)
        amplitude = (hi - lo) / c0
        parte = pontos.loc[ok, ["ticker", "trade_date", "z_log", "dias_no_bloco"]].copy()
        parte["mkt_vol_z"] = m.mkt_vol_z[i[ok]]
        parte["sigma60"] = sigma[ok]
        parte["N"] = n
        parte["data_fim"] = data_fim[ok]
        parte["var_abs"] = var_abs[ok]
        parte["amplitude"] = amplitude[ok]
        parte["var_abs_norm"] = var_abs[ok] / sigma[ok]
        parte["amplitude_norm"] = amplitude[ok] / sigma[ok]
        partes.append(parte)
    return pd.concat(partes, ignore_index=True).loc[:, colunas]


def observar(dados: Dados, p: Parametros) -> pd.DataFrame:
    """Eventos e controles medidos, com a coluna `grupo` e a marca `mkt_alto`."""
    m = montar_matrizes(dados.bars, p)
    eventos = medir(selecionar_eventos(dados, m, p), m, p).assign(grupo="evento")
    controle = medir(amostrar_controle(dados, p), m, p).assign(grupo="controle")
    obs = pd.concat([eventos, controle], ignore_index=True)
    # Sem mkt_vol_z (inicio da serie) nao da para dizer que o mercado estava
    # calmo: fica marcado como alto, e a versao (c) o exclui.
    obs["mkt_alto"] = ~(obs["mkt_vol_z"] < p.limiar_mkt_alto)
    return obs


def resumir(obs: pd.DataFrame, horizontes: Sequence[int]) -> pd.DataFrame:
    """Tabela por horizonte e metrica: n, mediana, p25, p75, p90 e razoes."""
    linhas = []
    for n in horizontes:
        for metrica in METRICAS:
            linha: dict[str, object] = {"N": n, "metrica": metrica}
            for grupo in ("evento", "controle"):
                filtro = (obs["N"] == n) & (obs["grupo"] == grupo)
                valores = obs.loc[filtro, metrica].to_numpy(dtype=float)
                linha[f"n_{grupo}"] = len(valores)
                for nome, q in (("mediana", 0.5), ("p25", 0.25), ("p75", 0.75), ("p90", 0.9)):
                    linha[f"{nome}_{grupo}"] = (
                        float(np.quantile(valores, q)) if len(valores) else np.nan
                    )
            for nome in ("mediana", "p75", "p90"):
                controle = float(linha[f"{nome}_controle"])  # type: ignore[arg-type]
                evento = float(linha[f"{nome}_evento"])  # type: ignore[arg-type]
                linha[f"razao_{nome}"] = evento / controle if controle > 0 else np.nan
            linhas.append(linha)
    return pd.DataFrame(linhas)


def versoes(dados_corte: Dados, dados_tudo: Dados, p: Parametros) -> dict[str, pd.DataFrame]:
    """As quatro versoes de observacoes. (a), (c) e (d) saem da mesma leitura."""
    obs_a = observar(dados_corte, p)
    obs_b = observar(dados_tudo, replace(p, data_corte=None))
    return {
        "a_corte": obs_a,
        "b_sem_corte": obs_b,
        "c_corte_sem_mkt_alto": obs_a[~obs_a["mkt_alto"]].reset_index(drop=True),
        "d_corte_so_mkt_alto": obs_a[obs_a["mkt_alto"]].reset_index(drop=True),
    }


# --------------------------------------------------------------------------- saida


def contagens(por_versao: dict[str, pd.DataFrame], horizontes: Sequence[int]) -> pd.DataFrame:
    """n de eventos e de controles por versao e horizonte."""
    linhas = []
    for versao, obs in por_versao.items():
        for grupo in ("evento", "controle"):
            por_n = obs[obs["grupo"] == grupo].groupby("N").size()
            linhas.append(
                {"versao": versao, "grupo": grupo}
                | {f"N={n}": int(por_n.get(n, 0)) for n in horizontes}
            )
    return pd.DataFrame(linhas)


def grafico(resumo: pd.DataFrame, destino: Path, horizontes: Sequence[int]) -> None:
    """Linha de cima: evento x controle na versao (a). Linha de baixo: razoes."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    azul, laranja = "#2a78d6", "#eb6834"
    cores_versao = {
        "a_corte": "#2a78d6",
        "b_sem_corte": "#eb6834",
        "c_corte_sem_mkt_alto": "#1baf7a",
        "d_corte_so_mkt_alto": "#eda100",
    }
    titulos = {
        "var_abs": "|variação| até t+N",
        "amplitude": "amplitude t+1..t+N",
        "var_abs_norm": "|variação| / sigma60",
        "amplitude_norm": "amplitude / sigma60",
    }
    fig, eixos = plt.subplots(2, 4, figsize=(18, 8.5), constrained_layout=True)
    a = resumo[resumo["versao"] == "a_corte"]
    for col, metrica in enumerate(METRICAS):
        ax = eixos[0, col]
        dados = a[a["metrica"] == metrica].sort_values("N")
        for grupo, cor in (("evento", azul), ("controle", laranja)):
            ax.fill_between(
                dados["N"], dados[f"p25_{grupo}"], dados[f"p75_{grupo}"], color=cor, alpha=0.15
            )
            ax.plot(dados["N"], dados[f"mediana_{grupo}"], color=cor, lw=2, marker="o", ms=5,
                    label=f"{grupo} (mediana, faixa p25-p75)")  # fmt: skip
        ax.set_title(titulos[metrica], fontsize=11)
        ax.set_xticks(list(horizontes))
        ax.grid(alpha=0.25)
        if metrica in ("var_abs", "amplitude"):
            ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        if col == 0:
            ax.legend(fontsize=8, frameon=False)
            ax.set_ylabel("versão (a) com corte")

        ax = eixos[1, col]
        for versao, cor in cores_versao.items():
            linha = resumo[(resumo["versao"] == versao) & (resumo["metrica"] == metrica)]
            linha = linha.sort_values("N")
            ax.plot(linha["N"], linha["razao_mediana"], color=cor, lw=2, marker="o", ms=5,
                    label=versao)  # fmt: skip
        ax.axhline(1.0, color="#52514e", lw=1, ls="--")
        ax.set_xticks(list(horizontes))
        ax.set_xlabel("horizonte N (pregões)")
        ax.grid(alpha=0.25)
        if col == 0:
            ax.set_ylabel("razão das medianas evento / controle")
            ax.legend(fontsize=8, frameon=False)
    fig.suptitle("Depois de um z_log ≥ 6 (janela 30): quanto o preço anda, contra dias comuns")
    fig.savefig(destino, dpi=130)
    plt.close(fig)


def _args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--data-corte", type=date.fromisoformat, default=DATA_CORTE)
    ap.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    ap.add_argument("--n-controle", type=int, default=Parametros.n_controle)
    ap.add_argument("--semente", type=int, default=Parametros.semente)
    ap.add_argument("--mkt-alto", type=float, default=Parametros.limiar_mkt_alto,
                    help="mkt_vol_z a partir do qual o dia conta como 'mercado alto'")  # fmt: skip
    ap.add_argument("--database-url", default=None, help="Padrao: SCANNER_DATABASE_URL")
    return ap.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    from scanner.config import load_config
    from scanner.storage.engine import build_engine

    args = _args(argv)
    p = Parametros(
        data_corte=args.data_corte,
        n_controle=args.n_controle,
        semente=args.semente,
        limiar_mkt_alto=args.mkt_alto,
        min_volume_brl=float(load_config().alert.min_volume_brl),
    )
    engine = build_engine(args.database_url)
    dados_corte = carregar(engine, p.janela_evento, p.data_corte)
    dados_tudo = carregar(engine, p.janela_evento, None)

    por_versao = versoes(dados_corte, dados_tudo, p)
    resumo = pd.concat(
        [resumir(obs, p.horizontes).assign(versao=v) for v, obs in por_versao.items()],
        ignore_index=True,
    )
    resumo = resumo.loc[:, ["versao", *[c for c in resumo.columns if c != "versao"]]]

    args.saida.mkdir(parents=True, exist_ok=True)
    resumo.to_csv(args.saida / "resumo.csv", index=False, float_format="%.6g")
    observacoes = pd.concat(
        [por_versao[v].assign(versao=v) for v in ("a_corte", "b_sem_corte")], ignore_index=True
    )
    observacoes.to_csv(args.saida / "observacoes.csv", index=False, float_format="%.6g")
    grafico(resumo, args.saida / "grafico.png", p.horizontes)

    ultimo = dados_tudo.bars["trade_date"].max()
    print(f"Banco: {dados_tudo.bars['trade_date'].min():%Y-%m-%d} a {ultimo:%Y-%m-%d}, "
          f"{dados_tudo.bars['ticker'].nunique()} papeis")  # fmt: skip
    print(f"DATA_CORTE = {p.data_corte}  |  mkt_vol_z alto >= {p.limiar_mkt_alto}  |  "
          f"semente {p.semente}, {p.n_controle} controles sorteados")  # fmt: skip
    print(f"Linhas na tabela `events` (ate o corte): {len(dados_corte.eventos_tabela)}")
    print("\nn por versao e horizonte:")
    print(contagens(por_versao, p.horizontes).to_string(index=False))
    for versao in por_versao:
        print(f"\n== {versao} ==")
        tabela = resumo[resumo["versao"] == versao].drop(columns="versao")
        print(tabela.to_string(index=False, float_format=lambda x: f"{x:.4g}"))
    print(f"\nGravado em {args.saida}/: resumo.csv, observacoes.csv, grafico.png")


if __name__ == "__main__":
    main()
