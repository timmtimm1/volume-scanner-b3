"""Montagem do payload: blocos isolados, JSON puro e previa legivel."""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from scanner.config import ScannerConfig
from scanner.semana import agenda, balancos, montagem
from scanner.semana.fontes import (
    FonteIndisponivelError,
    anbima,
    bcb,
    cripto,
    fed,
    google_noticias,
    treasury,
    yahoo,
)
from scanner.semana.montagem import (
    PregaoAusenteError,
    _limpo,
    montar_dados_de_mercado,
    previa,
)
from scanner.semana.periodo import semana_da_data
from scanner.storage import repository

SEMANA = semana_da_data(date(2026, 10, 16))
AGORA = datetime(2026, 10, 17, 19, 0, tzinfo=UTC)
ENGINE: Any = object()


def _acao(ticker: str, variacao: float, **extra: Any) -> dict[str, Any]:
    base = {
        "ticker": ticker,
        "data_inicio": "2026-10-09",
        "preco_inicio": 10.0,
        "data_fim": "2026-10-16",
        "preco_fim": 11.0,
        "variacao": variacao,
        "variacao_bruta": variacao,
        "proventos_por_acao": 0.0,
        "multiplicador": 1.0,
        "ajustado": False,
        "conferido": True,
        "eventos_sem_ajuste": None,
    }
    return {**base, **extra}


BLOCO_ACOES = {
    "altas": [_acao("AAAA3", 0.1)],
    "quedas": [
        _acao(
            "BBBB3",
            -0.02,
            ajustado=True,
            variacao_bruta=-0.5,
            multiplicador=2.0,
            proventos_por_acao=0.3,
            conferido=False,
        )
    ],
    "fora_do_ranking": [
        _acao("CCCC3", float("nan"), variacao_bruta=-0.3, eventos_sem_ajuste="CIS RED CAP")
    ],
    "avaliados": 3,
    "conferidos": 2,
    "falhas_b3": ["DDDD"],
}


EVENTO = {
    "data": "2026-10-23",
    "hora": "09:00",
    "pais": "BR",
    "evento": "IPCA-15",
    "detalhe": "outubro",
    "consenso": None,
    "fonte": "IBGE",
}
BLOCO_BALANCOS = {
    "confirmados": [
        {
            "empresa": "BANCO BRADESCO S.A.",
            "cd_cvm": 906,
            "tickers": ["BBDC3", "BBDC4"],
            "data": "2026-10-22",
            "horario": "após o fechamento",
            "trimestre": "3T26",
            "fonte": "Nasdaq",
        }
    ],
    "provaveis": [
        {
            "empresa": "WEG SA",
            "cd_cvm": 5410,
            "tickers": ["WEGE3"],
            "documento": "ITR 3T25",
            "entregue_em": "2025-10-22",
        }
    ],
    "avisos": [],
}


def vivo_agenda(falhas: dict[str, Exception]) -> Any:
    def f(*_a: Any, **_k: Any) -> tuple[list[dict[str, Any]], list[str]]:
        if "agenda" in falhas:
            raise falhas["agenda"]
        return [EVENTO], ["Focus indisponível (HTTP 503): eventos sem consenso"]

    return f


def _coletar_noticias(falhas: dict[str, Exception]) -> Any:
    xml = (Path(__file__).parent / "fixtures" / "semana" / "google_busca_deficit.xml").read_text()

    def f(*_a: Any, **_k: Any) -> tuple[list[Any], list[str]]:
        if "noticias" in falhas:
            raise falhas["noticias"]
        return google_noticias.ler_rss(xml), ["busca 'Fed' falhou: HTTP 503"]

    return f


