"""Contexto do evento. Cobre o teste 8 da secao 10 do plano."""

from __future__ import annotations

import math
from datetime import date

import pandas as pd
import pytest

from scanner.calendar import sessions_before
from scanner.features import compute_features
from scanner.ingest.cotahist import TRADES_SENTINEL
from scanner.metrics import compute_zscores

FIM = date(2026, 6, 30)
JANELA = 30


def barras(
    n: int,
    ticker: str = "TEST3",
    *,
    volume: float = 1_000_000.0,
    trades: int = 500,
    censored: bool = False,
) -> pd.DataFrame:
    """Barras planas: preco 10,00 e volume constante, salvo ajuste no teste."""
    dias = sessions_before(FIM, n, inclusive=True)
    return pd.DataFrame(
        {
            "ticker": ticker,
            "trade_date": dias,
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.0,
            "avg_price": 10.0,
            "volume_financial": [volume * (1 + 0.1 * math.sin(i)) for i in range(n)],
            "trades_count": trades,
            "trades_censored": censored,
        }
    )


def ultima(frame: pd.DataFrame) -> pd.Series:
    return frame.sort_values("trade_date").iloc[-1]


# --- Secao 10, teste 8 -------------------------------------------------------


def test_ticket_censurado_nao_gera_avg_ticket() -> None:
    # TOTNEG saturado em 99999 e teto de campo, nao contagem real: dividir por ele
    # produziria um ticket medio inventado.
    b = barras(40, trades=TRADES_SENTINEL, censored=True)
    f = compute_features(b, JANELA)

    assert bool(f["avg_ticket"].isna().all())
    assert bool(f["ticket_z"].isna().all())


def test_ticket_normal_gera_avg_ticket() -> None:
    b = barras(40, volume=1_000_000.0, trades=500)
    f = ultima(compute_features(b, JANELA))
    esperado = float(ultima(b)["volume_financial"]) / 500
    assert f["avg_ticket"] == pytest.approx(esperado)


def test_censura_afeta_so_o_dia_censurado() -> None:
    b = barras(40)
    b.loc[b.index[-1], ["trades_count", "trades_censored"]] = [TRADES_SENTINEL, True]
    f = compute_features(b, JANELA).sort_values("trade_date")

    assert bool(pd.isna(f.iloc[-1]["avg_ticket"]))
    assert bool(f.iloc[-2:-1]["avg_ticket"].notna().all())


def test_totneg_zero_tambem_nao_gera_ticket() -> None:
    b = barras(40, trades=0)
    assert bool(compute_features(b, JANELA)["avg_ticket"].isna().all())


# --- Features de preco -------------------------------------------------------


def test_ret_day_e_gap_usam_o_fechamento_da_vespera() -> None:
    b = barras(5)
    b.loc[b.index[-1], ["open", "close"]] = [10.5, 12.0]
    f = ultima(compute_features(b, JANELA))

    assert f["ret_day"] == pytest.approx(12.0 / 10.0 - 1)
    assert f["gap"] == pytest.approx(10.5 / 10.0 - 1)


def test_clv_posiciona_o_fechamento_no_range() -> None:
    b = barras(3)
    # Fecha no topo, no fundo e no meio do range 9-11.
    for fechamento, esperado in ((11.0, 1.0), (9.0, 0.0), (10.0, 0.5)):
        b.loc[b.index[-1], "close"] = fechamento
        assert ultima(compute_features(b, JANELA))["clv"] == pytest.approx(esperado)


def test_clv_e_nan_quando_o_range_e_zero() -> None:
    b = barras(3)
    b.loc[b.index[-1], ["high", "low"]] = [10.0, 10.0]
    assert bool(pd.isna(ultima(compute_features(b, JANELA))["clv"]))


def test_range_norm_e_a_amplitude_sobre_o_preco_medio() -> None:
    f = ultima(compute_features(barras(3), JANELA))
    assert f["range_norm"] == pytest.approx((11.0 - 9.0) / 10.0)


def test_ret_prior_20_para_na_vespera() -> None:
    # A feature diz de onde o papel veio; o dia do evento nao pode entrar nela.
    b = barras(40)
    b["close"] = [10.0] * 39 + [99.0]
    f = ultima(compute_features(b, JANELA))

    assert f["ret_prior_20"] == pytest.approx(0.0)
    assert f["ret_day"] == pytest.approx(99.0 / 10.0 - 1)


def test_pos252_exige_um_ano_de_historico() -> None:
    curto = compute_features(barras(100), JANELA)
    assert bool(curto["pos252"].isna().all())


def test_pos252_localiza_o_preco_na_faixa_do_ano() -> None:
    b = barras(260)
    b["close"] = [10.0 + (i % 20) for i in range(260)]  # oscila entre 10 e 29
    b.loc[b.index[-1], "close"] = 29.0
    f = ultima(compute_features(b, JANELA))
    assert f["pos252"] == pytest.approx(1.0)


# --- Mercado -----------------------------------------------------------------


def test_mkt_vol_z_e_o_mesmo_para_todos_os_papeis_do_dia() -> None:
    b = pd.concat([barras(40, "AAAA3"), barras(40, "BBBB4", volume=5_000_000.0)])
    f = compute_features(b, JANELA)
    por_dia = f.dropna(subset=["mkt_vol_z"]).groupby("trade_date")["mkt_vol_z"].nunique()
    assert bool((por_dia == 1).all())


def test_z_excess_e_o_z_do_papel_menos_o_do_mercado() -> None:
    b = pd.concat([barras(40, "AAAA3"), barras(40, "BBBB4", volume=5_000_000.0)])
    b.loc[(b["ticker"] == "AAAA3") & (b["trade_date"] == FIM), "volume_financial"] = 5e8

    z = compute_zscores(b, [JANELA])
    f = compute_features(b, JANELA, z)

    linha = f[(f["ticker"] == "AAAA3") & (f["trade_date"] == pd.Timestamp(FIM))].iloc[0]
    z_papel = z[(z["ticker"] == "AAAA3") & (z["trade_date"] == pd.Timestamp(FIM))].iloc[0]["z_log"]

    assert linha["z_excess"] == pytest.approx(z_papel - linha["mkt_vol_z"])
    # O evento e do papel, nao do mercado: a anomalia liquida sobra alta.
    assert linha["z_excess"] > 1


def test_sem_metricas_o_z_excess_fica_nan() -> None:
    f = compute_features(barras(40), JANELA)
    assert bool(f["z_excess"].isna().all())


# --- Contratos ---------------------------------------------------------------


def test_sem_barras_devolve_vazio() -> None:
    vazio = pd.DataFrame(
        columns=[
            "ticker",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "avg_price",
            "volume_financial",
            "trades_count",
            "trades_censored",
        ]
    )
    assert compute_features(vazio, JANELA).empty


def test_uma_linha_por_ticker_e_pregao() -> None:
    b = pd.concat([barras(40, "AAAA3"), barras(40, "BBBB4")])
    f = compute_features(b, JANELA)
    assert not bool(f.duplicated(["ticker", "trade_date"]).any())
    assert len(f) == 80
