"""Variacao semanal ajustada: carteira de uma acao, com caixa e multiplicador."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import pytest

from scanner.fundamentos.b3 import B3IndisponivelError, EventoEmAcoes, Provento, Suplemento
from scanner.semana import acoes
from scanner.semana.acoes import (
    buscar_eventos_da_semana,
    ranking,
    variacoes_da_semana,
)
from scanner.semana.periodo import semana_da_data
from scanner.storage import repository

# Semana do feriado de 12/10/2026: base na sexta 09/10, pregoes de 13 a 16.
SEMANA = semana_da_data(date(2026, 10, 16))
INI = SEMANA.inicio
FIM = SEMANA.fim


def _barras(**precos: tuple[float, float]) -> pd.DataFrame:
    linhas = []
    for ticker, (p_ini, p_fim) in precos.items():
        linhas.append({"ticker": ticker, "trade_date": INI, "close": p_ini})
        linhas.append({"ticker": ticker, "trade_date": date(2026, 10, 14), "close": p_ini})
        linhas.append({"ticker": ticker, "trade_date": FIM, "close": p_fim})
    return pd.DataFrame(linhas)


def _provs(*itens: tuple[str, date, float]) -> pd.DataFrame:
    return pd.DataFrame(itens, columns=["ticker", "data_com", "valor"])


def _evs(*itens: tuple[str, date, str, float]) -> pd.DataFrame:
    return pd.DataFrame(itens, columns=["ticker", "data_com", "tipo", "multiplicador"])


SEM_PROVS = _provs()
SEM_EVS = _evs()
DIA_13 = date(2026, 10, 13)
DIA_14 = date(2026, 10, 14)


def _calc(
    barras: pd.DataFrame,
    proventos: pd.DataFrame = SEM_PROVS,
    eventos: pd.DataFrame = SEM_EVS,
    universo: list[str] | None = None,
    conferidos: set[str] | None = None,
) -> pd.DataFrame:
    tickers = list(barras["ticker"].unique()) if universo is None else universo
    return variacoes_da_semana(
        barras, tickers, SEMANA, proventos, eventos, tickers if conferidos is None else conferidos
    )


def _linha(frame: pd.DataFrame, ticker: str) -> Any:
    return frame.set_index("ticker").loc[ticker]


def test_sem_evento_a_variacao_e_a_bruta() -> None:
    out = _calc(_barras(AAAA3=(10.0, 10.5)))

    linha = _linha(out, "AAAA3")
    assert linha["variacao"] == pytest.approx(0.05)
    assert linha["variacao_bruta"] == pytest.approx(0.05)
    assert linha["multiplicador"] == 1.0
    assert linha["proventos_por_acao"] == 0.0
    assert not linha["ajustado"]
    assert linha["comparavel"]
    assert linha["data_inicio"] == INI
    assert linha["data_fim"] == FIM


def test_dividendo_de_2_reais_em_acao_de_40_que_fecha_a_38_nao_variou() -> None:
    out = _calc(_barras(DIVI3=(40.0, 38.0)), _provs(("DIVI3", DIA_14, 2.0)))

    linha = _linha(out, "DIVI3")
    assert linha["variacao"] == pytest.approx(0.0)
    assert linha["variacao_bruta"] == pytest.approx(-0.05)
    assert linha["proventos_por_acao"] == pytest.approx(2.0)
    assert linha["ajustado"]


def test_desdobramento_1_para_2() -> None:
    out = _calc(_barras(SPLT3=(40.0, 20.4)), eventos=_evs(("SPLT3", DIA_14, "DESDOBRAMENTO", 2.0)))

    linha = _linha(out, "SPLT3")
    assert linha["variacao"] == pytest.approx(0.02)
    assert linha["multiplicador"] == pytest.approx(2.0)
    assert linha["variacao_bruta"] == pytest.approx(-0.49)


def test_grupamento_10_para_1() -> None:
    out = _calc(_barras(GRUP3=(1.0, 10.5)), eventos=_evs(("GRUP3", DIA_14, "GRUPAMENTO", 0.1)))

    assert _linha(out, "GRUP3")["variacao"] == pytest.approx(0.05)


def test_bonificacao_de_3_por_cento() -> None:
    # 100 -> 103 acoes por 100; o preco cai de 10,00 para 9,709... e nada mudou.
    out = _calc(
        _barras(BONI3=(10.0, 10.0 / 1.03)), eventos=_evs(("BONI3", DIA_14, "BONIFICACAO", 1.03))
    )

    assert _linha(out, "BONI3")["variacao"] == pytest.approx(0.0, abs=1e-12)


def test_ordem_importa_dividendo_antes_do_desdobramento() -> None:
    # Dividendo de R$ 2 sobre 1 acao (dia 13), depois desdobramento 1:2 (dia 14):
    # 2 acoes x 19 + 2 de caixa = 40 -> variacao 0 sobre o preco 40.
    antes = _calc(
        _barras(ORDM3=(40.0, 19.0)),
        _provs(("ORDM3", DIA_13, 2.0)),
        _evs(("ORDM3", DIA_14, "DESDOBRAMENTO", 2.0)),
    )
    # Desdobramento (dia 13) e depois o dividendo (dia 14) de R$ 1 por acao NOVA:
    # incide sobre 2 acoes -> caixa 2.
    depois = _calc(
        _barras(ORDM3=(40.0, 19.0)),
        _provs(("ORDM3", DIA_14, 1.0)),
        _evs(("ORDM3", DIA_13, "DESDOBRAMENTO", 2.0)),
    )

    assert _linha(antes, "ORDM3")["proventos_por_acao"] == pytest.approx(2.0)
    assert _linha(antes, "ORDM3")["variacao"] == pytest.approx(0.0)
    assert _linha(depois, "ORDM3")["proventos_por_acao"] == pytest.approx(2.0)
    assert _linha(depois, "ORDM3")["variacao"] == pytest.approx(0.0)


def test_no_mesmo_dia_o_provento_vem_antes_do_evento() -> None:
    # Data com igual: o dividendo vale para a acao de antes do desdobramento.
    out = _calc(
        _barras(MESM3=(40.0, 19.0)),
        _provs(("MESM3", DIA_14, 2.0)),
        _evs(("MESM3", DIA_14, "DESDOBRAMENTO", 2.0)),
    )

    linha = _linha(out, "MESM3")
    assert linha["proventos_por_acao"] == pytest.approx(2.0)
    assert linha["variacao"] == pytest.approx((2 * 19.0 + 2.0) / 40.0 - 1)


def test_data_com_no_ultimo_pregao_nao_ajusta() -> None:
    # Ex so na semana seguinte: o preco_fim ainda e "com" o direito.
    out = _calc(
        _barras(NOFM3=(40.0, 38.0)),
        _provs(("NOFM3", FIM, 2.0)),
        _evs(("NOFM3", FIM, "DESDOBRAMENTO", 2.0)),
    )

    linha = _linha(out, "NOFM3")
    assert linha["variacao"] == pytest.approx(linha["variacao_bruta"])
    assert not linha["ajustado"]


def test_data_com_no_pregao_base_ajusta() -> None:
    out = _calc(_barras(NOIN3=(40.0, 38.0)), _provs(("NOIN3", INI, 2.0)))

    linha = _linha(out, "NOIN3")
    assert linha["variacao"] == pytest.approx(0.0)
    assert linha["ajustado"]


def test_evento_fora_da_janela_e_ignorado() -> None:
    out = _calc(
        _barras(FORA3=(40.0, 38.0)),
        _provs(("FORA3", date(2026, 10, 8), 2.0)),
        _evs(("FORA3", date(2026, 10, 19), "DESDOBRAMENTO", 2.0)),
    )

    assert _linha(out, "FORA3")["variacao"] == pytest.approx(-0.05)
    assert not _linha(out, "FORA3")["ajustado"]


def test_cisao_fica_fora_do_ranking() -> None:
    barras = _barras(CISA3=(10.0, 7.0), BOAA3=(10.0, 11.0))
    out = _calc(barras, eventos=_evs(("CISA3", DIA_14, "CIS RED CAP", np.nan)))

    assert not _linha(out, "CISA3")["comparavel"]
    # O motivo vai junto, para a tela dizer por que o papel ficou de fora.
    assert _linha(out, "CISA3")["eventos_sem_ajuste"] == "CIS RED CAP"
    assert _linha(out, "BOAA3")["eventos_sem_ajuste"] is None
    altas, quedas, fora = ranking(out, 10)
    assert list(altas["ticker"]) == ["BOAA3"]
    assert quedas.empty  # BOAA3 subiu: nao e queda
    assert list(fora["ticker"]) == ["CISA3"]


def test_ticker_sem_negocio_na_semana_sai() -> None:
    barras = pd.concat(
        [
            _barras(OKOK3=(10.0, 11.0)),
            pd.DataFrame([{"ticker": "PARA3", "trade_date": INI, "close": 5.0}]),
        ]
    )

    assert list(_calc(barras)["ticker"]) == ["OKOK3"]


def test_ticker_sem_base_nos_5_pregoes_anteriores_sai() -> None:
    barras = pd.concat(
        [
            _barras(OKOK3=(10.0, 11.0)),
            pd.DataFrame(
                [
                    {"ticker": "VELH3", "trade_date": date(2026, 9, 30), "close": 5.0},
                    {"ticker": "VELH3", "trade_date": FIM, "close": 6.0},
                ]
            ),
        ]
    )

    assert list(_calc(barras)["ticker"]) == ["OKOK3"]


def test_base_usa_o_ultimo_pregao_negociado_dentro_dos_5() -> None:
    # Sem negocio na sexta 09/10: vale a quinta 08/10.
    barras = pd.DataFrame(
        [
            {"ticker": "ATRA3", "trade_date": date(2026, 10, 8), "close": 20.0},
            {"ticker": "ATRA3", "trade_date": FIM, "close": 22.0},
        ]
    )

    linha = _linha(_calc(barras), "ATRA3")
    assert linha["data_inicio"] == date(2026, 10, 8)
    assert linha["variacao"] == pytest.approx(0.10)


def test_ticker_fora_do_universo_sai() -> None:
    out = _calc(_barras(DENT3=(10.0, 11.0), FORA3=(10.0, 12.0)), universo=["DENT3"])

    assert list(out["ticker"]) == ["DENT3"]


def test_semana_do_feriado_de_12_de_outubro_usa_a_base_de_09_10() -> None:
    assert date(2026, 10, 9) == INI
    barras = pd.DataFrame(
        [
            {"ticker": "FERI3", "trade_date": date(2026, 10, 9), "close": 10.0},
            {"ticker": "FERI3", "trade_date": date(2026, 10, 13), "close": 12.0},
            {"ticker": "FERI3", "trade_date": date(2026, 10, 16), "close": 11.0},
        ]
    )

    linha = _linha(_calc(barras), "FERI3")
    assert linha["preco_inicio"] == 10.0
    assert linha["variacao"] == pytest.approx(0.10)


def test_conferido_so_para_quem_a_b3_respondeu() -> None:
    out = _calc(_barras(CONF3=(10.0, 11.0), NAOC3=(10.0, 11.0)), conferidos={"CONF3"})

    assert bool(_linha(out, "CONF3")["conferido"]) is True
    assert bool(_linha(out, "NAOC3")["conferido"]) is False


def test_barras_vazias() -> None:
    out = variacoes_da_semana(
        pd.DataFrame(columns=["ticker", "trade_date", "close"]),
        ["X"],
        SEMANA,
        SEM_PROVS,
        SEM_EVS,
        [],
    )
    assert out.empty
    assert list(out.columns) == list(acoes.COLUNAS_SAIDA)


def test_ranking_com_empate_desempata_por_ticker() -> None:
    barras = _barras(CCCC3=(10.0, 11.0), AAAA3=(10.0, 11.0), BBBB3=(10.0, 11.0), DDDD3=(10.0, 9.0))
    out = _calc(barras)

    altas, quedas, fora = ranking(out, 2)

    assert list(altas["ticker"]) == ["AAAA3", "BBBB3"]
    assert list(quedas["ticker"]) == ["DDDD3"]  # so ela caiu
    assert fora.empty


def test_altas_so_com_quem_subiu_e_quedas_so_com_quem_caiu() -> None:
    """18/10/2026: nas criptos, "Maiores altas" saiu com duas moedas em queda.

    As acoes usam a mesma regra de ranking e tinham o mesmo defeito: numa
    semana com uma alta so, a lista de altas era completada com quedas. Se o
    ranking voltar a ser "as n maiores variacoes", este teste quebra.
    """
    barras = _barras(SOBE3=(10.0, 11.0), PARA3=(10.0, 10.0), CAI3=(10.0, 9.5), DESCE3=(10.0, 8.0))
    out = _calc(barras)

    altas, quedas, _ = ranking(out, 5)

    assert list(altas["ticker"]) == ["SOBE3"]
    assert list(quedas["ticker"]) == ["DESCE3", "CAI3"]


# --- coleta ---------------------------------------------------------------


class _Cliente:
    pass


# O repositorio e trocado nos testes abaixo: o engine nunca e usado.
_ENGINE: Any = object()


def test_coleta_com_dois_emissores_um_falhando(monkeypatch: pytest.MonkeyPatch) -> None:
    papeis = [
        {"ticker": "AAAA3", "isin": "BRAAAAACNOR1", "emissor_b3": "AAAA"},
        {"ticker": "AAAA4", "isin": "BRAAAAACNPR1", "emissor_b3": "AAAA"},
        {"ticker": "BBBB3", "isin": "BRBBBBACNOR1", "emissor_b3": "BBBB"},
    ]
    monkeypatch.setattr(repository, "papeis_com_emissor", lambda *_a: papeis)
    chamadas: list[str] = []

    def falso(_cliente: object, emissor: str) -> Suplemento:
        chamadas.append(emissor)
        if emissor == "BBBB":
            raise B3IndisponivelError("fora do ar")
        return Suplemento(
            proventos=[
                Provento(None, "BRAAAAACNOR1", "DIVIDENDO", Decimal("0.5"), DIA_14, None, None),
                Provento(
                    None, "BRAAAAACNOR1", "DIVIDENDO", Decimal("9"), FIM, None, None
                ),  # data com no ultimo pregao: fora da janela
            ],
            eventos_em_acoes=[
                EventoEmAcoes("BRAAAAACNPR1", "DESDOBRAMENTO", Decimal("100"), DIA_14, None),
                EventoEmAcoes("BRAAAAACNPR1", "CIS RED CAP", Decimal("100"), DIA_13, None),
                EventoEmAcoes("BRAAAAACNPR1", "CIS RED CAP", Decimal("100"), DIA_13, None),
            ],
        )

    monkeypatch.setattr(acoes, "suplemento", falso)

    res = buscar_eventos_da_semana(_ENGINE, ["AAAA3", "AAAA4", "BBBB3"], SEMANA, _Cliente())

    assert chamadas == ["AAAA", "BBBB"]  # uma chamada por emissor, nao por ticker
    assert res.falhas == ("BBBB",)
    assert res.conferidos == frozenset({"AAAA3", "AAAA4"})
    assert list(res.proventos["ticker"]) == ["AAAA3"]
    assert list(res.proventos["valor"]) == [0.5]
    ev = res.eventos.sort_values("tipo")
    assert list(ev["ticker"]) == ["AAAA4", "AAAA4"]  # a cisao duplicada conta uma vez
    assert list(ev["tipo"]) == ["CIS RED CAP", "DESDOBRAMENTO"]
    assert ev["multiplicador"].isna().tolist() == [True, False]


def test_coleta_sem_papeis_nao_chama_a_b3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repository, "papeis_com_emissor", lambda *_a: [])

    def nunca(*_a: object) -> Suplemento:
        raise AssertionError("nao devia chamar")

    monkeypatch.setattr(acoes, "suplemento", nunca)

    res = buscar_eventos_da_semana(_ENGINE, ["ZZZZ3"], SEMANA, _Cliente())

    assert res.conferidos == frozenset()
    assert res.proventos.empty
    assert res.eventos.empty