def _patch_fontes(monkeypatch: pytest.MonkeyPatch, **falhas: Exception) -> None:
    def vivo(nome: str, valor: dict[str, Any]) -> Any:
        def f(*_a: Any, **_k: Any) -> dict[str, Any]:
            if nome in falhas:
                raise falhas[nome]
            return valor

        return f

    ativo = {"valor": 1.0, "data": "2026-10-16", "semana": 0.01, "mes": None, "ano": 0.2}
    monkeypatch.setattr(repository, "existe_barra_em", lambda *_a: True)
    monkeypatch.setattr(montagem, "_bloco_acoes", lambda *_a: BLOCO_ACOES)
    monkeypatch.setattr(
        yahoo,
        "abertura",
        vivo("abertura", dict.fromkeys(("ibovespa", "dolar", "brent", "ouro"), ativo)),
    )
    monkeypatch.setattr(cripto, "buscar_cripto", vivo("cripto", {"moedas": []}))
    monkeypatch.setattr(
        anbima,
        "curva_prefixada",
        vivo("curva", {"data": "2026-10-16", "data_anterior": "2026-10-09", "vertices": []}),
    )
    monkeypatch.setattr(
        bcb,
        "indicadores",
        vivo(
            "indicadores",
            {
                "selic_meta": 13.75,
                "cdi_mes": 0.005,
                "cdi_ano": 0.11,
                "cdi_data": "2026-10-15",
                "ipca_12m": 4.58,
                "ipca_referencia": "2026-09",
            },
        ),
    )
    monkeypatch.setattr(
        treasury,
        "treasuries",
        vivo(
            "treasuries", {"data": "2026-10-16", "data_anterior": "2026-10-09", "vencimentos": []}
        ),
    )
    monkeypatch.setattr(montagem, "load_universe", lambda *_a: pd.DataFrame())
    monkeypatch.setattr(google_noticias, "coletar", _coletar_noticias(falhas))
    monkeypatch.setattr(agenda, "montar_agenda", vivo_agenda(falhas))
    monkeypatch.setattr(balancos, "montar_balancos", vivo("balancos", BLOCO_BALANCOS))
    monkeypatch.setattr(
        fed,
        "dot_plot",
        vivo(
            "fed", {"data_projecao": "2026-09-16", "medianas": [{"periodo": "2026", "taxa": 4.1}]}
        ),
    )


def test_sem_o_pregao_final_levanta_pregao_ausente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repository, "existe_barra_em", lambda *_a: False)

    with pytest.raises(PregaoAusenteError, match="2026-10-16"):
        montar_dados_de_mercado(ENGINE, ScannerConfig(), SEMANA, agora=AGORA)


