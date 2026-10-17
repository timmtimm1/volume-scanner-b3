"""Montagem do payload: blocos isolados, JSON puro e previa legivel."""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import pytest

from scanner.config import ScannerConfig
from scanner.semana import montagem
from scanner.semana.fontes import FonteIndisponivelError, anbima, bcb, cripto, fed, treasury, yahoo
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
