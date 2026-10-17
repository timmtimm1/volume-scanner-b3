"""Treasury: leitura do CSV e variacao semanal, contra dados reais de 17/10/2026."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scanner.semana.fontes import FonteIndisponivelError
from scanner.semana.fontes.treasury import ler_csv, montar_treasuries
from scanner.semana.periodo import semana_da_data

FIXTURES = Path(__file__).parent / "fixtures" / "semana"
PRAZOS = ["3 Mo", "6 Mo", "2 Yr", "5 Yr", "10 Yr", "30 Yr"]


def _tabela(*nomes: str) -> pd.DataFrame:
    return pd.concat([ler_csv((FIXTURES / n).read_text()) for n in nomes]).sort_index()


def test_le_datas_e_colunas_com_aspas() -> None:
    tabela = _tabela("treasury_2026.csv")

    assert tabela.index.max() == pd.Timestamp("2026-10-16")
    assert tabela.loc["2026-10-16", "10 Yr"] == 5.09
    assert "1.5 Month" in tabela.columns


def test_semana_do_feriado_de_12_de_outubro() -> None:
    # Columbus Day: 12/10 e feriado la tambem, entao a base e sexta 09/10.
    bloco = montar_treasuries(
        _tabela("treasury_2026.csv"), semana_da_data(date(2026, 10, 16)), PRAZOS
    )

    assert bloco["data"] == "2026-10-16"
    assert bloco["data_anterior"] == "2026-10-09"
    dez = next(v for v in bloco["vencimentos"] if v["prazo"] == "10 Yr")
    assert dez["taxa"] == 5.09
    assert dez["taxa_anterior"] == 5.24
    assert dez["variacao_bp"] == pytest.approx(-15.0)
    assert [v["prazo"] for v in bloco["vencimentos"]] == PRAZOS


def test_base_no_ano_anterior() -> None:
    # Semana de 29/12/2025 a 02/01/2026: a base e 26/12/2025 (arquivo de 2025).
    tabela = _tabela("treasury_2025.csv", "treasury_2026.csv")

    bloco = montar_treasuries(tabela, semana_da_data(date(2026, 1, 2)), ["10 Yr"])

    assert bloco["data"] == "2026-01-02"
    assert bloco["data_anterior"] == "2025-12-26"
    assert bloco["vencimentos"][0]["taxa_anterior"] == 4.14
    assert bloco["vencimentos"][0]["taxa"] == 4.19
    assert bloco["vencimentos"][0]["variacao_bp"] == pytest.approx(5.0)


def test_sem_o_arquivo_do_ano_anterior_nao_inventa_base() -> None:
    with pytest.raises(FonteIndisponivelError, match="antes da segunda"):
        montar_treasuries(_tabela("treasury_2026.csv"), semana_da_data(date(2026, 1, 2)), ["10 Yr"])


def test_prazo_inexistente() -> None:
    with pytest.raises(FonteIndisponivelError, match="9 Yr"):
        montar_treasuries(
            _tabela("treasury_2026.csv"), semana_da_data(date(2026, 10, 16)), ["9 Yr"]
        )


def test_dados_velhos_levantam() -> None:
    tabela = _tabela("treasury_2026.csv").loc[:"2026-10-08"]

    with pytest.raises(FonteIndisponivelError, match="velha demais"):
        montar_treasuries(tabela, semana_da_data(date(2026, 10, 16)), ["10 Yr"])


@pytest.mark.parametrize("texto", ["", "<html>", 'Date,"3 Mo"\n', 'Date,"3 Mo"\nabc,1\n'])
def test_formato_inesperado(texto: str) -> None:
    with pytest.raises(FonteIndisponivelError):
        ler_csv(texto)
