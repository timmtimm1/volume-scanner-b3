"""BCB/SGS: Selic, CDI acumulado e IPCA, contra series reais de 17/10/2026."""

from __future__ import annotations

import json
import math
from datetime import date
from itertools import pairwise
from pathlib import Path
from typing import Any

import httpx
import pytest

from scanner.semana.fontes import FonteIndisponivelError
from scanner.semana.fontes import bcb as bcb_mod
from scanner.semana.fontes.bcb import acumulado, ler_sgs, montar_indicadores
from scanner.semana.periodo import semana_da_data

FIXTURES = Path(__file__).parent / "fixtures" / "semana"
FIM = date(2026, 10, 16)


def _serie(nome: str) -> list[tuple[date, float]]:
    return ler_sgs(json.loads((FIXTURES / f"{nome}.json").read_text()))


def test_indicadores_da_semana_de_16_de_outubro() -> None:
    r = montar_indicadores(
        FIM,
        _serie("bcb_432_selic"),
        _serie("bcb_12_cdi_mes"),
        _serie("bcb_12_cdi_ano"),
        _serie("bcb_13522_ipca"),
    )

    assert r["selic_meta"] == 13.75
    assert r["ipca_12m"] == 4.58
    assert r["ipca_referencia"] == "2026-09"
    # O SGS ainda nao publicou o CDI de 16/10: a conta termina em 15/10 e diz isso.
    assert r["cdi_data"] == "2026-10-15"
    assert r["cdi_mes"] == pytest.approx(1.00050788**10 - 1)
    assert r["cdi_ano"] == pytest.approx(
        math.prod(1 + p[1] / 100 for p in _serie("bcb_12_cdi_ano")) - 1
    )
    assert 0.10 < r["cdi_ano"] < 0.12


def test_selic_usa_o_ultimo_valor_ate_o_fim_e_ignora_o_posterior() -> None:
    selic = [(date(2026, 10, 9), 13.75), (date(2026, 10, 16), 13.75), (date(2026, 10, 20), 13.50)]

    r = montar_indicadores(FIM, selic, [], [], [(date(2026, 9, 1), 4.58)])

    assert r["selic_meta"] == 13.75
    assert r["cdi_mes"] is None
    assert r["cdi_ano"] is None
    assert r["cdi_data"] is None


def test_acumulado_composto() -> None:
    pontos = [(date(2026, 10, 1), 1.0), (date(2026, 10, 2), 2.0)]

    assert acumulado(pontos) == pytest.approx(1.01 * 1.02 - 1)
    assert acumulado([]) is None


def test_sem_selic_ou_sem_ipca_levanta() -> None:
    ipca = [(date(2026, 9, 1), 4.58)]
    with pytest.raises(FonteIndisponivelError, match="Selic"):
        montar_indicadores(FIM, [], [], [], ipca)
    with pytest.raises(FonteIndisponivelError, match="IPCA"):
        montar_indicadores(FIM, [(date(2026, 10, 9), 13.75)], [], [], [])


@pytest.mark.parametrize(
    "dados", [{"erro": "x"}, [{"data": "2026-10-01", "valor": "1"}], [{"x": 1}]]
)
def test_formato_inesperado(dados: Any) -> None:
    with pytest.raises(FonteIndisponivelError):
        ler_sgs(dados)


class _Cliente:
    def __init__(self, respostas: list[httpx.Response]) -> None:
        self.respostas = list(respostas)
        self.urls: list[str] = []

    def request(self, metodo: str, url: str, **_kw: Any) -> httpx.Response:
        self.urls.append(url)
        return self.respostas.pop(0)

    def close(self) -> None:
        pass


