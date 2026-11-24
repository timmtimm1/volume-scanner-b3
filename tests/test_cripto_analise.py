"""Cada cripto contra o Bitcoin: retornos por mes e ano, beta, correlacao e janela movel."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from scanner.cripto.analise import (
    ANO_TOTAL,
    COLUNAS_ANUAIS,
    COLUNAS_MENSAIS,
    COLUNAS_MOVEIS,
    JANELA_MOVEL,
    PASSO_MOVEL,
    beta_por_ano,
    calcular,
    janela_movel,
    periodo_todo,
    resumo,
    retornos_por_periodo,
)

DIAS = pd.date_range("2022-12-01", "2024-01-31", freq="D")


def _btc(seed: int = 1) -> pd.Series:
    """Um BTC com retornos diarios sorteados (o mesmo a cada chamada)."""
    rng = np.random.default_rng(seed)
    return pd.Series(100.0 * np.cumprod(1 + rng.normal(0.001, 0.03, len(DIAS))), index=DIAS)


def _matriz(**moedas: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(moedas, index=DIAS).astype("float64")


def _linha(frame: pd.DataFrame, moeda: str, coluna: str, valor: object) -> pd.Series:
    achadas = frame[(frame["moeda"] == moeda) & (frame[coluna] == valor)]
    assert len(achadas) == 1, achadas
    return achadas.iloc[0]


def _no(serie: pd.Series, dia: str) -> float:
    return float(serie[pd.Timestamp(dia)])


def test_retorno_do_ano_vai_do_ultimo_fechamento_anterior_ao_ultimo_do_ano() -> None:
    btc = _btc()
    eth = btc * np.linspace(1.0, 1.5, len(DIAS))
    anos = retornos_por_periodo(_matriz(BTC=btc, ETH=eth), "Y")

    ano = _linha(anos, "ETH", "periodo", date(2023, 1, 1))
    assert ano["inicio"] == date(2022, 12, 31)
    assert ano["fim"] == date(2023, 12, 31)
    assert not ano["parcial"]
    esperado = _no(eth, "2023-12-31") / _no(eth, "2022-12-31") - 1
    esperado_btc = _no(btc, "2023-12-31") / _no(btc, "2022-12-31") - 1
    assert ano["retorno"] == pytest.approx(esperado)
    assert ano["retorno_btc"] == pytest.approx(esperado_btc)
    assert ano["relativo"] == pytest.approx((1 + esperado) / (1 + esperado_btc) - 1)

    o_btc = _linha(anos, "BTC", "periodo", date(2023, 1, 1))
    assert o_btc["relativo"] == pytest.approx(0.0, abs=1e-12)


def test_mes_comeca_no_fechamento_do_ultimo_dia_do_mes_anterior() -> None:
    btc = _btc()
    meses = retornos_por_periodo(_matriz(BTC=btc), "M")
    marco = _linha(meses, "BTC", "periodo", date(2023, 3, 1))
    assert (marco["inicio"], marco["fim"]) == (date(2023, 2, 28), date(2023, 3, 31))
    assert marco["retorno"] == pytest.approx(_no(btc, "2023-03-31") / _no(btc, "2023-02-28") - 1)


def test_moeda_que_estreia_no_meio_do_ano_e_comparada_com_o_btc_desde_a_estreia() -> None:
    btc = _btc()
    nova = (btc * 2).where(DIAS >= "2023-03-10")
    ano = _linha(
        retornos_por_periodo(_matriz(BTC=btc, NOVA=nova), "Y"), "NOVA", "periodo", date(2023, 1, 1)
    )
    assert ano["inicio"] == date(2023, 3, 10)
    assert ano["parcial"]
    assert ano["retorno_btc"] == pytest.approx(_no(btc, "2023-12-31") / _no(btc, "2023-03-10") - 1)
    # Andou igual ao BTC desde a estreia: nem mais forte nem mais fraca.
    assert ano["relativo"] == pytest.approx(0.0, abs=1e-12)


def test_moeda_deslistada_para_no_ultimo_candle_e_o_btc_tambem() -> None:
    btc = _btc()
    morta = (btc * 3).where(DIAS <= "2023-08-15")
    ano = _linha(
        retornos_por_periodo(_matriz(BTC=btc, MORTA=morta), "Y"),
        "MORTA",
        "periodo",
        date(2023, 1, 1),
    )
    assert ano["fim"] == date(2023, 8, 15)
    assert ano["parcial"]
    assert ano["retorno_btc"] == pytest.approx(_no(btc, "2023-08-15") / _no(btc, "2022-12-31") - 1)


def test_faltar_um_dia_no_fim_do_ano_nao_torna_o_ano_parcial() -> None:
    btc = _btc()
    furada = (btc * 1.0).where(~DIAS.isin(pd.to_datetime(["2023-12-30", "2023-12-31"])))
    ano = _linha(
        retornos_por_periodo(_matriz(BTC=btc, F=furada), "Y"), "F", "periodo", date(2023, 1, 1)
    )
    assert ano["fim"] == date(2023, 12, 29)
    assert not ano["parcial"]


def test_buraco_de_mais_de_30_dias_recomeca_a_serie() -> None:
    btc = _btc()
    # Para em 31/03 e volta em 01/07 cotada 10 vezes mais alta.
    parada = (btc * 1.0).where((DIAS <= "2023-03-31") | (DIAS >= "2023-07-01"))
    parada[DIAS >= "2023-07-01"] *= 10
    fech = _matriz(BTC=btc, P=parada)
    ano = _linha(retornos_por_periodo(fech, "Y"), "P", "periodo", date(2023, 1, 1))
    assert ano["inicio"] == date(2023, 7, 1)
    assert ano["parcial"]
    assert ano["relativo"] == pytest.approx(0.0, abs=1e-12)
    meses = retornos_por_periodo(fech, "M")
    assert set(meses.loc[meses["moeda"] == "P", "periodo"]) >= {date(2023, 3, 1), date(2023, 7, 1)}
    assert not (meses["moeda"].eq("P") & meses["periodo"].isin([date(2023, 4, 1)])).any()
    julho = _linha(meses, "P", "periodo", date(2023, 7, 1))
    assert julho["inicio"] == date(2023, 7, 1)
    assert periodo_todo(fech).set_index("moeda").loc["P", "inicio"] == date(2023, 7, 1)


def test_troca_de_escala_depois_de_uma_pausa_recomeca_a_serie() -> None:
    btc = _btc()
    # Quatro dias parada e volta valendo 1.000 vezes mais (redenominacao).
    troca = (btc * 1.0).where((DIAS < "2023-05-10") | (DIAS > "2023-05-13"))
    troca[DIAS > "2023-05-13"] *= 1000
    ano = _linha(
        retornos_por_periodo(_matriz(BTC=btc, T=troca), "Y"), "T", "periodo", date(2023, 1, 1)
    )
    assert ano["inicio"] == date(2023, 5, 14)
    assert ano["retorno"] < 100  # nada de +99.900%


def test_queda_de_um_dia_para_o_outro_sem_pausa_conta_inteira() -> None:
    btc = _btc()
    luna = pd.Series(80.0, index=DIAS)
    luna[DIAS >= "2023-05-12"] = 0.08  # -99,9% de um dia para o outro, sem pausa
    ano = _linha(
        retornos_por_periodo(_matriz(BTC=btc, LUNA=luna), "Y"), "LUNA", "periodo", date(2023, 1, 1)
    )
    assert ano["inicio"] == date(2022, 12, 31)
    assert ano["retorno"] == pytest.approx(-0.999)


def test_beta_2_e_correlacao_1_para_moeda_que_anda_o_dobro_do_btc() -> None:
    btc = _btc()
    ret_btc = btc.pct_change().fillna(0)
    dobro = 50.0 * np.cumprod(1 + 2 * ret_btc)
    contra = 50.0 * np.cumprod(1 - ret_btc)
    anos = beta_por_ano(_matriz(BTC=btc, DOBRO=dobro, CONTRA=contra))
    l2023 = anos[anos["ano"] == 2023].set_index("moeda")
    assert l2023.loc["DOBRO", "beta"] == pytest.approx(2.0)
    assert l2023.loc["DOBRO", "correlacao"] == pytest.approx(1.0)
    assert l2023.loc["CONTRA", "beta"] == pytest.approx(-1.0)
    assert l2023.loc["CONTRA", "correlacao"] == pytest.approx(-1.0)
    assert l2023.loc["BTC", "beta"] == pytest.approx(1.0)


def test_beta_confere_com_a_covariancia_do_numpy() -> None:
    btc = _btc()
    rng = np.random.default_rng(7)
    ret = btc.pct_change()
    ruido = pd.Series(1.3 * ret.to_numpy() + rng.normal(0, 0.02, len(DIAS)), index=DIAS).fillna(0)
    moeda = 10.0 * np.cumprod(1 + ruido)
    l2023 = beta_por_ano(_matriz(BTC=btc, X=moeda)).query("ano == 2023").set_index("moeda")
    x = moeda.pct_change()[DIAS.year == 2023].to_numpy()
    y = ret[DIAS.year == 2023].to_numpy()
    cov = np.cov(x, y)
    assert l2023.loc["X", "beta"] == pytest.approx(cov[0, 1] / cov[1, 1])
    assert l2023.loc["X", "correlacao"] == pytest.approx(np.corrcoef(x, y)[0, 1])
    assert l2023.loc["X", "dias"] == 365


def test_beta_sem_60_dias_de_retorno_fica_vazio() -> None:
    btc = _btc()
    curta = (btc * 1.0).where(DIAS >= "2023-11-15")  # 47 dias em 2023
    l2023 = beta_por_ano(_matriz(BTC=btc, C=curta)).query("ano == 2023").set_index("moeda")
    assert np.isnan(l2023.loc["C", "beta"])
    assert np.isnan(l2023.loc["C", "correlacao"])


def test_janela_movel_de_7_em_7_dias_ate_o_mais_recente() -> None:
    btc = _btc()
    dobro = 50.0 * np.cumprod(1 + 2 * btc.pct_change().fillna(0))
    movel = janela_movel(_matriz(BTC=btc, DOBRO=dobro))
    pontos = movel[movel["moeda"] == "DOBRO"]
    assert pontos["dia"].iloc[-1] == DIAS[-1].date()
    passos = pd.to_datetime(pontos["dia"]).diff().dropna().dt.days
    assert set(passos) == {PASSO_MOVEL}
    assert pontos["beta"].to_numpy() == pytest.approx(2.0)
    assert pontos["correlacao"].to_numpy() == pytest.approx(1.0)
    # Nenhum ponto com menos de 60 retornos na janela: o primeiro vem depois disso.
    assert (pontos["dias"] >= 60).all()
    assert pontos["dias"].max() == JANELA_MOVEL


def test_periodo_todo_e_a_linha_ano_zero_da_tabela_anual() -> None:
    btc = _btc()
    eth = btc * np.linspace(1.0, 0.5, len(DIAS))
    vol = _matriz(BTC=pd.Series(1e9, index=DIAS), ETH=pd.Series(1e8, index=DIAS))
    analise = calcular(_matriz(BTC=btc, ETH=eth), vol)
    assert list(analise.anual.columns) == list(COLUNAS_ANUAIS)
    assert list(analise.mensal.columns) == list(COLUNAS_MENSAIS)
    assert list(analise.movel.columns) == list(COLUNAS_MOVEIS)
    total = _linha(analise.anual, "ETH", "ano", ANO_TOTAL)
    assert (total["inicio"], total["fim"]) == (DIAS[0].date(), DIAS[-1].date())
    assert total["relativo"] == pytest.approx(0.5 - 1, rel=1e-9)
    assert total["dias"] == len(DIAS) - 1


def test_resumo_soma_o_volume_dos_ultimos_365_dias() -> None:
    btc = _btc()
    antiga = (btc * 1.0).where(DIAS <= "2023-01-10")
    vol = _matriz(
        BTC=pd.Series(2.0, index=DIAS),
        ANTIGA=pd.Series(5.0, index=DIAS).where(DIAS <= "2023-01-10"),
    )
    r = resumo(_matriz(BTC=btc, ANTIGA=antiga), vol).set_index("moeda")
    assert r.loc["BTC", "volume_12m"] == pytest.approx(2.0 * 365)
    assert r.loc["ANTIGA", "volume_12m"] == pytest.approx(0.0)
    assert r.loc["ANTIGA", "ultimo_dia"] == date(2023, 1, 10)


def test_sem_btc_nao_ha_regua() -> None:
    with pytest.raises(ValueError, match="BTC"):
        calcular(_matriz(ETH=_btc()), _matriz(ETH=_btc()))
