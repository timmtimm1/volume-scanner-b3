"""Quando comprar e quando vender a cesta das criptos mais negociadas."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from scanner.cripto.sazonal import (
    COMPRA,
    CONFERENCIA,
    EM_PARTE,
    ESCOLHA,
    FORA,
    NAO_REPETIU,
    REPETIU,
    SEM_CONFERENCIA,
    TAXA_A_VISTA,
    TAXA_FUTUROS,
    VENDA,
    calcular,
    cesta_mensal,
    julgar,
    resultado_por_ano,
)

PERIODOS = ((2017, 2021), (2022, 2026))


def _cesta(padrao: dict[int, float], inicio: str = "2017-01", fim: str = "2026-10") -> pd.DataFrame:
    """Uma cesta mes a mes com o retorno de cada mes do calendario fixo."""
    meses = pd.period_range(inicio, fim, freq="M")
    return pd.DataFrame(
        {
            "mes": [m.to_timestamp().date() for m in meses],
            "retorno": [padrao.get(m.month, 0.0) for m in meses],
            "retorno_btc": 0.0,
            "moedas": 50,
        }
    )


def _linha(janelas: pd.DataFrame, lado: str, inicio_mes: int, meses: int) -> pd.Series:
    achou = janelas[
        (janelas["lado"] == lado)
        & (janelas["inicio_mes"] == inicio_mes)
        & (janelas["meses"] == meses)
    ]
    assert len(achou) == 1
    return achou.iloc[0]


def test_compra_e_venda_de_uma_janela_com_as_taxas() -> None:
    anos = resultado_por_ano(_cesta({4: 0.10, 5: -0.05}), PERIODOS)
    um = anos[(anos["inicio_mes"] == 4) & (anos["meses"] == 2) & (anos["ano"] == 2019)]
    compra = um[um["lado"] == COMPRA]["resultado"].item()
    venda = um[um["lado"] == VENDA]["resultado"].item()
    assert compra == pytest.approx(1.10 * 0.95 * (1 - TAXA_A_VISTA) ** 2 - 1)
    # Vendido refeito todo mes: ganha 10% de queda... perde nos 10% de alta.
    assert venda == pytest.approx(0.90 * 1.05 * (1 - TAXA_FUTUROS) ** 2 - 1)


def test_janela_que_cruza_a_fronteira_nao_entra_na_escolha_nem_na_conferencia() -> None:
    anos = resultado_por_ano(_cesta({}), PERIODOS)
    nov21 = anos[(anos["inicio_mes"] == 11) & (anos["meses"] == 4) & (anos["ano"] == 2021)]
    assert set(nov21["periodo"]) == {FORA}
    dez21 = anos[(anos["inicio_mes"] == 12) & (anos["meses"] == 1) & (anos["ano"] == 2021)]
    assert set(dez21["periodo"]) == {ESCOLHA}
    jan22 = anos[(anos["inicio_mes"] == 1) & (anos["meses"] == 6) & (anos["ano"] == 2022)]
    assert set(jan22["periodo"]) == {CONFERENCIA}


def test_janela_so_com_meses_que_existem() -> None:
    cesta = _cesta({})
    cesta = cesta[cesta["mes"] != date(2019, 3, 1)]  # um mes faltando
    anos = resultado_por_ano(cesta, PERIODOS)
    atravessa = anos[(anos["ano"] == 2019) & (anos["inicio_mes"] == 2) & (anos["meses"] == 2)]
    assert atravessa.empty
    # A ultima janela termina no ultimo mes da cesta.
    assert not anos[(anos["inicio_mes"] == 10) & (anos["meses"] == 1) & (anos["ano"] == 2026)].empty
    assert anos[(anos["inicio_mes"] == 10) & (anos["meses"] == 2) & (anos["ano"] == 2026)].empty


def test_junho_que_sempre_cai_e_a_venda_escolhida_e_repete() -> None:
    janelas = julgar(resultado_por_ano(_cesta({6: -0.10, 4: 0.08}), PERIODOS))
    venda = janelas[janelas["lado"] == VENDA].sort_values("posicao")
    primeira = venda.iloc[0]
    assert (primeira["inicio_mes"], primeira["meses"]) == (6, 1)
    assert primeira["posicao"] == 1
    assert primeira["veredito"] == REPETIU
    assert primeira["escolha_positivos"] == primeira["escolha_anos"] == 5
    # A melhor compra pega abril e foge de junho. Pode ser mais longa que "so
    # abril": cada janela e julgada contra uma janela qualquer do MESMO tamanho,
    # e entre as de 6 meses metade pega junho (novembro a abril sai na frente).
    compra = janelas[janelas["lado"] == COMPRA].sort_values("posicao").iloc[0]
    meses = {(int(compra["inicio_mes"]) - 1 + i) % 12 + 1 for i in range(int(compra["meses"]))}
    assert 4 in meses
    assert 6 not in meses
    assert compra["veredito"] == REPETIU
    assert _linha(janelas, COMPRA, 4, 1)["veredito"] == REPETIU


def test_controle_e_a_media_de_uma_janela_qualquer_do_mesmo_tamanho() -> None:
    anos = resultado_por_ano(_cesta({6: -0.10, 4: 0.08}), PERIODOS)
    janelas = julgar(anos)
    um_mes_escolha = anos[
        (anos["lado"] == COMPRA) & (anos["meses"] == 1) & (anos["periodo"] == ESCOLHA)
    ]
    linha = _linha(janelas, COMPRA, 4, 1)
    assert linha["escolha_controle"] == pytest.approx(um_mes_escolha["resultado"].mean())


def test_veredito_em_parte_e_nao_repetiu() -> None:
    # Abril sobe forte na escolha e cai um pouco na conferencia, num mercado que
    # cai mais: ganhou da janela qualquer, mas perdeu dinheiro -> em parte.
    meses = pd.period_range("2017-01", "2026-10", freq="M")
    retorno = []
    for m in meses:
        escolha = m.year <= 2021
        if m.month == 4:
            retorno.append(0.20 if escolha else -0.02)
        else:
            retorno.append(0.0 if escolha else -0.05)
    cesta = pd.DataFrame({"mes": [m.to_timestamp().date() for m in meses], "retorno": retorno})
    janelas = julgar(resultado_por_ano(cesta, PERIODOS))
    assert _linha(janelas, COMPRA, 4, 1)["veredito"] == EM_PARTE
    # Maio: neutro na escolha, cai na conferencia igual ao resto -> nao repetiu.
    assert _linha(janelas, COMPRA, 5, 1)["veredito"] == NAO_REPETIU


def test_sem_anos_suficientes_na_escolha_nao_concorre_e_sem_conferencia_avisa() -> None:
    janelas = julgar(resultado_por_ano(_cesta({}, inicio="2020-01", fim="2021-12"), PERIODOS))
    assert janelas["posicao"].isna().all()  # 2 anos de escolha: pouco
    assert set(janelas["veredito"]) == {SEM_CONFERENCIA}


def test_cesta_pega_as_mais_negociadas_antes_do_mes_e_tira_a_media() -> None:
    dias = pd.date_range("2025-01-01", "2025-06-30", freq="D")
    fech = pd.DataFrame(index=dias, dtype="float64")
    vol = pd.DataFrame(index=dias, dtype="float64")
    # Tres moedas sobem 10%, 20% e 30% ao mes (o salto e no ultimo dia do mes).
    for moeda, alta, volume in (("BTC", 0.10, 3e9), ("A", 0.20, 2e9), ("B", 0.30, 1e9)):
        nivel = pd.Series(1.0, index=dias)
        for fim in pd.date_range("2025-01-31", "2025-06-30", freq="ME"):
            nivel[nivel.index >= fim] *= 1 + alta
        fech[moeda] = nivel
        vol[moeda] = volume
    # A moeda B passa a ser a mais negociada a partir de 01/04: entra na cesta de
    # maio e junho com 2 vagas, nunca na de abril (o volume de abril e o de antes).
    vol.loc[vol.index >= "2025-04-01", "B"] = 9e9
    cesta = cesta_mensal(fech, vol, pd.Timestamp("2025-06-15"), n=2).set_index("mes")
    abril = cesta.loc[date(2025, 4, 1)]
    assert abril["retorno"] == pytest.approx((0.10 + 0.20) / 2)
    assert abril["moedas"] == 2
    maio = cesta.loc[date(2025, 5, 1)]
    assert maio["retorno"] == pytest.approx((0.10 + 0.30) / 2)
    assert maio["retorno_btc"] == pytest.approx(0.10)
    # Junho ainda nao fechou em 15/06: fica de fora.
    assert date(2025, 6, 1) not in cesta.index
    # Janeiro nao tem 60 dias de volume antes: sem cesta.
    assert date(2025, 1, 1) not in cesta.index


def test_calcular_devolve_as_tres_tabelas() -> None:
    dias = pd.date_range("2016-09-01", "2026-11-23", freq="D")
    rng = np.random.default_rng(5)
    fech = pd.DataFrame(
        {m: 100 * np.cumprod(1 + rng.normal(0, 0.02, len(dias))) for m in ("BTC", "ETH", "SOL")},
        index=dias,
    )
    vol = pd.DataFrame(dict.fromkeys(fech.columns, 1000000000.0), index=dias)
    estudo = calcular(fech, vol, PERIODOS)
    assert len(estudo.cesta) > 100
    assert set(estudo.janelas["lado"]) == {COMPRA, VENDA}
    assert len(estudo.janelas) == 2 * 12 * 6
    assert estudo.anos["resultado"].notna().all()
    # Novembro de 2026 nao fechou.
    assert pd.to_datetime(estudo.cesta["mes"]).max() == pd.Timestamp("2026-10-01")


def test_rotulo_da_janela_vira_o_ano() -> None:
    from scanner.cripto.sazonal import rotulo

    assert rotulo(4, 1) == "abr"
    assert rotulo(5, 6) == "mai a out"
    assert rotulo(11, 6) == "nov a abr"


def test_sem_anos_de_escolha_ninguem_e_escolhido_e_o_log_diz() -> None:
    from scanner.cripto.sazonal import escolhidas

    janelas = julgar(resultado_por_ano(_cesta({}, inicio="2023-01", fim="2025-12"), PERIODOS))
    assert janelas["posicao"].isna().all()
    assert (janelas["conferencia_anos"] > 0).all()
    assert all("nenhuma janela" in linha for linha in escolhidas(janelas))


def test_log_mostra_a_escolhida_de_cada_lado() -> None:
    from scanner.cripto.sazonal import escolhidas

    linhas = escolhidas(julgar(resultado_por_ano(_cesta({6: -0.10, 4: 0.08}), PERIODOS)))
    assert linhas[0].startswith("compra: ")
    assert linhas[1].startswith("venda: jun -- repetiu")
