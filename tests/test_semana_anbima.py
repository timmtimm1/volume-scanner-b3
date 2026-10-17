"""ANBIMA: leitura da curva prefixada, contra o CSV real de 16/10/2026."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scanner.semana.fontes import FonteIndisponivelError
from scanner.semana.fontes.anbima import ler_curva, montar_curva

FIXTURES = Path(__file__).parent / "fixtures" / "semana"


def _csv(nome: str) -> str:
    return (FIXTURES / nome).read_bytes().decode("latin-1")


def test_le_a_data_e_a_coluna_prefixada() -> None:
    data, curva = ler_curva(_csv("anbima_2026-10-16.csv"))

    assert data == date(2026, 10, 16)
    assert curva == {252: 12.9234, 504: 12.7898, 1260: 13.0456, 2520: 13.0723}


def test_vertice_sem_prefixado_nao_entra() -> None:
    _, curva = ler_curva(_csv("anbima_2026-10-16.csv"))

    assert 2646 not in curva


def test_variacao_em_pontos_base() -> None:
    fim = ler_curva(_csv("anbima_2026-10-16.csv"))[1]
    inicio = ler_curva(_csv("anbima_2026-10-09.csv"))[1]

    bloco = montar_curva(date(2026, 10, 16), date(2026, 10, 9), fim, inicio, [252, 2520])

    um_ano, dez_anos = bloco["vertices"]
    assert bloco["data"] == "2026-10-16"
    assert bloco["data_anterior"] == "2026-10-09"
    assert um_ano["anos"] == 1.0
    assert um_ano["taxa"] == 12.9234
    assert um_ano["taxa_anterior"] == 12.5792
    assert um_ano["variacao_bp"] == pytest.approx(34.42)
    assert dez_anos["anos"] == 10.0
    assert dez_anos["variacao_bp"] == pytest.approx((13.0723 - 12.5151) * 100)


def test_vertice_ausente_na_data_final_levanta() -> None:
    with pytest.raises(FonteIndisponivelError, match="vertice 756"):
        montar_curva(date(2026, 10, 16), date(2026, 10, 9), {252: 1.0}, {252: 1.0, 756: 1.0}, [756])


def test_vertice_ausente_na_base_deixa_a_variacao_nula() -> None:
    bloco = montar_curva(date(2026, 10, 16), date(2026, 10, 9), {252: 1.0}, {}, [252])

    assert bloco["vertices"][0]["variacao_bp"] is None


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "<html>erro</html>",
        "17/10/2026;Beta 1\n",
        "16/10/2026;Beta 1\n\nVertices;ETTJ IPCA\n1;2\n",
    ],
)
def test_formato_inesperado(texto: str) -> None:
    with pytest.raises(FonteIndisponivelError):
        ler_curva(texto)
