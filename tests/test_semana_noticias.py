"""Noticias da semana: RSS do Google, filtros e agrupamento por historia.

As fixtures sao recortes de respostas reais do Google Noticias de 17/10/2026
(secao Negocios e buscas), sem o <description>, que o parser nao usa.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from scanner.semana import noticias as sn
from scanner.semana.fontes import FonteIndisponivelError
from scanner.semana.fontes.google_noticias import (
    Noticia,
    coletar,
    ler_rss,
    url_da_busca,
)

FIXTURES = Path(__file__).parent / "fixtures" / "semana"
NOTICIAS_TS = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "noticias.ts"

SEGUNDA = date(2026, 10, 12)
INICIO = sn.inicio_da_semana(SEGUNDA)
COLETA = datetime(2026, 10, 17, 21, 0, tzinfo=UTC)


def _rss(nome: str) -> list[Noticia]:
    return ler_rss((FIXTURES / f"google_{nome}.xml").read_text(encoding="utf-8"))


def _todas() -> list[Noticia]:
    return [n for f in sorted(FIXTURES.glob("google_*.xml")) for n in ler_rss(f.read_text())]


def _n(
    titulo: str, fonte: str = "InfoMoney", dominio: str = "infomoney.com.br", **kw: object
) -> Noticia:
    horas = kw.get("horas", 0)
    assert isinstance(horas, int | float)
    return Noticia(
        titulo=titulo,
        fonte=fonte,
        dominio=dominio,
        link=str(kw.get("link", f"https://x/{titulo}/{fonte}")),
        publicada_em=datetime(2026, 10, 14, 12, tzinfo=UTC) + timedelta(hours=horas),
    )


def _fundo(quantas: int = 30) -> list[Noticia]:
    """Manchetes sem palavra em comum: o IDF precisa de um conjunto grande para pesar.

    Com 2 manchetes, toda palavra repetida tem df = N e idf 0; nos ~400 titulos
    reais da semana a palavra que so 2 veiculos usaram pesa muito.
    """
    return [
        _n(f"assunto{i} topico{i} caso{i} evento{i} tema{i}", fonte=f"Fundo {i}")
        for i in range(quantas)
    ]


def _repetidas(historias: list[dict[str, object]]) -> list[dict[str, object]]:
    return [h for h in historias if h["veiculos"] != 1]


# --- ler_rss ----------------------------------------------------------------


def test_ler_rss_do_topico() -> None:
    itens = _rss("topico")

    assert len(itens) == 8
    ig = itens[0]
    # O titulo real do Google vem quebrado em duas linhas; o sufixo " - Portal iG" sai.
    assert ig.titulo == "Carro\nvoador da Tesla vira meme nas redes sociais; confira"
    assert ig.fonte == "Portal iG"
    assert ig.dominio == "carros.ig.com.br"
    assert ig.link.startswith("https://news.google.com/rss/articles/")
    assert ig.publicada_em == datetime(2026, 10, 17, 9, 0, tzinfo=UTC)


def test_ler_rss_decodifica_entidade_e_tira_so_o_sufixo_exato() -> None:
    (n,) = _rss("busca_juros")

    assert (
        n.titulo
        == "Futuros do Nasdaq caem com temor sobre IA e juros nos EUA; Dow Jones e S&P 500 divergem"
    )
    assert n.fonte == "ADVFN"
    assert n.dominio == "br.advfn.com"

    # Titulo com " - " da propria manchete e fonte diferente do sufixo: nada e cortado.
    xml = (
        "<item><title>Alta - de juros &#39;forte&#39; - Outra Coisa</title><link>https://a/1</link>"
        "<pubDate>Fri, 16 Oct 2026 18:13:09 GMT</pubDate>"
        '<source url="https://www.exemplo.com.br">Fonte X</source></item>'
    )
    (m,) = ler_rss(xml)
    assert m.titulo == "Alta - de juros 'forte' - Outra Coisa"
    assert m.dominio == "exemplo.com.br"  # sem "www."


def test_ler_rss_ignora_item_incompleto_ou_com_data_ruim() -> None:
    sem_fonte = (
        "<item><title>T</title><link>https://a/1</link>"
        "<pubDate>Fri, 16 Oct 2026 18:13:09 GMT</pubDate></item>"
    )
    data_ruim = (
        "<item><title>T</title><link>https://a/2</link><pubDate>ontem</pubDate>"
        '<source url="https://a.com">A</source></item>'
    )
    assert ler_rss(sem_fonte + data_ruim) == []


def test_fixtures_trazem_fonte_fora_da_imprensa_boletim_e_link_repetido() -> None:
    todas = _todas()

    assert any(n.dominio == "agenciabrasil.ebc.com.br" for n in todas)
    assert any(sn.boletim_diario(n.titulo) for n in todas)
    links = [n.link for n in todas]
    assert len(links) > len(set(links))  # a materia do g1 vem no topico e na busca


# --- coleta -----------------------------------------------------------------


def test_url_da_busca_usa_datas_absolutas_em_volta_da_semana() -> None:
    url = url_da_busca('Fed OR "Federal Reserve"', SEGUNDA)

    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "after%3A2026-10-11" in url and "before%3A2026-10-18" in url
    assert "when" not in url
    assert url.endswith("hl=pt-BR&gl=BR&ceid=BR:pt-419")


def _cliente(responder: dict[str, int]) -> httpx.Client:
    xml = (FIXTURES / "google_busca_deficit.xml").read_text()

    def handler(req: httpx.Request) -> httpx.Response:
        for trecho, status in responder.items():
            if trecho in str(req.url):
                return httpx.Response(status, text=xml if status == 200 else "")
        return httpx.Response(200, text=xml)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_coletar_junta_topico_e_buscas_e_busca_que_falha_vira_aviso() -> None:
    itens, avisos = coletar(["Ibovespa", "juros"], SEGUNDA, cliente=_cliente({"juros": 503}))

    assert len(itens) == 12  # topico + Ibovespa, 6 itens cada (o mesmo XML)
    assert avisos == ["busca 'juros' falhou: HTTP 503"]


def test_coletar_so_levanta_quando_todas_falham() -> None:
    with pytest.raises(FonteIndisponivelError, match="todas as consultas falharam"):
        coletar(["Ibovespa"], SEGUNDA, cliente=_cliente({"news.google.com": 503}))


# --- filtros ----------------------------------------------------------------


def test_janela_comeca_na_segunda_a_meia_noite_de_brasilia() -> None:
    assert datetime(2026, 10, 12, 3, 0, tzinfo=UTC) == INICIO


def test_fontes_iguais_as_do_site() -> None:
    """Mudou web/src/lib/noticias.ts, mude src/scanner/semana/noticias.py."""
    ts = NOTICIAS_TS.read_text(encoding="utf-8")

    def conjunto(nome: str) -> frozenset[str]:
        achado = re.search(rf"const {nome} = new Set\(\[(.*?)\]\)", ts, re.DOTALL)
        assert achado, f"{nome} nao encontrado em noticias.ts"
        return frozenset(re.findall(r'"([^"]+)"', achado.group(1)))

    assert conjunto("FONTES_FINANCEIRAS") == sn.FONTES_FINANCEIRAS
    assert conjunto("FONTES_GERAIS") == sn.FONTES_GERAIS


def test_nao_e_noticia_pega_cotacao_titulo_curto_e_loteria() -> None:
    assert sn.nao_e_noticia("Petrobras (PETR4): Resultados, Dividendos, Cotação e mais")
    assert sn.nao_e_noticia("Alpargatas (ALPA4) hoje")  # menos de 4 palavras
    # Medido: entrou pela busca "economia" e e da imprensa financeira.
    assert sn.nao_e_noticia("Mega-Sena acumulada em R$ 150 milhões: veja quanto a bolada renderia")
    assert sn.nao_e_noticia("Resultado da Quina de hoje: veja números e ganhadores do concurso")
    assert not sn.nao_e_noticia(
        "Focus eleva projeção de inflação para 5,2% em 2026; reduz câmbio e Selic"
    )


def test_boletim_diario_cai_e_noticia_sobre_o_assunto_fica() -> None:
    cai = [
        "Ibovespa fecha negativo, com eleição e dados de inflação; dólar vale R$ 5,02",
        "Ibovespa Futuro cai com foco em pesquisas eleitorais e aprovação do fim da 6\u00d71",
        "Ibovespa Fecha em Alta Moderada em Mais um Pregão Marcado por Pesquisas Eleitorais",
        "Boletim Focus: Mercado espera taxa Selic em 13,25% neste ano",
        "Boletim Focus eleva projeção de inflação para 5,22% em 2026 e reduz câmbio",
        "Focus: mercado eleva previsão da inflação para 5,22% em 2026 e reduz estimativa da Selic",
        "Ibovespa volta a subir, após três quedas, mas semana termina no negativo; Dólar cai",
        # O fechamento com palavras no meio, que a primeira versao deixava passar.
        "Ibovespa devolve perdas e fecha no zero com Petrobras em alta",
        "Dólar à vista sobe e fecha a semana acima de R$ 5,10",
    ]
    fica = [
        "Ibovespa nos 240 mil pontos? Por que o Inter diz que \u2018não é hora de vender bolsa'",
        "Focus eleva projeção de inflação para 5,2% em 2026; reduz câmbio e Selic",
        "Potencial de alta do Ibovespa, IPCA e balanços dos EUA; veja destaques da semana",
        "Déficit das contas públicas dos EUA sobe a US$ 1,99 trilhão, maior em 5 anos",
    ]
    assert all(sn.boletim_diario(t) for t in cai)
    assert not any(sn.boletim_diario(t) for t in fica)


def test_cada_filtro_conta_o_proprio_descarte_na_ordem() -> None:
    antes = _n("Mercado financeiro discute política monetária hoje", horas=-24 * 4)
    depois = _n("Mercado financeiro discute política monetária depois", horas=24 * 6)
    fora = _n(
        "Mercado financeiro discute política monetária fora", fonte="Blog", dominio="blog.com.br"
    )
    loteria = _n(
        "Mega-Sena acumulada em R$ 150 milhões: veja o prêmio",
        fonte="BPMoney",
        dominio="bpmoney.com.br",
    )
    boletim = _n("Ibovespa fecha em queda com juros nos EUA e eleição")
    boa = _n("Governo anuncia pacote fiscal com corte de gastos")
    duplicada = _n("Governo anuncia pacote fiscal com corte de gastos", link=boa.link)

    historias, c = sn.selecionar(
        [antes, depois, fora, loteria, boletim, boa, duplicada], INICIO, COLETA, 8
    )

    assert [h["titulo"] for h in historias] == [boa.titulo]
    assert c == {
        "recebidas": 7,
        "distintas": 6,
        "na_semana": 4,  # fora_da_semana tirou 2
        "na_imprensa": 3,
        "descartes": {
            "boletim_diario": 1,
            "nao_e_noticia": 1,
            "fora_da_imprensa": 1,
            "fora_da_semana": 2,
        },
    }


# --- agrupamento ------------------------------------------------------------


def test_idf_agrupa_a_dupla_do_deficit_e_conta_veiculos() -> None:
    historias, _ = sn.selecionar(_todas(), INICIO, COLETA, 8)

    topo = historias[0]
    assert "déficit" in topo["titulo"].lower() and "EUA" in topo["titulo"]
    assert topo["veiculos"] == 6
    fontes = {topo["fonte"], *(o["fonte"] for o in topo["outras_fontes"])}
    # As duas manchetes do enunciado, de veiculos que escreveram diferente, na mesma historia.
    assert {"ADVFN", "Folha de S.Paulo", "G1", "O GLOBO"} <= fontes
    # A fonte do representante nao se repete em `outras_fontes`.
    assert topo["fonte"] not in {o["fonte"] for o in topo["outras_fontes"]}


def test_representante_e_a_primeira_de_fonte_financeira() -> None:
    geral = _n(
        "Governo anuncia pacote fiscal com corte de gastos", fonte="G1", dominio="g1.globo.com"
    )
    fin = _n(
        "Pacote fiscal do governo prevê corte de gastos públicos",
        fonte="Valor",
        dominio="valor.globo.com",
        horas=1,
    )

    historias, _ = sn.selecionar([geral, fin, *_fundo()], INICIO, COLETA, 50)
    (h,) = _repetidas(historias)

    assert h["fonte"] == "Valor"
    assert h["outras_fontes"] == [{"fonte": "G1", "link": geral.link}]
    assert h["publicada_em"] == fin.publicada_em.isoformat()  # a mais recente do grupo


def test_ibovespa_de_assuntos_diferentes_nao_gruda() -> None:
    a = _n("Ibovespa nos 240 mil pontos? Por que o Inter diz que não é hora de vender bolsa")
    b = _n(
        "Potencial de alta do Ibovespa, IPCA e balanços dos EUA; veja destaques da semana",
        fonte="Valor",
    )
    c = _n("Petrobras (PETR4) lidera alta do Ibovespa após anúncio de dividendos", fonte="Exame")
    # "Ibovespa" aparece em todas; o IDF so conta o que e raro. O pano de fundo
    # mantem "ibovespa" comum, como nos ~400 titulos reais da semana.
    fundo = [
        _n(f"Ibovespa e dólar com juros e eleição no radar número {i}", fonte=f"F{i}")
        for i in range(20)
    ]

    historias, _ = sn.selecionar([a, b, c, *fundo], INICIO, COLETA, 50)

    titulos = {h["titulo"] for h in historias}
    assert {a.titulo, b.titulo, c.titulo} <= titulos


def test_manchetes_parecidas_de_dias_distantes_sao_eventos_distintos() -> None:
    titulo = "BC mantém Selic em 13,75% e sinaliza cautela com inflação"
    perto = [
        _n(titulo, fonte="A", dominio="infomoney.com.br"),
        _n(titulo, fonte="B", dominio="exame.com", horas=47),
    ]
    longe = [
        _n(titulo, fonte="A", dominio="infomoney.com.br"),
        _n(titulo, fonte="B", dominio="exame.com", horas=49),
    ]

    h_perto, _ = sn.selecionar([*perto, *_fundo()], INICIO, COLETA, 50)
    h_longe, _ = sn.selecionar([*longe, *_fundo()], INICIO, COLETA, 50)

    assert [h["veiculos"] for h in _repetidas(h_perto)] == [2]
    assert _repetidas(h_longe) == []


def test_ranking_veiculos_depois_manchetes_depois_recencia() -> None:
    a = "Petrobras anuncia nova descoberta de petróleo na Margem Equatorial"
    b = "Câmara aprova texto-base da reforma do imposto de renda"
    c = "Tesouro Direto bate recorde de investidores cadastrados"
    d = "Vale fecha acordo de indenização por Mariana com governo federal"
    itens = [
        # a: 2 veiculos, 3 manchetes (uma fonte repetida)
        _n(a, fonte="A1", horas=0),
        _n(a, fonte="A2", dominio="exame.com", horas=1),
        _n(a + " hoje", fonte="A1", dominio="infomoney.com.br", horas=2, link="https://x/a3"),
        # b: 2 veiculos, 2 manchetes, mais recente que a
        _n(b, fonte="B1", horas=10),
        _n(b, fonte="B2", dominio="exame.com", horas=11),
        # c: 2 veiculos, 2 manchetes, mais antiga que b
        _n(c, fonte="C1", horas=5),
        _n(c, fonte="C2", dominio="exame.com", horas=6),
        # d: 3 veiculos
        _n(d, fonte="D1", horas=20),
        _n(d, fonte="D2", dominio="exame.com", horas=21),
        _n(d, fonte="D3", dominio="valor.globo.com", horas=22),
    ]

    historias, _ = sn.selecionar([*itens, *_fundo()], INICIO, COLETA, 3)

    assert [h["veiculos"] for h in historias] == [3, 2, 2]
    assert historias[0]["titulo"] == d
    assert historias[1]["titulo"] == a  # 3 manchetes ganha de 2
    assert historias[2]["titulo"] == b  # empate total: a mais recente primeiro


def test_sem_nada_na_semana_devolve_lista_vazia() -> None:
    historias, c = sn.selecionar([], INICIO, COLETA, 8)

    assert historias == []
    assert c["recebidas"] == 0


def test_config_das_noticias(repo_config_path: Path) -> None:
    from pydantic import ValidationError

    from scanner.config import SemanaConfig, load_config

    cfg = load_config(repo_config_path).semana
    assert cfg.noticias_top == 8
    assert cfg.noticias_buscas == SemanaConfig().noticias_buscas  # yaml e padrao iguais
    with pytest.raises(ValidationError):
        SemanaConfig(noticias_top=0)
    with pytest.raises(ValidationError):
        SemanaConfig(noticias_buscas=[])
