"""A mensagem do Telegram com o resumo da semana.

Enxuta de proposito: so os numeros e as manchetes, com o completo no app (o link
fecha a mensagem). Funcao pura sobre o payload gravado em `resumos_semanais`: nao
toca rede nem banco, e e o que os testes exercitam.

Sem `<pre>`, de proposito. A primeira versao alinhava os numeros em tabelas
monoespacadas, e no Telegram do iPhone (17/10/2026) o bloco aparecia como codigo:
borda laranja, fonte de terminal e o botao de copiar POR CIMA da primeira linha,
cobrindo o "-1,7%" do Ibovespa e o "-22,3%" da maior queda. Agora e lista na
fonte normal: cada linha le sozinha, com o nome em negrito e uma seta para a
direcao. Todo texto que vem de fora (manchete, nome de empresa, evento) passa
por `html.escape`.
"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping
from datetime import date
from typing import Any

from scanner.notify.telegram import br, pct

# O Telegram recusa mensagem com mais de 4096 caracteres.
LIMITE_TELEGRAM = 4096
LADO_DO_RANKING = 5
NOTICIAS_NA_MENSAGEM = 5
INDISPONIVEL = "<i>indisponível</i>"

DIAS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def _esc(texto: object) -> str:
    return html.escape(str(texto), quote=True)


def _seta(variacao: float | None, casas: int = 1) -> str:
    """'▲ 1,6%', '▼ 1,7%': a seta diz a direcao, o numero vai sem sinal."""
    if variacao is None:
        return "-"
    if round(variacao * 100, casas) == 0:
        return f"{br(0.0, casas)}%"
    return f"{'▲' if variacao > 0 else '▼'} {br(abs(variacao) * 100, casas)}%"


def _erro(bloco: Any) -> bool:
    return not isinstance(bloco, Mapping) or "erro" in bloco


def _periodo(semana: Mapping[str, Any]) -> str:
    pregoes = [date.fromisoformat(d) for d in semana["pregoes"]] or [
        date.fromisoformat(semana["fim"])
    ]
    primeiro, ultimo = pregoes[0], pregoes[-1]
    if primeiro == ultimo:
        return ultimo.strftime("%d/%m/%Y")
    if (primeiro.year, primeiro.month) == (ultimo.year, ultimo.month):
        return f"{primeiro.day} a {ultimo.strftime('%d/%m/%Y')}"
    if primeiro.year == ultimo.year:
        return f"{primeiro.strftime('%d/%m')} a {ultimo.strftime('%d/%m/%Y')}"
    return f"{primeiro.strftime('%d/%m/%Y')} a {ultimo.strftime('%d/%m/%Y')}"


# --- abertura ---------------------------------------------------------------


def _abertura(bloco: Any) -> str:
    if _erro(bloco):
        return "<i>Abertura indisponível</i>"
    # (chave, nome, moeda na frente do valor, casas)
    itens = (
        ("ibovespa", "Ibovespa", "", 0),
        ("dolar", "Dólar", "R$ ", 2),
        ("brent", "Brent", "US$ ", 2),
        ("ouro", "Ouro", "US$ ", 0),
    )
    linhas: list[str] = []
    for chave, nome, moeda, casas in itens:
        ativo = bloco.get(chave)
        if _erro(ativo):
            linhas.append(f"<b>{nome}</b> {INDISPONIVEL}")
            continue
        valor = f"{moeda}{br(ativo['valor'], casas)}"
        linhas.append(f"<b>{nome}</b> {valor} {_seta(ativo['semana'])}")
        if chave == "ibovespa":
            linhas.append(f"mês {pct(ativo['mes'])} · ano {pct(ativo['ano'])}")
    return "\n".join(linhas)


# --- ações ------------------------------------------------------------------


def _linha_acao(acao: Mapping[str, Any]) -> str:
    marca = "*" if acao.get("ajustado") else ""
    return f"{_esc(acao['ticker'])} {pct(acao['variacao'])}{marca}"


def _acoes(bloco: Any) -> str:
    if _erro(bloco):
        return f"📈 <b>Ações</b>\n{INDISPONIVEL}"
    altas = list(bloco["altas"])[:LADO_DO_RANKING]
    quedas = list(bloco["quedas"])[:LADO_DO_RANKING]
    if not altas and not quedas:
        return f"📈 <b>Ações</b>\n{INDISPONIVEL}"
    partes = [
        "📈 <b>Maiores altas</b>\n" + "\n".join(_linha_acao(a) for a in altas),
        "📉 <b>Maiores quedas</b>\n" + "\n".join(_linha_acao(a) for a in quedas),
    ]
    texto = "\n\n".join(partes)
    if any(a.get("ajustado") for a in (*altas, *quedas)):
        texto += "\n<i>* ajustada por proventos ou desdobramento</i>"
    return texto


# --- notícias ---------------------------------------------------------------


def _noticia(historia: Mapping[str, Any]) -> str:
    veiculos = int(historia["veiculos"])
    fonte = _esc(historia["fonte"])
    origem = fonte if veiculos <= 1 else f"{fonte} e mais {veiculos - 1}"
    return f'• <a href="{_esc(historia["link"])}">{_esc(historia["titulo"])}</a> · {origem}'


def _historias(bloco: Any) -> list[str] | None:
    """As manchetes ja formatadas, ou None se o bloco nao existe."""
    if _erro(bloco):
        return None
    return [_noticia(h) for h in list(bloco["historias"])[:NOTICIAS_NA_MENSAGEM]]


def _bloco_noticias(historias: list[str] | None) -> str:
    titulo = "📰 <b>Notícias da semana</b>"
    if historias is None:
        return f"{titulo}\n{INDISPONIVEL}"
    if not historias:
        return f"{titulo}\n<i>sem notícias</i>"
    return titulo + "\n" + "\n".join(historias)


# --- cripto -----------------------------------------------------------------


def _cripto(bloco: Any) -> str:
    titulo = "🪙 <b>Cripto</b> · 7 dias"
    if _erro(bloco):
        return f"{titulo}\n{INDISPONIVEL}"
    linhas = [
        f"<b>{_esc(moeda['simbolo'])}</b> US$ {br(moeda['preco'], 0)} {_seta(moeda['variacao_7d'])}"
        for moeda in (bloco.get("btc"), bloco.get("eth"))
        if moeda
    ]
    if not linhas:
        return f"{titulo}\n{INDISPONIVEL}"
    return titulo + "\n" + "\n".join(linhas)


# --- juros ------------------------------------------------------------------


def _bp(valor: float | None) -> str:
    if valor is None:
        return ""
    n = round(valor)
    return f" ({'+' if n >= 0 else '-'}{abs(n)} bp)"


def _linha_juros(nome: str, taxa: float | None, variacao_bp: float | None = None) -> str:
    if taxa is None:
        return f"{nome} {INDISPONIVEL}"
    return f"{nome} {br(taxa)}%{_bp(variacao_bp)}"


def _juros(payload: Mapping[str, Any]) -> str:
    br_ = payload.get("juros_br") or {}
    eua = payload.get("eua") or {}
    curva: Any = br_.get("curva")
    indicadores: Any = br_.get("indicadores")
    tesouro: Any = eua.get("treasuries")
    real: Any = br_.get("curva_real")

    def vertice(du: int, bloco: Any = curva) -> Mapping[str, Any] | None:
        # Edicao antiga nao tem `curva_real`: a linha do IPCA+ simplesmente nao sai.
        if bloco is None or _erro(bloco):
            return None
        return next((v for v in bloco["vertices"] if v["du"] == du), None)

    def vencimento(prazo: str) -> Mapping[str, Any] | None:
        if _erro(tesouro):
            return None
        return next((v for v in tesouro["vencimentos"] if v["prazo"] == prazo), None)

    def com_variacao(nome: str, item: Mapping[str, Any] | None) -> str:
        if item is None:
            return _linha_juros(nome, None)
        return _linha_juros(nome, item["taxa"], item["variacao_bp"])

    selic = None if _erro(indicadores) else indicadores.get("selic_meta")
    linhas = [
        com_variacao("Pré 1 ano", vertice(252)),
        com_variacao("Pré 10 anos", vertice(2520)),
        _linha_juros("Selic", selic),
        *([com_variacao("IPCA+ 10 anos", vertice(2520, real))] if real is not None else []),
        com_variacao("Treasury 2 anos", vencimento("2 Yr")),
        com_variacao("Treasury 10 anos", vencimento("10 Yr")),
    ]
    return "💰 <b>Juros</b> · na semana\n" + "\n".join(linhas)


# --- semana que vem ---------------------------------------------------------


def _dia(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{DIAS[d.weekday()]} {d.strftime('%d/%m')}"


def _evento(e: Mapping[str, Any]) -> tuple[tuple[str, str], str]:
    quando = f"{_dia(e['data'])} {e['hora']}" if e.get("hora") else _dia(e["data"])
    consenso = e.get("consenso")
    focus = ""
    if consenso:
        unidade = "%" if str(consenso["unidade"]).startswith("%") else str(consenso["unidade"])
        focus = f" (Focus {br(consenso['mediana'], 2)}{unidade})"
    return (e["data"], e.get("hora") or "99:99"), f"{quando} · {_esc(e['evento'])}{_esc(focus)}"


_SUFIXO_SA = re.compile(r"\s+S\.?/?A\.?\s*$", re.IGNORECASE)


def _nome_curto(empresa: str) -> str:
    return _SUFIXO_SA.sub("", empresa).title()


def _balanco(b: Mapping[str, Any]) -> tuple[tuple[str, str], str]:
    tickers = ", ".join(b.get("tickers") or [])
    nome = _nome_curto(str(b["empresa"])) + (f" ({tickers})" if tickers else "")
    horario = f" · {b['horario']}" if b.get("horario") else ""
    return (b["data"], "99:99"), f"{_dia(b['data'])} · Balanço {_esc(nome)}{_esc(horario)}"


def _proxima_semana(bloco: Any) -> str:
    titulo = "📅 <b>Semana que vem</b>"
    if _erro(bloco):
        return f"{titulo}\n{INDISPONIVEL}"
    itens = [_evento(e) for e in bloco.get("agenda", [])]
    balancos = bloco.get("balancos")
    provaveis = 0
    if not _erro(balancos):
        itens += [_balanco(b) for b in balancos.get("confirmados", [])]
        provaveis = len(balancos.get("provaveis", []))
    linhas = [texto for _, texto in sorted(itens, key=lambda item: item[0])]
    if provaveis == 1:
        linhas.append("+1 balanço provável no app")
    elif provaveis > 1:
        linhas.append(f"+{provaveis} balanços prováveis no app")
    feriados = [date.fromisoformat(d).strftime("%d/%m") for d in bloco.get("feriados_b3", [])]
    if feriados:
        rotulo = "Feriados na B3" if len(feriados) > 1 else "Feriado na B3"
        linhas.append(f"{rotulo}: {', '.join(feriados)}")
    if _erro(balancos):
        linhas.append("<i>balanços indisponíveis</i>")
    if not linhas:
        linhas.append("<i>nada na agenda</i>")
    return titulo + "\n" + "\n".join(linhas)


# --- mensagem ---------------------------------------------------------------


def formatar_mensagem(payload: Mapping[str, Any], base_url: str) -> str:
    """O resumo da semana em HTML do Telegram, sempre abaixo de 4.096 caracteres.

    Estourou o limite: corta manchetes do fim ate caber. O resto nao e cortado:
    tem tamanho fixo.
    """
    semana = payload["semana"]
    # Com barra final: o site usa `trailingSlash`, e sem ela cada toque no link
    # passava por um 308 antes de abrir a pagina.
    link = f"{base_url.rstrip('/')}/semana/{semana['sexta']}/"
    historias = _historias(payload.get("noticias"))

    def montar(noticias: list[str] | None) -> str:
        blocos = [
            f"📊 <b>Resumo da semana</b>\n{_periodo(semana)}",
            _abertura(payload.get("abertura")),
            _acoes(payload.get("acoes")),
            _bloco_noticias(noticias),
            _cripto(payload.get("cripto")),
            _juros(payload),
            _proxima_semana(payload.get("proxima_semana")),
            f'<a href="{_esc(link)}">Resumo completo no app</a>',
        ]
        return "\n\n".join(blocos)

    texto = montar(historias)
    while len(texto) > LIMITE_TELEGRAM and historias:
        historias = historias[:-1]
        texto = montar(historias)
    return texto