def test_502_tenta_mais_uma_vez(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scanner.semana.fontes.bcb.time.sleep", lambda _s: None)
    cliente = _Cliente(
        [httpx.Response(502), httpx.Response(200, json=[{"data": "16/10/2026", "valor": "13.75"}])]
    )

    pontos = bcb_mod._serie(432, date(2026, 9, 16), FIM, cliente)  # type: ignore[arg-type]

    assert pontos == [(date(2026, 10, 16), 13.75)]
    assert "dataInicial=16/09/2026&dataFinal=16/10/2026" in cliente.urls[0]


def test_periodo_sem_dado_e_404_e_vira_lista_vazia() -> None:
    erro = {"erro": {"statusCode": 404, "detail": "Value(s) not found"}}
    cliente = _Cliente([httpx.Response(404, json=erro)])

    assert bcb_mod._serie(12, date(2026, 10, 1), FIM, cliente) == []  # type: ignore[arg-type]


def test_busca_das_quatro_series_com_as_janelas_da_spec() -> None:
    um = httpx.Response(200, json=[{"data": "01/09/2026", "valor": "4.58"}])
    cliente = _Cliente(
        [
            httpx.Response(200, json=[{"data": "16/10/2026", "valor": "13.75"}]),
            httpx.Response(200, json=[{"data": "15/10/2026", "valor": "0.05"}]),
            httpx.Response(200, json=[{"data": "15/10/2026", "valor": "0.05"}]),
            um,
        ]
    )

    r = bcb_mod.indicadores(semana_da_data(FIM), cliente=cliente)  # type: ignore[arg-type]

    urls = cliente.urls
    assert "sgs.432" in urls[0]
    assert "sgs.12/" in urls[1] and "dataInicial=01/10/2026" in urls[1]
    assert "sgs.12/" in urls[2] and "dataInicial=01/01/2026" in urls[2]
    assert "sgs.13522" in urls[3] and "dataInicial=11/09/2025" in urls[3]
    assert r["selic_meta"] == 13.75


def test_pedacos_cobrem_o_periodo_sem_buraco_nem_passar_de_10_anos() -> None:
    pedacos = bcb_mod._pedacos(date(2016, 7, 16), date(2026, 10, 16))

    assert pedacos[0][0] == date(2016, 7, 16)
    assert pedacos[-1][1] == date(2026, 10, 16)
    for (_, fim), (inicio, _) in pairwise(pedacos):
        assert (inicio - fim).days == 1
    assert all((fim - inicio).days < 3650 for inicio, fim in pedacos)
    assert len(pedacos) == 3


def test_pedaco_unico_quando_o_periodo_e_curto() -> None:
    assert bcb_mod._pedacos(date(2026, 9, 1), FIM) == [(date(2026, 9, 1), FIM)]


def test_selic_na_sexta_e_o_ultimo_valor_ate_ela() -> None:
    pontos = [(date(2016, 7, 20), 14.25), (date(2016, 10, 19), 14.0), (date(2016, 12, 1), 13.75)]

    frame = bcb_mod.selic_por_semana(
        pontos, [date(2016, 10, 14), date(2016, 10, 21), date(2016, 12, 2)]
    )

    assert frame["taxa"].tolist() == [14.25, 14.0, 13.75]
    assert frame["data_base"].tolist() == [date(2016, 7, 20), date(2016, 10, 19), date(2016, 12, 1)]
    assert set(frame["serie"]) == {"selic"}
    assert set(frame["fonte"]) == {"bcb"}


def test_selic_antes_do_primeiro_ponto_nao_gera_semana() -> None:
    frame = bcb_mod.selic_por_semana([(date(2016, 10, 20), 14.0)], [date(2016, 10, 14)])

    assert frame.empty


def test_selic_semanal_pede_em_pedacos_e_junta() -> None:
    cliente = _Cliente(
        [
            httpx.Response(200, json=[{"data": "20/07/2016", "valor": "14.25"}]),
            httpx.Response(200, json=[{"data": "19/10/2016", "valor": "14.00"}]),
            httpx.Response(200, json=[{"data": "01/12/2021", "valor": "9.25"}]),
        ]
    )

    frame = bcb_mod.selic_semanal(
        date(2016, 10, 14),
        date(2026, 10, 16),
        cliente=cliente,  # type: ignore[arg-type]
    )

    assert len(cliente.urls) == 3
    assert frame["semana"].iloc[0] == date(2016, 10, 14)
    assert frame["taxa"].iloc[0] == 14.25
    assert frame["semana"].iloc[-1] == date(2026, 10, 16)
    assert frame["taxa"].iloc[-1] == 9.25
    assert len(frame) == 523  # de 14/10/2016 a 16/10/2026, inclusive


def test_selic_semanal_sem_nenhum_ponto_levanta() -> None:
    erro = {"erro": {"statusCode": 404}}
    cliente = _Cliente([httpx.Response(404, json=erro)] * 3)

    with pytest.raises(FonteIndisponivelError, match="nenhum ponto"):
        bcb_mod.selic_semanal(date(2016, 10, 14), FIM, cliente=cliente)  # type: ignore[arg-type]
