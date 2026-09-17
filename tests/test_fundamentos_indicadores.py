"""Do dado bruto da CVM para o trimestre da ficha (sem banco).

Os numeros sao os da Unipar, conferidos contra o balanco publicado.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from scanner.fundamentos.indicadores import trimestres

UNIPAR = 11592
BANCO = 19348

# Em reais, como a fase 1 grava (a CVM publica em milhares).
MIL = 1_000


def _resultado(
    cd_cvm: int,
    tipo: str,
    dt_refer: date,
    dt_ini: date,
    dt_fim: date,
    receita: float | None,
    ebit: float | None,
    lucro: float | None,
    depreciacao: float | None = None,
) -> dict[str, object]:
    return {
        "cd_cvm": cd_cvm,
        "tipo": tipo,
        "dt_refer": dt_refer,
        "dt_ini": dt_ini,
        "dt_fim": dt_fim,
        "receita": None if receita is None else receita * MIL,
        "resultado_bruto": None,
        "ebit": None if ebit is None else ebit * MIL,
        "lucro_liquido": None if lucro is None else lucro * MIL,
        "lucro_controladores": None if lucro is None else lucro * MIL,
        "depreciacao_amortizacao": None if depreciacao is None else depreciacao * MIL,
    }


def _balanco(cd_cvm: int, tipo: str, dt_refer: date, **valores: float | None) -> dict[str, object]:
    linha: dict[str, object] = {
        "cd_cvm": cd_cvm,
        "tipo": tipo,
        "dt_refer": dt_refer,
        "ativo_total": None,
        "ativo_circulante": None,
        "caixa": None,
        "aplicacoes_financeiras": None,
        "passivo_circulante": None,
        "emprestimos_cp": None,
        "arrendamento_cp": None,
        "emprestimos_lp": None,
        "arrendamento_lp": None,
        "patrimonio_liquido": None,
        "pl_nao_controladores": None,
        "acoes_on": None,
        "acoes_pn": None,
        "tesouraria_on": None,
        "tesouraria_pn": None,
    }
    for nome, valor in valores.items():
        if nome.startswith(("acoes", "tesouraria")):
            linha[nome] = valor
        else:
            linha[nome] = None if valor is None else valor * MIL
    return linha


def _documento(cd_cvm: int, tipo: str, dt_refer: date, publicado: date, layout: str) -> dict:
    return {
        "cd_cvm": cd_cvm,
        "tipo": tipo,
        "dt_refer": dt_refer,
        "publicado_em": publicado,
        "layout": layout,
    }


@pytest.fixture
def unipar() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Quatro trimestres reais da Unipar: 3T25, o ano de 2025 e 1T26 e 2T26."""
    resultados = [
        # 3T25: acumulado de 9 meses e o proprio trimestre.
        _resultado(
            UNIPAR,
            "ITR",
            date(2025, 9, 30),
            date(2025, 1, 1),
            date(2025, 9, 30),
            3_903_705,
            753_520,
            493_757,
            -230_831,
        ),
        _resultado(
            UNIPAR,
            "ITR",
            date(2025, 9, 30),
            date(2025, 7, 1),
            date(2025, 9, 30),
            1_260_883,
            186_060,
            109_148,
        ),
        # DFP 2025: so o ano inteiro. O 4T sai da diferenca.
        _resultado(
            UNIPAR,
            "DFP",
            date(2025, 12, 31),
            date(2025, 1, 1),
            date(2025, 12, 31),
            5_142_676,
            793_527,
            488_622,
            -316_152,
        ),
        _resultado(
            UNIPAR,
            "ITR",
            date(2026, 3, 31),
            date(2026, 1, 1),
            date(2026, 3, 31),
            1_238_235,
            84_970,
            37_472,
            -69_065,
        ),
        _resultado(
            UNIPAR,
            "ITR",
            date(2026, 6, 30),
            date(2026, 1, 1),
            date(2026, 6, 30),
            2_733_910,
            385_448,
            162_546,
            -154_745,
        ),
        _resultado(
            UNIPAR,
            "ITR",
            date(2026, 6, 30),
            date(2026, 4, 1),
            date(2026, 6, 30),
            1_495_676,
            300_481,
            125_074,
        ),
    ]
    balancos = [
        _balanco(UNIPAR, "ITR", date(2025, 9, 30), patrimonio_liquido=2_484_401),
        _balanco(UNIPAR, "DFP", date(2025, 12, 31), patrimonio_liquido=1_816_695),
        _balanco(UNIPAR, "ITR", date(2026, 3, 31), patrimonio_liquido=1_886_590),
        _balanco(
            UNIPAR,
            "ITR",
            date(2026, 6, 30),
            ativo_total=7_759_771,
            ativo_circulante=2_808_901,
            caixa=635_751,
            aplicacoes_financeiras=735_544,
            passivo_circulante=1_177_117,
            emprestimos_cp=227_600,
            arrendamento_cp=2_461,
            emprestimos_lp=3_474_947,
            arrendamento_lp=9_128,
            patrimonio_liquido=2_010_867,
            pl_nao_controladores=12_045,
            acoes_on=39_059_883,
            acoes_pn=74_113_382,
            tesouraria_on=74_500,
            tesouraria_pn=1_476_612,
        ),
    ]
    documentos = [
        _documento(UNIPAR, "ITR", date(2025, 9, 30), date(2025, 11, 13), "geral"),
        _documento(UNIPAR, "DFP", date(2025, 12, 31), date(2026, 3, 19), "geral"),
        _documento(UNIPAR, "ITR", date(2026, 3, 31), date(2026, 5, 14), "geral"),
        _documento(UNIPAR, "ITR", date(2026, 6, 30), date(2026, 8, 6), "geral"),
    ]
    return pd.DataFrame(resultados), pd.DataFrame(balancos), pd.DataFrame(documentos)


