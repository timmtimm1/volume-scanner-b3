"""Focus e Nasdaq: respostas reais de 17/10/2026."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scanner.semana.fontes import FonteIndisponivelError
from scanner.semana.fontes.focus import ler_consenso, url
from scanner.semana.fontes.nasdaq import ler_data, rotulo_do_trimestre

FIXTURES = Path(__file__).parent / "fixtures" / "semana"


def _json(nome: str) -> Any:
    return json.loads((FIXTURES / nome).read_text())


def test_focus_da_selic_da_reuniao_7() -> None:
    assert ler_consenso(_json("focus_selic_r7_2026.json"), "selic") == {
        "mediana": 13.5,
        "unidade": "% a.a.",
        "fonte": "Focus",
        "data": "2026-10-09",
    }


def test_focus_do_ipca_do_mes() -> None:
    assert ler_consenso(_json("focus_ipca_10_2026.json"), "ipca") == {
        "mediana": 0.3277,
        "unidade": "%",
        "fonte": "Focus",
        "data": "2026-10-09",
    }


def test_focus_sem_serie_devolve_none() -> None:
    assert ler_consenso(_json("focus_vazio.json"), "ipca") is None


def test_focus_formato_inesperado_levanta() -> None:
    with pytest.raises(FonteIndisponivelError):
        ler_consenso({"value": "x"}, "ipca")
    with pytest.raises(FonteIndisponivelError):
        ler_consenso({"value": [{"Data": "2026-10-09"}]}, "ipca")


def test_url_do_focus_usa_base_zero_e_a_maior_data_ate_a_sexta() -> None:
    u = url("ipca", "10/2026", date(2026, 10, 16))

    assert "ExpectativaMercadoMensais" in u
    assert "baseCalculo%20eq%200" in u
    assert "Data%20le%20%272026-10-16%27" in u
    assert "orderby=Data%20desc" in u and "$top=1" in u
    assert "Indicador%20eq%20%27IPCA%27" in u
    assert "ExpectativasMercadoSelic" in url("selic", "R7/2026", date(2026, 10, 16))


def test_nasdaq_bbd_confirmado_apos_o_fechamento() -> None:
    r = ler_data(_json("nasdaq_bbd_confirmado.json"))

    assert r is not None
    assert (r.data, r.horario, r.trimestre) == (date(2026, 10, 22), "após o fechamento", "3T26")


def test_nasdaq_abev_estimado_nao_entra() -> None:
    assert ler_data(_json("nasdaq_abev_estimado.json")) is None


def test_nasdaq_antes_da_abertura_e_sem_horario() -> None:
    base = _json("nasdaq_bbd_confirmado.json")
    texto = base["data"]["reportText"]

    antes = ler_data(
        {"data": {"reportText": texto.replace("after market close", "before market open")}}
    )
    sem = ler_data({"data": {"reportText": texto.replace(" after market close", "")}})

    assert antes is not None and antes.horario == "antes da abertura"
    assert sem is not None and sem.horario is None and sem.data == date(2026, 10, 22)


def test_nasdaq_texto_desconhecido_levanta() -> None:
    with pytest.raises(FonteIndisponivelError):
        ler_data({"data": {"reportText": "no date available"}})
    with pytest.raises(FonteIndisponivelError):
        ler_data({"data": None})


@pytest.mark.parametrize(
    ("bruto", "rotulo"),
    [("Sep 2026", "3T26"), ("Dec 2026", "4T26"), ("Mar 2027", "1T27"), ("Jan 2027", "Jan 2027")],
)
def test_rotulo_do_trimestre(bruto: str, rotulo: str) -> None:
    assert rotulo_do_trimestre(bruto) == rotulo
