"""As noticias principais da semana: filtro e agrupamento por historia. PURO, sem rede.

Pedido do usuario: as principais da semana em economia e mercado financeiro, SEM
relacao com as acoes das listas de altas e quedas e SEM IA. "Principal" e a
historia que mais veiculos DISTINTOS deram; as primeiras entram no resumo.

A logica de fonte, de "nao e noticia" e de agrupamento vem da aba Noticias da
ficha (`web/src/lib/noticias.ts`), com duas diferencas medidas em 17/10/2026,
na semana de 16/10, que ficam explicadas em `_semelhanca` e `_agrupar`.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from scanner.semana.fontes.google_noticias import Noticia

# Mesma lista de web/src/lib/noticias.ts: mudou la, mude aqui.
# (tests/test_semana_noticias.py le o .ts e confere.)
FONTES_FINANCEIRAS = frozenset(
    {
        "valor.globo.com",
        "valorinveste.globo.com",
        "infomoney.com.br",
        "moneytimes.com.br",
        "seudinheiro.com",
        "br.investing.com",
        "suno.com.br",
        "investidor10.com.br",
        "br.advfn.com",
        "exame.com",
        "neofeed.com.br",
        "braziljournal.com",
        "bloomberglinea.com.br",
        "spacemoney.com.br",
        "bpmoney.com.br",
        "acionista.com.br",
        "timesbrasil.com.br",
        "einvestidor.estadao.com.br",
        "forbes.com.br",
        "istoedinheiro.com.br",
        "conteudos.xpi.com.br",
        "eixos.com.br",
        "brasilenergia.com.br",
        "agenciainfra.com",
        "monitormercantil.com.br",
        "kinvo.com.br",
    }
)

# Mesma lista de web/src/lib/noticias.ts: mudou la, mude aqui.
FONTES_GERAIS = frozenset(
    {
        "g1.globo.com",
        "oglobo.globo.com",
        "estadao.com.br",
        "economia.uol.com.br",
        "noticias.uol.com.br",
        "folha.uol.com.br",
        "www1.folha.uol.com.br",
        "cnnbrasil.com.br",
        "poder360.com.br",
        "gazetadopovo.com.br",
        "veja.abril.com.br",
        "correiobraziliense.com.br",
        "metropoles.com",
    }
)

# Do site: pagina de cotacao e boletim de analise grafica que o Google indexa
# como noticia. Aqui sem a excecao "fonte desconhecida com ticker": noticia
# geral nao tem ticker, a fonte fora das listas simplesmente sai.
NAO_NOTICIA = re.compile(
    r"Resultados, Dividendos, Cotação|cotação, dividendos|cotação hoje"
    r"|ATEN[CÇ][AÃ]O PARA O CALL|Análise Técnica Semanal|Giro de Gráficos|Fórum \|",
    re.IGNORECASE,
)
PALAVRAS_MINIMAS = 4
# Medido em 17/10/2026: "Mega-Sena acumulada em R$ 150 milhões" (BPMoney) entrou
# pela busca "economia". Fonte da imprensa, mas nao e economia.
LOTERIA = re.compile(r"Mega-Sena|Lotofácil|Lotofacil|Quina|Lotomania|loteria", re.IGNORECASE)

# Boletins recorrentes de mercado: todo veiculo publica um por dia, entao sem
# este corte eles dominavam o topo como "a noticia mais repetida". Medido na
# semana de 16/10/2026: 121 manchetes; antes do corte, 3 das 8 primeiras eram
# "Ibovespa fecha...", "Ibovespa Futuro..." e o Boletim Focus de segunda.
# Fica de fora o que e noticia sobre o assunto: "Focus eleva projecao de
# inflacao..." nao casa (sem "focus:" nem "boletim focus"). A segunda linha
# pega o fechamento com palavras no meio ("Ibovespa devolve perdas e fecha no
# zero..."), e o `[^?]` deixa de fora a pergunta ("Ibovespa nos 240 mil
# pontos? Por que..."), que e analise, nao boletim.
BOLETIM_DIARIO = re.compile(
    r"^(ibovespa|dólar|dolar|bolsa|mercados?|juros futuros|di)( futuro)?"
    r"( hoje| agora| ao vivo)?[:,]? "
    r"(fecha|abre|encerra|termina|opera|sobe|cai|recua|avança|avanca|tem|segue|renova"
    r"|dispara|despenca|oscila|volta|amplia|reduz|inverte|zera|firma)"
    r"|^ibovespa futuro|boletim focus|focus:|maiores altas e (as )?(maiores )?baixas"
    r"|o que esperar (dos mercados|da bolsa|do ibovespa)|agenda do dia|abertura de mercado"
    r"|fechamento de mercado|resumo do mercado|minuto touro"
    r"|^(ibovespa|dólar|dolar|bolsa)\b[^?]{0,60}\b(fecha|abre|encerra)\b",
    re.IGNORECASE,
)

# Duas manchetes parecidas de dias distantes sao eventos distintos (dois
# fechamentos de Ibovespa, duas decisoes de juros).
JANELA_DA_MESMA_HISTORIA = timedelta(hours=48)
# Medido na semana de 16/10/2026, com o mesmo conjunto de manchetes nos tres:
# - 0,45 deixava o Focus partido em dois grupos (Kinvo e G1, 4 veiculos cada) e
#   a inflacao dos EUA (CPI) fora do top 8;
# - 0,40 junta o Focus (7 veiculos) e poe o CPI no topo (6);
# - 0,35 colava demais: um grupo de 11 misturando Citi, CPI e Fed, e
#   fechamentos de Ibovespa de dias diferentes.
# Ver `_semelhanca`.
LIMIAR_DE_MESMA_HISTORIA = 0.40

BRASILIA = ZoneInfo("America/Sao_Paulo")

MOTIVOS = ("boletim_diario", "nao_e_noticia", "fora_da_imprensa", "fora_da_semana")


def inicio_da_semana(segunda: date) -> datetime:
    """Segunda 00:00 de Brasilia, em UTC (12/10/2026 -> 03:00 UTC)."""
    return datetime.combine(segunda, time.min, tzinfo=BRASILIA).astimezone(UTC)


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def tokens(titulo: str) -> frozenset[str]:
    """Palavras de 4+ letras, sem acento e minusculas (como `tokens` do site)."""
    return frozenset(re.findall(r"[a-z0-9]{4,}", _sem_acento(titulo).lower()))


def nao_e_noticia(titulo: str) -> bool:
    return (
        NAO_NOTICIA.search(titulo) is not None
        or len(titulo.split()) < PALAVRAS_MINIMAS
        or LOTERIA.search(titulo) is not None
    )


def boletim_diario(titulo: str) -> bool:
    return BOLETIM_DIARIO.search(titulo) is not None


@dataclass
class _Grupo:
    itens: list[Noticia]
    tokens: list[frozenset[str]]


def _agrupar(noticias: list[Noticia]) -> list[_Grupo]:
    """Guloso na ordem de entrada, como o `agrupar` do site, com duas diferencas.

    1. Peso por raridade (IDF) em vez de contagem. Com contagem a 0,6, "Deficit
       fiscal dos EUA chega a US$ 2 trilhoes" e "O deficit orcamentario dos EUA
       se aproxima de US$ 2 trilhoes" ficavam em grupos separados; a 0,4 sem
       peso, "Ibovespa", "dolar" e "juros" (em quase toda manchete) colavam
       historias diferentes. `idf(w) = ln(N / df(w))` sobre as manchetes que
       sobraram do filtro; semelhanca = soma idf(A inter B) / min(soma idf(A),
       soma idf(B)).
    2. Janela de 48 h: so entra no grupo se a semelhanca passa com uma manchete
       do grupo publicada a ate 48 h dela.
    """
    toks = [tokens(n.titulo) for n in noticias]
    total = len(noticias)
    freq = Counter(w for t in toks for w in t)
    idf = {w: math.log(total / c) for w, c in freq.items()}

    def peso(palavras: frozenset[str]) -> float:
        return sum(idf[w] for w in palavras)

    pesos = [peso(t) for t in toks]
    grupos: list[_Grupo] = []
    pesos_do_grupo: list[list[float]] = []
    for n, t, p in zip(noticias, toks, pesos, strict=True):
        destino = -1
        for i, g in enumerate(grupos):
            for outro, p_outro, m in zip(g.tokens, pesos_do_grupo[i], g.itens, strict=True):
                if abs(n.publicada_em - m.publicada_em) > JANELA_DA_MESMA_HISTORIA:
                    continue
                menor = min(p, p_outro)
                if menor > 0 and peso(t & outro) / menor >= LIMIAR_DE_MESMA_HISTORIA:
                    destino = i
                    break
            if destino >= 0:
                break
        if destino >= 0:
            grupos[destino].itens.append(n)
            grupos[destino].tokens.append(t)
            pesos_do_grupo[destino].append(p)
        else:
            grupos.append(_Grupo([n], [t]))
            pesos_do_grupo.append([p])
    return grupos


def _historia(g: _Grupo) -> dict[str, Any]:
    financeira = next((n for n in g.itens if n.dominio in FONTES_FINANCEIRAS), None)
    rep = financeira or g.itens[0]
    vistas = {rep.fonte}
    outras: list[dict[str, str]] = []
    for n in g.itens:
        if n.fonte in vistas:
            continue
        vistas.add(n.fonte)
        outras.append({"fonte": n.fonte, "link": n.link})
    return {
        "titulo": rep.titulo,
        "fonte": rep.fonte,
        "link": rep.link,
        "publicada_em": max(n.publicada_em for n in g.itens).astimezone(UTC).isoformat(),
        "veiculos": len({n.fonte for n in g.itens}),
        "outras_fontes": outras,
    }


def selecionar(
    noticias: list[Noticia], inicio: datetime, fim: datetime, top: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filtra, agrupa por historia e devolve as `top` primeiras com a contagem.

    Contagem em cascata: `recebidas` e o bruto; `distintas`, sem link repetido
    (duplicata nao e descarte); `na_semana`, as distintas dentro de `inicio` e
    `fim`; `na_imprensa`, as da semana em fonte da lista. Os descartes por
    motivo somam o que cada filtro tirou, na ordem em que eles rodam.
    """
    descartes = dict.fromkeys(MOTIVOS, 0)

    vistos: set[str] = set()
    distintas: list[Noticia] = []
    for n in noticias:
        if n.link not in vistos:
            vistos.add(n.link)
            distintas.append(n)

    na_semana = [n for n in distintas if inicio <= n.publicada_em <= fim]
    descartes["fora_da_semana"] = len(distintas) - len(na_semana)

    na_imprensa = [n for n in na_semana if n.dominio in FONTES_FINANCEIRAS | FONTES_GERAIS]
    descartes["fora_da_imprensa"] = len(na_semana) - len(na_imprensa)

    restantes: list[Noticia] = []
    for n in na_imprensa:
        if nao_e_noticia(n.titulo):
            descartes["nao_e_noticia"] += 1
        elif boletim_diario(n.titulo):
            descartes["boletim_diario"] += 1
        else:
            restantes.append(n)

    grupos = _agrupar(restantes) if restantes else []
    # Ranking: veiculos desc, depois manchetes do grupo desc, depois a mais
    # recente. `publicada_em` e ISO em UTC, entao ordena como texto.
    ranking = sorted(
        ((_historia(g), len(g.itens)) for g in grupos),
        key=lambda par: (par[0]["veiculos"], par[1], par[0]["publicada_em"]),
        reverse=True,
    )
    historias = [h for h, _ in ranking]
    contagem = {
        "recebidas": len(noticias),
        "na_semana": len(na_semana),
        "distintas": len(distintas),
        "na_imprensa": len(na_imprensa),
        "descartes": descartes,
    }
    return historias[:top], contagem
