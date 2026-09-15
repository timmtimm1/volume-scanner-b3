"""Z-scores de volume. Cobre os testes 1 a 5 da secao 10 do plano."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd
import pytest

from scanner.calendar import sessions_before
from scanner.metrics import (
    compute_zscores,
    market_volume_z,
    max_reachable_z,
    rolling_mad,
    to_wide,
    to_wide_many,
)

FIM = date(2026, 6, 30)


def pregoes(n: int) -> list[date]:
    return sessions_before(FIM, n, inclusive=True)


def serie(volumes: Sequence[float], ticker: str = "TEST3") -> pd.DataFrame:
    """Barras de um unico papel, um volume por pregao."""
    dias = pregoes(len(volumes))
    return pd.DataFrame({"ticker": ticker, "trade_date": dias, "volume_financial": list(volumes)})


def base_com_variacao(n: int, nivel: float = 1_000_000.0) -> list[float]:
    """Baseline com dispersao pequena mas nao nula: desvio zero daria NaN."""
    return [nivel * (1 + 0.1 * math.sin(i)) for i in range(n)]


# --- Secao 10, teste 1 -------------------------------------------------------


def test_baseline_nao_vaza_o_dia_corrente() -> None:
    volumes = [*base_com_variacao(40), 1_000_000_000.0]
    resultado = compute_zscores(serie(volumes), [30])
    ultimo = resultado.iloc[-1]

    assert ultimo["z_log"] > 10, "z travado abaixo de 10: o shift(1) sumiu"


def test_z_ultrapassa_o_teto_que_existiria_sem_shift() -> None:
    # Se o dia entrasse na propria janela, o maximo possivel seria (N-1)/sqrt(N).
    # Passar disso so e possivel com baseline deslocado. Nao e estilo, e aritmetica.
    volumes = [*base_com_variacao(40), 1_000_000_000.0]
    z = compute_zscores(serie(volumes), [30]).iloc[-1]["z_log"]

    assert max_reachable_z(30) == pytest.approx(5.2947, abs=1e-3)
    assert z > max_reachable_z(30)


@pytest.mark.parametrize(
    ("janela", "exato", "tabela_do_plano"),
    [(30, 5.294651, 5.29), (45, 6.559133, 6.56), (60, 7.616867, 7.62)],
)
def test_teto_sem_shift_bate_com_a_tabela_do_plano(
    janela: int, exato: float, tabela_do_plano: float
) -> None:
    assert max_reachable_z(janela) == pytest.approx(exato, abs=1e-6)
    # A tabela da secao 1 do plano traz o valor com duas casas.
    assert round(max_reachable_z(janela), 2) == tabela_do_plano


def test_baseline_usa_exatamente_os_n_pregoes_anteriores() -> None:
    # Gabarito calculado a mao: com 31 pregoes e janela 30, o z do ultimo dia usa
    # a media e o desvio dos 30 primeiros, e nada mais.
    volumes = [*base_com_variacao(30), 5_000_000.0]
    resultado = compute_zscores(serie(volumes), [30])

    anteriores = np.log(np.array(volumes[:30]))
    esperado = (math.log(5_000_000.0) - anteriores.mean()) / anteriores.std(ddof=1)

    assert len(resultado) == 1
    assert resultado.iloc[0]["z_log"] == pytest.approx(esperado)


# --- Secao 10, teste 2 -------------------------------------------------------


def test_serie_constante_nao_divide_por_zero() -> None:
    resultado = compute_zscores(serie([1_000_000.0] * 40), [30])
    assert resultado.empty  # desvio zero -> NaN -> linha descartada


def test_serie_constante_com_um_salto_final() -> None:
    # Desvio do baseline segue zero: nem o salto pode gerar z, so infinito.
    volumes = [*([1_000_000.0] * 35), 9_000_000.0]
    resultado = compute_zscores(serie(volumes), [30])
    assert resultado["z_log"].isna().sum() == 0
    assert (~np.isfinite(resultado["z_log"])).sum() == 0


# --- Secao 10, teste 3 -------------------------------------------------------


@pytest.mark.parametrize("n", [29, 30])
def test_historico_insuficiente_produz_zero_linhas(n: int) -> None:
    # min_periods=w: a janela precisa dos w pregoes anteriores completos.
    assert compute_zscores(serie(base_com_variacao(n)), [30]).empty


def test_primeiro_pregao_com_baseline_completo_produz_uma_linha() -> None:
    resultado = compute_zscores(serie(base_com_variacao(31)), [30])
    assert len(resultado) == 1


# --- Secao 10, teste 4 -------------------------------------------------------


def test_invariancia_de_escala() -> None:
    volumes = [*base_com_variacao(40), 800_000_000.0]
    original = compute_zscores(serie(volumes), [30, 60])
    escalado = compute_zscores(serie([v * 1000 for v in volumes]), [30, 60])

    pd.testing.assert_series_equal(original["z_log"], escalado["z_log"])
    pd.testing.assert_series_equal(original["rvol"], escalado["rvol"])
    pd.testing.assert_series_equal(original["z_robust"], escalado["z_robust"])


def test_z_log_e_z_raw_medem_coisas_diferentes() -> None:
    # Num spike grande sobre baseline lognormal, z_raw explode muito acima de
    # z_log: e por isso que "6 sigma" no valor bruto nao e comparavel entre
    # papeis, e o plano elege z_log como metrica primaria.
    volumes = [*base_com_variacao(40), 800_000_000.0]
    ultimo = compute_zscores(serie(volumes), [30]).iloc[-1]
    assert ultimo["z_raw"] > ultimo["z_log"] * 10


# --- Secao 10, teste 5 -------------------------------------------------------


def test_dia_sem_negocio_vira_nan_nunca_zero() -> None:
    volumes = base_com_variacao(40)
    volumes[10] = 0.0
    wide = to_wide(serie(volumes))
    convertido = wide.where(wide > 0)

    assert convertido.iloc[10, 0] != 0
    assert bool(pd.isna(convertido.iloc[10, 0]))


def test_buraco_na_janela_impede_o_z_daquele_dia() -> None:
    # Um zero no meio da janela nao pode virar "negociou zero" e puxar a media.
    volumes = base_com_variacao(40)
    com_buraco = list(volumes)
    com_buraco[20] = 0.0

    limpo = compute_zscores(serie(volumes), [30])
    furado = compute_zscores(serie(com_buraco), [30])
    assert len(furado) < len(limpo)


def test_ticker_ausente_no_pregao_nao_vira_volume_zero() -> None:
    dias = pregoes(35)
    barras = pd.concat(
        [
            pd.DataFrame(
                {"ticker": "AAAA3", "trade_date": dias, "volume_financial": base_com_variacao(35)}
            ),
            # BBBB4 so aparece em metade dos pregoes.
            pd.DataFrame(
                {
                    "ticker": "BBBB4",
                    "trade_date": dias[::2],
                    "volume_financial": base_com_variacao(len(dias[::2]), 2_000_000.0),
                }
            ),
        ],
        ignore_index=True,
    )
    wide = to_wide(barras)
    assert bool(wide["BBBB4"].isna().any())
    assert not bool((wide["BBBB4"] == 0).any())


# --- rvol, z_robust e mercado ------------------------------------------------


def test_rvol_e_o_multiplo_da_mediana_da_janela() -> None:
    volumes = [*base_com_variacao(30), 5_000_000.0]
    resultado = compute_zscores(serie(volumes), [30])
    esperado = 5_000_000.0 / float(np.median(volumes[:30]))
    assert resultado.iloc[0]["rvol"] == pytest.approx(esperado)


def test_z_robust_ignora_spike_anterior_no_baseline() -> None:
    # Um pico antigo infla media e desvio, mas nao a mediana nem o MAD.
    base = base_com_variacao(40)
    com_spike = list(base)
    com_spike[5] = 500_000_000.0
    alvo = 20_000_000.0

    limpo = compute_zscores(serie([*base, alvo]), [30]).iloc[-1]
    sujo = compute_zscores(serie([*com_spike, alvo]), [30]).iloc[-1]

    # O pico antigo ja saiu da janela de 30 do ultimo dia: nada muda.
    assert sujo["z_robust"] == pytest.approx(limpo["z_robust"])


def test_rolling_mad_bate_com_o_calculo_direto() -> None:
    valores = pd.DataFrame({"X": [1.0, 2.0, 3.0, 10.0, 5.0, 6.0]})
    mad = rolling_mad(valores, 3)
    janela = np.array([1.0, 2.0, 3.0])
    esperado = np.median(np.abs(janela - np.median(janela)))
    assert mad.iloc[2, 0] == pytest.approx(esperado)
    assert bool(pd.isna(mad.iloc[1, 0]))


def test_mkt_vol_z_usa_o_agregado_do_mercado() -> None:
    dias = pregoes(40)
    barras = pd.concat(
        [
            pd.DataFrame(
                {"ticker": t, "trade_date": dias, "volume_financial": base_com_variacao(40, nivel)}
            )
            for t, nivel in (("AAAA3", 1_000_000.0), ("BBBB4", 3_000_000.0))
        ],
        ignore_index=True,
    )
    z = market_volume_z(barras, 30)
    assert len(z) == 40
    assert bool(z.iloc[:30].isna().all())
    assert bool(z.iloc[30:].notna().all())


# --- contratos ---------------------------------------------------------------


def test_janela_invalida_falha_alto() -> None:
    with pytest.raises(ValueError, match="janela minima"):
        compute_zscores(serie(base_com_variacao(40)), [1])
    with pytest.raises(ValueError, match="ao menos uma janela"):
        compute_zscores(serie(base_com_variacao(40)), [])


def test_sem_barras_devolve_vazio() -> None:
    vazio = pd.DataFrame(columns=["ticker", "trade_date", "volume_financial"])
    assert compute_zscores(vazio, [30]).empty


def test_uma_linha_por_ticker_pregao_e_janela() -> None:
    resultado = compute_zscores(serie(base_com_variacao(40)), [30, 45])
    assert not bool(resultado.duplicated(["ticker", "trade_date", "window_size"]).any())
    assert set(resultado["window_size"].unique()) <= {30, 45}


# --- Equivalencia com as implementacoes anteriores ---------------------------
#
# rolling_mad e to_wide foram reescritas por desempenho. Estas referencias sao
# as versoes antigas, copiadas aqui como oraculo: a nova tem de dar o mesmo
# numero bit a bit, nao "aproximadamente".


def _rolling_mad_referencia(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    import warnings

    from numpy.lib.stride_tricks import sliding_window_view

    values = frame.to_numpy(dtype=float)
    out = np.full(values.shape, np.nan, dtype=float)
    if len(values) >= window:
        view = sliding_window_view(values, window, axis=0)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", "All-NaN slice encountered", RuntimeWarning)
            median = np.nanmedian(view, axis=-1)
            mad = np.nanmedian(np.abs(view - median[..., None]), axis=-1)
        complete = (~np.isnan(view)).sum(axis=-1) == window
        out[window - 1 :] = np.where(complete, mad, np.nan)
    return pd.DataFrame(out, index=frame.index, columns=frame.columns)


def _to_wide_referencia(bars: pd.DataFrame, value: str) -> pd.DataFrame:
    frame = bars.loc[:, ["ticker", "trade_date", value]].copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    wide = frame.pivot_table(
        index="trade_date", columns="ticker", values=value, aggfunc="last"
    ).sort_index()
    return wide.astype(float)


@pytest.mark.parametrize("window", [2, 3, 30, 45, 60])
def test_rolling_mad_igual_a_versao_anterior_bit_a_bit(window: int) -> None:
    rng = np.random.default_rng(42)
    valores = rng.lognormal(mean=13, sigma=1.5, size=(150, 12))
    # Buracos espalhados, papel que lista no meio e papel que sai antes do fim.
    valores[rng.random(valores.shape) < 0.05] = np.nan
    valores[:70, 3] = np.nan
    valores[110:, 7] = np.nan
    valores[:, 9] = np.nan
    frame = pd.DataFrame(np.log(valores)).shift(1)

    novo = rolling_mad(frame, window).to_numpy()
    antigo = _rolling_mad_referencia(frame, window).to_numpy()
    assert np.array_equal(novo, antigo, equal_nan=True)


def test_rolling_mad_com_historico_menor_que_a_janela() -> None:
    frame = pd.DataFrame({"X": [1.0, 2.0, 3.0]})
    assert bool(rolling_mad(frame, 5).isna().all().all())


def _barras_variadas() -> pd.DataFrame:
    dias = pregoes(8)
    linhas = []
    for i, dia in enumerate(dias):
        for ticker in ("AAAA3", "BBBB4", "CCCC11"):
            if ticker == "CCCC11" and i < 3:
                continue  # ainda nao listado
            linhas.append(
                {
                    "ticker": ticker,
                    "trade_date": dia,
                    "close": 10.0 + i,
                    "open": None if ticker == "BBBB4" else 9.5 + i,  # coluna toda nula
                    "trades_count": 100 + i,
                    "trades_censored": i == 5,
                }
            )
    return pd.DataFrame(linhas)


@pytest.mark.parametrize("coluna", ["close", "open", "trades_count", "trades_censored"])
def test_to_wide_many_igual_ao_pivot_table(coluna: str) -> None:
    barras = _barras_variadas()
    barras["trades_censored"] = barras["trades_censored"].astype(float)
    colunas = ["close", "open", "trades_count", "trades_censored"]

    pd.testing.assert_frame_equal(
        to_wide_many(barras, colunas)[coluna],
        _to_wide_referencia(barras, coluna),
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        to_wide(barras, coluna), _to_wide_referencia(barras, coluna), check_exact=True
    )


def test_to_wide_many_com_duplicata_fica_com_o_ultimo_nao_nulo() -> None:
    barras = _barras_variadas()
    dia = barras["trade_date"].iloc[0]
    repetida = pd.DataFrame(
        [
            {"ticker": "AAAA3", "trade_date": dia, "close": 99.0, "open": None},
            {"ticker": "AAAA3", "trade_date": dia, "close": None, "open": 1.0},
        ]
    )
    barras = pd.concat([barras, repetida], ignore_index=True)

    for coluna in ("close", "open"):
        pd.testing.assert_frame_equal(
            to_wide_many(barras, ["close", "open"])[coluna],
            _to_wide_referencia(barras, coluna),
            check_exact=True,
        )
