"""A mensagem do Telegram com o resumo da semana (funcao pura sobre o payload)."""

from __future__ import annotations

import copy
import html
import json
import re
from pathlib import Path
from typing import Any

import pytest

from scanner.semana.mensagem import LIMITE_TELEGRAM, formatar_mensagem

FIXTURE = Path(__file__).parent / "fixtures" / "semana" / "payload_2026-10-16.json"
BASE = "https://exemplo.vercel.app"


@pytest.fixture
def payload() -> dict[str, Any]:
    return dict(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _blocos_pre(texto: str) -> list[list[str]]:
    return [
        html.unescape(bloco).split("\n") for bloco in re.findall(r"<pre>(.*?)</pre>", texto, re.S)
    ]


def test_cabecalho_com_o_primeiro_e_o_ultimo_pregao(payload: dict[str, Any]) -> None:
    texto = formatar_mensagem(payload, BASE)
    assert texto.startswith("📊 <b>Resumo da semana</b>\n13 a 16/10/2026\n")


def test_cabecalho_quando_a_semana_vira_o_mes(payload: dict[str, Any]) -> None:
    payload["semana"]["pregoes"] = ["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]
    assert "\n29/09 a 02/10/2026\n" in formatar_mensagem(payload, BASE)


def test_abertura(payload: dict[str, Any]) -> None:
    abertura = _blocos_pre(formatar_mensagem(payload, BASE))[0]
    assert abertura[0].split() == ["Ibovespa", "205.430", "-1,7%"]
    assert abertura[1].split() == ["mês", "+10,2%", "ano", "+27,5%"]
    assert abertura[2].split() == ["Dólar", "5,0966", "+1,6%"]
    assert abertura[3].split() == ["Brent", "109,86", "+4,9%"]
    assert abertura[4].split() == ["Ouro", "4.181,10", "-0,8%"]


def test_item_da_abertura_com_erro_diz_indisponivel(payload: dict[str, Any]) -> None:
    payload["abertura"]["brent"] = {"erro": "Yahoo fora do ar"}
    abertura = _blocos_pre(formatar_mensagem(payload, BASE))[0]
    assert abertura[3].split() == ["Brent", "indisponível"]
    assert "Yahoo" not in "\n".join(abertura)


def test_cinco_altas_e_cinco_quedas(payload: dict[str, Any]) -> None:
    acoes = _blocos_pre(formatar_mensagem(payload, BASE))[1]
    assert len(acoes) == 5
    esperado = [
        ("AZEV3", "+22,2%", "PTBL3", "-22,3%"),
        ("PRIO3", "+8,8%", "GFSA3", "-20,5%"),
        ("ALPA4", "+7,3%", "PLPL3", "-19,1%"),
        ("PETR4", "+6,6%", "JSLG3", "-18,2%"),
        ("TGMA3", "+6,2%", "QUAL3", "-17,7%"),
    ]
    assert [tuple(linha.split()) for linha in acoes] == esperado


def test_sem_ajuste_nao_ha_nota_de_rodape(payload: dict[str, Any]) -> None:
    assert "ajustada" not in formatar_mensagem(payload, BASE)


def test_ajustada_leva_asterisco_e_nota(payload: dict[str, Any]) -> None:
    payload["acoes"]["altas"][1]["ajustado"] = True
    texto = formatar_mensagem(payload, BASE)
    acoes = _blocos_pre(texto)[1]
    assert acoes[1].split()[:2] == ["PRIO3", "+8,8%*"]
    assert acoes[0].split()[1] == "+22,2%"
    assert "<i>* ajustada por proventos ou desdobramento</i>" in texto


def test_cinco_noticias_com_link_e_veiculos(payload: dict[str, Any]) -> None:
    texto = formatar_mensagem(payload, BASE)
    noticias = [linha for linha in texto.split("\n") if linha.startswith("• ")]
    assert len(noticias) == 5
    primeira = payload["noticias"]["historias"][0]
    assert f'<a href="{primeira["link"]}">' in noticias[0]
    assert noticias[0].endswith("</a> · InfoMoney e mais 7")


def test_fonte_sozinha_quando_so_um_veiculo(payload: dict[str, Any]) -> None:
    payload["noticias"]["historias"][0]["veiculos"] = 1
    noticias = [ln for ln in formatar_mensagem(payload, BASE).split("\n") if ln.startswith("• ")]
    assert noticias[0].endswith("</a> · InfoMoney")


def test_html_da_manchete_e_escapado(payload: dict[str, Any]) -> None:
    payload["noticias"]["historias"][0]["titulo"] = 'Vale & Petrobras <sobem> em "alta"'
    payload["noticias"]["historias"][0]["fonte"] = "A&B"
    texto = formatar_mensagem(payload, BASE)
    assert "Vale &amp; Petrobras &lt;sobem&gt; em &quot;alta&quot;" in texto
    assert "<sobem>" not in texto
    assert "A&amp;B e mais 7" in texto


def test_nome_de_empresa_e_evento_sao_escapados(payload: dict[str, Any]) -> None:
    payload["proxima_semana"]["balancos"]["confirmados"][0]["empresa"] = "A&B <X> S.A."
    payload["proxima_semana"]["agenda"][0]["evento"] = "<b>IPCA</b>"
    texto = formatar_mensagem(payload, BASE)
    assert "A&amp;B &lt;X&gt;" in texto
    assert "&lt;b&gt;IPCA&lt;/b&gt;" in texto


def test_bloco_indisponivel_mantem_o_titulo(payload: dict[str, Any]) -> None:
    payload["cripto"] = {"erro": "CoinGecko 429"}
    payload["noticias"] = {"erro": "Google fora"}
    texto = formatar_mensagem(payload, BASE)
    assert "<b>Cripto</b> · 7 dias\n<i>indisponível</i>" in texto
    assert "<b>Notícias da semana</b>\n<i>indisponível</i>" in texto
    assert "CoinGecko" not in texto


def test_cripto(payload: dict[str, Any]) -> None:
    cripto = _blocos_pre(formatar_mensagem(payload, BASE))[2]
    assert [linha.split() for linha in cripto] == [
        ["BTC", "81.289", "-1,7%"],
        ["ETH", "2.407", "-3,7%"],
    ]


def test_juros(payload: dict[str, Any]) -> None:
    juros = _blocos_pre(formatar_mensagem(payload, BASE))[3]
    assert juros[0].split() == ["taxa", "semana"]
    assert [linha.split() for linha in juros[1:]] == [
        ["Pré", "1a", "12,92%", "+34", "bp"],
        ["Pré", "10a", "13,07%", "+56", "bp"],
        ["Selic", "13,75%"],
        ["UST", "2a", "4,74%", "-6", "bp"],
        ["UST", "10a", "5,09%", "-15", "bp"],
    ]


def test_juros_com_fonte_fora_diz_indisponivel(payload: dict[str, Any]) -> None:
    payload["eua"]["treasuries"] = {"erro": "Tesouro fora"}
    payload["juros_br"]["indicadores"] = {"erro": "BCB fora"}
    juros = _blocos_pre(formatar_mensagem(payload, BASE))[3]
    assert juros[3].split() == ["Selic", "indisponível"]
    assert juros[4].split() == ["UST", "2a", "indisponível"]
    assert juros[1].split()[-1] == "bp"


def test_semana_que_vem(payload: dict[str, Any]) -> None:
    texto = formatar_mensagem(payload, BASE)
    assert "Qui 22/10 · Balanço Banco Bradesco (BBDC3, BBDC4) · após o fechamento" in texto
    assert "Sex 23/10 09:00 · IPCA-15" in texto
    assert "+3 balanços prováveis no app" in texto
    assert "Feriado" not in texto
    # Os prováveis entram so como contagem, nunca com nome.
    assert "ROMI" not in texto.upper()


def test_consenso_do_focus_e_feriado(payload: dict[str, Any]) -> None:
    payload["proxima_semana"]["agenda"][0]["consenso"] = {
        "mediana": 13.5,
        "unidade": "% a.a.",
        "fonte": "Focus",
        "data": "2026-10-16",
    }
    payload["proxima_semana"]["agenda"][0]["evento"] = "Copom: decisão"
    payload["proxima_semana"]["feriados_b3"] = ["2026-11-20"]
    texto = formatar_mensagem(payload, BASE)
    assert "Copom: decisão (Focus 13,50%)" in texto
    assert "Feriado na B3: 20/11" in texto


def test_semana_que_vem_vazia(payload: dict[str, Any]) -> None:
    prox = payload["proxima_semana"]
    prox["agenda"] = []
    prox["balancos"] = {"confirmados": [], "provaveis": [], "avisos": []}
    assert "<b>Semana que vem</b>\n<i>nada na agenda</i>" in formatar_mensagem(payload, BASE)


def test_link_do_app_usa_a_sexta_e_ignora_barra_final(payload: dict[str, Any]) -> None:
    texto = formatar_mensagem(payload, BASE + "/")
    assert texto.endswith(f'<a href="{BASE}/semana/2026-10-16">Resumo completo no app</a>')


def test_linhas_do_pre_cabem_em_32_colunas(payload: dict[str, Any]) -> None:
    payload["acoes"]["altas"][0]["ticker"] = "BPAC11"
    payload["acoes"]["quedas"][0]["ticker"] = "TAEE11"
    payload["acoes"]["altas"][0]["ajustado"] = True
    payload["acoes"]["quedas"][0]["ajustado"] = True
    blocos = _blocos_pre(formatar_mensagem(payload, BASE))
    assert len(blocos) == 4
    for bloco in blocos:
        for linha in bloco:
            assert len(linha) <= 32, linha


def test_tamanho_abaixo_do_limite_do_telegram(payload: dict[str, Any]) -> None:
    assert len(formatar_mensagem(payload, BASE)) < LIMITE_TELEGRAM


def test_manchetes_enormes_cortam_noticias_do_fim(payload: dict[str, Any]) -> None:
    for historia in payload["noticias"]["historias"]:
        historia["titulo"] = "x" * 900
    texto = formatar_mensagem(payload, BASE)
    assert len(texto) < LIMITE_TELEGRAM
    noticias = [ln for ln in texto.split("\n") if ln.startswith("• ")]
    assert 0 < len(noticias) < 5
    # Cortou do fim: as que ficaram sao as primeiras.
    primeiras = payload["noticias"]["historias"][: len(noticias)]
    assert [h["link"] for h in primeiras] == re.findall(r'<a href="([^"]+)">x', texto)[
        : len(noticias)
    ]
    # O resto da mensagem continua inteiro.
    assert "<b>Juros</b>" in texto and "Resumo completo no app" in texto


def test_nao_altera_o_payload(payload: dict[str, Any]) -> None:
    antes = copy.deepcopy(payload)
    formatar_mensagem(payload, BASE)
    assert payload == antes