def test_payload_completo_e_json_puro(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fontes(monkeypatch)

    payload = montar_dados_de_mercado(ENGINE, ScannerConfig(), SEMANA, agora=AGORA)

    # allow_nan=False: NaN no payload quebraria o JSONB e o site.
    json.dumps(payload, allow_nan=False)
    assert payload["versao"] == 1
    assert payload["semana"] == {
        "sexta": "2026-10-16",
        "inicio": "2026-10-09",
        "fim": "2026-10-16",
        "pregoes": ["2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"],
    }
    assert payload["gerado_em"] == "2026-10-17T19:00:00+00:00"
    assert payload["acoes"]["falhas_b3"] == ["DDDD"]
    assert payload["acoes"]["fora_do_ranking"][0]["variacao"] is None  # NaN virou null
    assert set(payload["abertura"]) == {"ibovespa", "dolar", "brent", "ouro"}
    assert payload["juros_br"]["indicadores"]["selic_meta"] == 13.75
    assert payload["eua"]["fed"]["medianas"][0]["taxa"] == 4.1


@pytest.mark.parametrize(
    "falha",
    [FonteIndisponivelError("coingecko", "HTTP 429"), RuntimeError("bug de parse")],
)
def test_bloco_que_falha_nao_derruba_o_resto(
    monkeypatch: pytest.MonkeyPatch, falha: Exception
) -> None:
    _patch_fontes(monkeypatch, cripto=falha, fed=falha)

    payload = montar_dados_de_mercado(ENGINE, ScannerConfig(), SEMANA, agora=AGORA)

    assert "erro" in payload["cripto"]
    assert "erro" in payload["eua"]["fed"]
    assert "erro" not in payload["eua"]["treasuries"]
    assert payload["acoes"]["avaliados"] == 3
    if isinstance(falha, FonteIndisponivelError):
        assert payload["cripto"]["erro"] == "HTTP 429"


def test_limpo_converte_nan_numpy_e_datas() -> None:
    sujo = {
        "a": float("nan"),
        "b": np.float64(1.5),
        "c": np.int64(3),
        "d": np.bool_(True),
        "e": [date(2026, 10, 16), math.inf],
        "f": (1, None),
    }

    assert _limpo(sujo) == {
        "a": None,
        "b": 1.5,
        "c": 3,
        "d": True,
        "e": ["2026-10-16", None],
        "f": [1, None],
    }


def test_previa_mostra_cada_bloco_e_o_motivo_de_quem_falhou(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fontes(monkeypatch, cripto=FonteIndisponivelError("coingecko", "HTTP 429"))
    payload = montar_dados_de_mercado(ENGINE, ScannerConfig(), SEMANA, agora=AGORA)

    texto = previa(payload)

    assert "RESUMO DA SEMANA DE 16/10/2026" in texto
    assert "base 09/10/2026 -> fim 16/10/2026, 4 pregoes" in texto
    assert "AAAA3" in texto
    assert "+10,0%" in texto
    assert "eventos NAO conferidos" in texto  # BBBB3
    assert "ajustada: bruta -50,0%" in texto
    assert "B3 sem resposta para 1 emissores: DDDD" in texto
    assert "Fora do ranking" in texto
    assert "(CIS RED CAP)" in texto
    assert "CRIPTO\n  indisponivel: HTTP 429" in texto
    assert "Selic meta 13,75% a.a." in texto
    assert "CDI acumulado: mes +0,50%, ano +11,00% (ate 15/10/2026)" in texto
    assert "Fed, mediana dos juros (16/09/2026): 2026 4,1%" in texto


def test_proxima_semana_no_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fontes(monkeypatch)

    bloco = montar_dados_de_mercado(ENGINE, ScannerConfig(), SEMANA, agora=AGORA)["proxima_semana"]

    assert bloco["inicio"] == "2026-10-19" and bloco["fim"] == "2026-10-23"
    assert bloco["feriados_b3"] == []
    assert bloco["agenda"] == [EVENTO]
    assert bloco["agenda_avisos"] == ["Focus indisponível (HTTP 503): eventos sem consenso"]
    assert bloco["balancos"]["confirmados"][0]["tickers"] == ["BBDC3", "BBDC4"]


def test_feriado_de_novembro_aparece_como_dia_util_sem_pregao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fontes(monkeypatch)
    semana = semana_da_data(date(2026, 11, 13))  # a seguinte, 16 a 20/11, tem o 20/11

    bloco = montar_dados_de_mercado(ENGINE, ScannerConfig(), semana, agora=AGORA)["proxima_semana"]

    assert bloco["feriados_b3"] == ["2026-11-20"]


def test_agenda_que_cai_nao_derruba_balancos_nem_o_resto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fontes(monkeypatch, agenda=FonteIndisponivelError("ibge", "HTTP 500"))

    payload = montar_dados_de_mercado(ENGINE, ScannerConfig(), SEMANA, agora=AGORA)

    bloco = payload["proxima_semana"]
    assert bloco["agenda"] == []
    assert bloco["agenda_avisos"] == ["agenda indisponível: HTTP 500"]
    assert bloco["balancos"]["confirmados"]
    assert payload["eua"]["fed"]["data_projecao"] == "2026-09-16"


def test_balancos_que_caem_viram_erro_e_a_agenda_segue(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fontes(monkeypatch)

    def cai(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise RuntimeError("banco fora")

    monkeypatch.setattr(balancos, "montar_balancos", cai)

    bloco = montar_dados_de_mercado(ENGINE, ScannerConfig(), SEMANA, agora=AGORA)["proxima_semana"]

    assert bloco["balancos"] == {"erro": "erro inesperado (RuntimeError: banco fora)"}
    assert bloco["agenda"] == [EVENTO]


def test_previa_da_semana_que_vem(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fontes(monkeypatch, cripto=FonteIndisponivelError("coingecko", "HTTP 429"))
    payload = montar_dados_de_mercado(ENGINE, ScannerConfig(), SEMANA, agora=AGORA)
    payload["proxima_semana"]["agenda"][0]["consenso"] = {
        "mediana": 0.45,
        "unidade": "%",
        "fonte": "Focus",
        "data": "2026-10-16",
    }

    texto = previa(payload)

    assert "SEMANA QUE VEM (19/10 a 23/10)" in texto
    assert "Feriados B3 (dia útil sem pregão): nenhum" in texto
    assert "  Sex 23/10  09:00  BR  IPCA-15 (outubro)   Focus: 0,45%" in texto
    assert "AVISO: Focus indisponível (HTTP 503)" in texto
    assert "Qui 22/10  após o fechamento  BANCO BRADESCO S.A. (BBDC3, BBDC4)" in texto
    assert "trimestre 3T26   [Nasdaq]" in texto
    assert "WEG SA (WEGE3)   ITR 3T25 entregue em 22/10/2025" in texto


def test_previa_com_balancos_indisponiveis(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fontes(monkeypatch, cripto=FonteIndisponivelError("coingecko", "HTTP 429"))
    payload = montar_dados_de_mercado(ENGINE, ScannerConfig(), SEMANA, agora=AGORA)
    payload["proxima_semana"]["balancos"] = {"erro": "banco fora"}

    assert "Balanços: indisponivel: banco fora" in previa(payload)


def test_bloco_de_noticias_traz_janela_historias_contagem_e_avisos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fontes(monkeypatch)

    bloco = montar_dados_de_mercado(ENGINE, ScannerConfig(), SEMANA, agora=AGORA)["noticias"]

    assert bloco["janela"] == {
        "de": "2026-10-12T03:00:00+00:00",
        "ate": "2026-10-17T19:00:00+00:00",
    }
    assert bloco["buscas"] == ScannerConfig().semana.noticias_buscas
    assert bloco["contagem"]["recebidas"] == 6
    assert set(bloco["contagem"]["descartes"]) == {
        "boletim_diario",
        "nao_e_noticia",
        "fora_da_imprensa",
        "fora_da_semana",
    }
    assert bloco["avisos"] == ["busca 'Fed' falhou: HTTP 503"]
    assert {"titulo", "fonte", "link", "publicada_em", "veiculos", "outras_fontes"} <= set(
        bloco["historias"][0]
    )
    json.dumps(bloco, allow_nan=False)


def test_noticias_indisponiveis_nao_derrubam_o_resumo(monkeypatch: pytest.MonkeyPatch) -> None:
    falha = FonteIndisponivelError("google_noticias", "todas as consultas falharam (HTTP 503)")
    _patch_fontes(monkeypatch, noticias=falha, cripto=FonteIndisponivelError("c", "x"))

    payload = montar_dados_de_mercado(ENGINE, ScannerConfig(), SEMANA, agora=AGORA)
    texto = previa(payload)

    assert payload["noticias"] == {"erro": "todas as consultas falharam (HTTP 503)"}
    assert "NOTÍCIAS DA SEMANA\n  indisponivel: todas as consultas falharam" in texto


def test_previa_das_noticias(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fontes(monkeypatch, cripto=FonteIndisponivelError("coingecko", "HTTP 429"))
    payload = montar_dados_de_mercado(ENGINE, ScannerConfig(), SEMANA, agora=AGORA)

    texto = previa(payload)

    assert "NOTÍCIAS DA SEMANA" in texto
    assert " veículos | " in texto
    assert "6 recebidas, 6 distintas, 6 na semana, 6 na imprensa" in texto
    assert (
        "descartes: boletim diário 0, não é notícia 0, fora da imprensa 0, fora da semana 0"
        in texto
    )
    assert "AVISO: busca 'Fed' falhou: HTTP 503" in texto
