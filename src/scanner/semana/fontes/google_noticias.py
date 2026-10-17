"""Google Noticias (RSS gratuito): a secao Negocios do Brasil e buscas da semana.

E a mesma fonte da aba Noticias da ficha (`web/src/lib/noticias.ts`) e `ler_rss`
e o porte fiel do `lerRss` de la. Aqui o uso e outro: nao ha empresa para achar,
so as manchetes mais repetidas da semana em economia e mercado.

Medido em 17/10/2026: a secao Negocios devolve 70 itens e cada busca ate 100. As
buscas levam datas ABSOLUTAS (`after:` e `before:`) e nao `when:7d`, para a
edicao de uma semana antiga poder ser montada depois.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlparse

import httpx

from scanner.semana.fontes import FonteIndisponivelError, baixar

FONTE = "google_noticias"
BASE = "https://news.google.com/rss"
PARAMETROS = "hl=pt-BR&gl=BR&ceid=BR:pt-419"
URL_TOPICO = f"{BASE}/headlines/section/topic/BUSINESS?{PARAMETROS}"
# O mesmo User-Agent que o site usa para o Google: o de navegador tambem passa,
# mas este identifica o projeto.
USER_AGENT = "Mozilla/5.0 (compatible; volume-scanner-b3)"


@dataclass(frozen=True)
class Noticia:
    titulo: str  # sem o " - Fonte" que o Google agrega ao final
    fonte: str  # nome da fonte, como o <source> escreve
    dominio: str  # host do <source url>, sem "www."
    link: str
    publicada_em: datetime  # com fuso (o RSS manda GMT)


def _entidades(s: str) -> str:
    """As entidades XML do RSS, na mesma ordem do site (&amp; por ultimo)."""
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    s = s.replace("&#39;", "'").replace("&apos;", "'")
    s = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), s)
    return s.replace("&amp;", "&")


def _dominio(link: str) -> str:
    try:
        host = urlparse(link).hostname or ""
    except ValueError:
        return ""
    return host.removeprefix("www.")


def ler_rss(xml: str) -> list[Noticia]:
    """Os <item> do RSS. Parser por regex como o do site: o formato e fixo."""
    noticias: list[Noticia] = []
    for item in re.findall(r"<item>[\s\S]*?</item>", xml):
        titulo_bruto = re.search(r"<title>([\s\S]*?)</title>", item)
        link_bruto = re.search(r"<link>([\s\S]*?)</link>", item)
        data_bruta = re.search(r"<pubDate>([\s\S]*?)</pubDate>", item)
        fonte_bruta = re.search(r'<source url="([^"]*)">([\s\S]*?)</source>', item)
        if not (titulo_bruto and link_bruto and data_bruta and fonte_bruta):
            continue
        if not (titulo_bruto.group(1) and link_bruto.group(1) and data_bruta.group(1)):
            continue
        if not fonte_bruta.group(2):
            continue

        completo = _entidades(titulo_bruto.group(1).strip())
        fonte = _entidades(fonte_bruta.group(2).strip())
        link = _entidades(link_bruto.group(1).strip())
        try:
            publicada = parsedate_to_datetime(data_bruta.group(1).strip())
        except (TypeError, ValueError):
            continue
        # Tirar so o sufixo exato evita cortar um " - " que seja parte da manchete.
        sufixo = f" - {fonte}"
        titulo = completo.removesuffix(sufixo)
        noticias.append(
            Noticia(
                titulo=titulo,
                fonte=fonte,
                dominio=_dominio(_entidades(fonte_bruta.group(1))) or _dominio(link),
                link=link,
                publicada_em=publicada,
            )
        )
    return noticias


def url_da_busca(termo: str, segunda: date) -> str:
    """Busca com datas absolutas: `after:` e o domingo, `before:` o domingo seguinte.

    O Google trata `after` e `before` como limites exclusivos de dia, entao a
    janela segunda..sabado precisa do dia antes e do dia depois. Quem corta de
    verdade e o filtro de data do pacote; isto so evita trazer a semana errada.
    """
    depois = segunda - timedelta(days=1)
    antes = segunda + timedelta(days=6)
    q = f"{termo} after:{depois.isoformat()} before:{antes.isoformat()}"
    return f"{BASE}/search?q={quote(q)}&{PARAMETROS}"


def _baixar_rss(url: str, cliente: httpx.Client | None) -> list[Noticia]:
    # follow_redirects: a secao /rss/headlines/section/... redireciona para /rss/topics/....
    proprio = cliente is None
    http = cliente or httpx.Client(timeout=20.0, follow_redirects=True)
    try:
        resposta = baixar(FONTE, url, cliente=http, headers={"User-Agent": USER_AGENT})
    finally:
        if proprio:
            http.close()
    return ler_rss(resposta.text)


def coletar(
    buscas: list[str], segunda: date, *, cliente: httpx.Client | None = None
) -> tuple[list[Noticia], list[str]]:
    """A secao Negocios mais cada busca. Uma consulta que falha vira aviso.

    So levanta `FonteIndisponivelError` quando TODAS falham: ai nao ha bloco.
    """
    consultas = [
        ("secao Negocios", URL_TOPICO),
        *((f"busca '{b}'", url_da_busca(b, segunda)) for b in buscas),
    ]
    noticias: list[Noticia] = []
    avisos: list[str] = []
    for nome, url in consultas:
        try:
            noticias += _baixar_rss(url, cliente)
        except FonteIndisponivelError as exc:
            avisos.append(f"{nome} falhou: {exc.motivo}")
    if len(avisos) == len(consultas):
        raise FonteIndisponivelError(FONTE, f"todas as consultas falharam ({avisos[0]})")
    return noticias, avisos