def _linha(saida: pd.DataFrame, rotulo: str) -> pd.Series:
    return saida[saida["rotulo"] == rotulo].iloc[0]


def test_trimestre_reportado_vale_como_esta(
    unipar: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    saida = trimestres(*unipar)

    dois_t26 = _linha(saida, "2T26")
    assert dois_t26["receita_tri"] == 1_495_676 * MIL
    assert dois_t26["lucro_tri"] == 125_074 * MIL
    assert dois_t26["origem"] == "ITR"
    assert dois_t26["publicado_em"] == date(2026, 8, 6)


def test_quarto_trimestre_sai_do_anual_menos_o_acumulado(
    unipar: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    """A CVM nao publica o 4T: 5.142.676 do ano menos 3.903.705 ate setembro."""
    quatro_t25 = _linha(trimestres(*unipar), "4T25")

    assert quatro_t25["receita_tri"] == (5_142_676 - 3_903_705) * MIL
    assert quatro_t25["lucro_tri"] == (488_622 - 493_757) * MIL  # prejuizo no trimestre
    assert quatro_t25["origem"] == "derivado"
    assert quatro_t25["publicado_em"] == date(2026, 3, 19)


def test_ebitda_usa_a_depreciacao_do_trimestre(
    unipar: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    """A DVA so traz o acumulado do ano: a do trimestre e a diferenca."""
    saida = trimestres(*unipar)

    # 2T26: D&A do trimestre = 154.745 acumulados ate junho - 69.065 ate marco.
    assert _linha(saida, "2T26")["ebitda_tri"] == (300_481 + (154_745 - 69_065)) * MIL
    # 1T26: o acumulado JA e o trimestre.
    assert _linha(saida, "1T26")["ebitda_tri"] == (84_970 + 69_065) * MIL


def test_doze_meses_somam_quatro_trimestres_seguidos(
    unipar: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    dois_t26 = _linha(trimestres(*unipar), "2T26")

    esperado = (1_495_676 + 1_238_235 + (5_142_676 - 3_903_705) + 1_260_883) * MIL
    assert dois_t26["receita_12m"] == esperado
    assert dois_t26["lucro_12m"] == (125_074 + 37_472 + (488_622 - 493_757) + 109_148) * MIL


def test_sem_os_quatro_trimestres_nao_ha_doze_meses(
    unipar: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    """Um acumulado de 15 meses disfarcado seria pior do que numero nenhum."""
    resultados, balancos, documentos = unipar
    sem_1t26 = resultados[resultados["dt_refer"] != date(2026, 3, 31)]

    saida = trimestres(sem_1t26, balancos, documentos)

    assert pd.isna(_linha(saida, "2T26")["receita_12m"])


def test_saldos_do_balanco(unipar: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]) -> None:
    dois_t26 = _linha(trimestres(*unipar), "2T26")

    # Patrimonio dos controladores, e nao o consolidado.
    assert dois_t26["patrimonio_liquido"] == (2_010_867 - 12_045) * MIL
    assert dois_t26["divida_liquida"] == (227_600 + 3_474_947 - 635_751 - 735_544) * MIL
    # A CVM poe o arrendamento dentro de "emprestimos": aqui ele sai.
    assert (
        dois_t26["divida_liquida_sem_arrendamento"]
        == (227_600 + 3_474_947 - 2_461 - 9_128 - 635_751 - 735_544) * MIL
    )
    assert round(float(dois_t26["liquidez_corrente"]), 3) == 2.386
    assert dois_t26["acoes_em_circulacao"] == 39_059_883 + 74_113_382 - 74_500 - 1_476_612


def test_banco_nao_tem_ebitda_nem_divida_liquida() -> None:
    """No layout financeiro esses numeros nao existem no sentido usual."""
    resultados = pd.DataFrame(
        [
            _resultado(
                BANCO,
                "ITR",
                date(2026, 6, 30),
                date(2026, 1, 1),
                date(2026, 6, 30),
                199_118_000,
                None,
                23_615_000,
            ),
            _resultado(
                BANCO,
                "ITR",
                date(2026, 6, 30),
                date(2026, 4, 1),
                date(2026, 6, 30),
                100_073_000,
                None,
                11_979_000,
            ),
        ]
    )
    balancos = pd.DataFrame(
        [
            _balanco(
                BANCO,
                "ITR",
                date(2026, 6, 30),
                patrimonio_liquido=228_026_000,
                pl_nao_controladores=10_247_000,
                ativo_total=3_202_125_000,
            )
        ]
    )
    documentos = pd.DataFrame(
        [_documento(BANCO, "ITR", date(2026, 6, 30), date(2026, 8, 4), "financeiro")]
    )

    linha = _linha(trimestres(resultados, balancos, documentos), "2T26")

    assert pd.isna(linha["ebitda_tri"])
    assert pd.isna(linha["divida_liquida"])
    assert pd.isna(linha["liquidez_corrente"])
    # O que existe no banco continua valendo.
    assert linha["lucro_tri"] == 11_979_000 * MIL
    assert linha["patrimonio_liquido"] == (228_026_000 - 10_247_000) * MIL


def test_mudanca_de_exercicio_social_mantem_o_trimestre_reportado() -> None:
    """ITR e DFP terminando no mesmo dia: vale o reportado, nao o derivado."""
    resultados = pd.DataFrame(
        [
            _resultado(
                21148,
                "ITR",
                date(2023, 3, 31),
                date(2023, 1, 1),
                date(2023, 3, 31),
                651_443,
                10_000,
                -41_902,
                -5_000,
            ),
            _resultado(
                21148,
                "ITR",
                date(2023, 3, 31),
                date(2023, 1, 1),
                date(2023, 3, 31),
                651_443,
                10_000,
                -41_902,
                -5_000,
            ),
            _resultado(
                21148,
                "DFP",
                date(2023, 3, 31),
                date(2022, 4, 1),
                date(2023, 3, 31),
                2_148_207,
                50_000,
                76_202,
                -20_000,
            ),
        ]
    )
    balancos = pd.DataFrame([_balanco(21148, "ITR", date(2023, 3, 31), patrimonio_liquido=100_000)])
    documentos = pd.DataFrame(
        [
            _documento(21148, "ITR", date(2023, 3, 31), date(2023, 5, 15), "geral"),
            _documento(21148, "DFP", date(2023, 3, 31), date(2023, 6, 29), "geral"),
        ]
    )

    saida = trimestres(resultados, balancos, documentos)

    assert len(saida) == 1
    assert saida.iloc[0]["origem"] == "ITR"
    assert saida.iloc[0]["receita_tri"] == 651_443 * MIL


def test_anual_sem_acumulado_do_mesmo_exercicio_nao_vira_trimestre() -> None:
    """Sem o acumulado para subtrair, o ano inteiro viraria um "trimestre"."""
    resultados = pd.DataFrame(
        [
            _resultado(
                999,
                "DFP",
                date(2024, 12, 31),
                date(2024, 1, 1),
                date(2024, 12, 31),
                4_000_000,
                500_000,
                300_000,
                -100_000,
            )
        ]
    )
    documentos = pd.DataFrame(
        [_documento(999, "DFP", date(2024, 12, 31), date(2025, 3, 20), "geral")]
    )

    saida = trimestres(resultados, pd.DataFrame(), documentos)

    assert saida.empty


def test_rotulo_do_trimestre(unipar: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]) -> None:
    assert set(trimestres(*unipar)["rotulo"]) == {"3T25", "4T25", "1T26", "2T26"}
