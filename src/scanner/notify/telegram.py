"""Alerta por Telegram (secao 4 do plano).

`format_alert` e puro e nao toca a rede: e o que os testes exercitam. O envio
fica isolado em `TelegramNotifier`.

O token e o chat vem do ambiente (`SCANNER_TELEGRAM_*`), nunca do repositorio.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

API_BASE = "https://api.telegram.org"
TIMEOUT_SECONDS = 20.0

# Abaixo disso o papel esta perto da minima do ano; acima, perto da maxima.
NEAR_LOW = 0.20
NEAR_HIGH = 0.80


class TelegramError(Exception):
    """O Telegram recusou a mensagem."""


def br(value: float | None, casas: int = 2) -> str:
    """Numero no formato brasileiro: 1234.5 vira '1.234,50'."""
    if value is None:
        return "-"
    texto = f"{value:,.{casas}f}"
    # Troca simultanea de separadores, via marcador temporario.
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def pct(value: float | None, casas: int = 1) -> str:
    """Percentual com sinal, no formato brasileiro."""
    if value is None:
        return "-"
    return f"{'+' if value >= 0 else '-'}{br(abs(value) * 100, casas)}%"


def money(value: float | None) -> str:
    """Volume financeiro em escala legivel: mil, mi ou bi."""
    if value is None:
        return "-"
    if value >= 1e9:
        return f"R$ {br(value / 1e9, 1)} bi"
    if value >= 1e6:
        return f"R$ {br(value / 1e6, 1)} mi"
    if value >= 1e3:
        return f"R$ {br(value / 1e3, 1)} mil"
    return f"R$ {br(value)}"


def _faixa_do_ano(pos: float | None) -> str:
    """Onde o papel esta na faixa de 252 pregoes, com a leitura em palavras."""
    if pos is None:
        return "Faixa de 252d: -"
    rotulo = ""
    if pos <= NEAR_LOW:
        rotulo = " (perto da minima)"
    elif pos >= NEAR_HIGH:
        rotulo = " (perto da maxima)"
    return f"Faixa de 252d: {br(pos * 100, 0)}%{rotulo}"


def _z_por_janela(zs: Mapping[int, float | None]) -> str:
    """Linha com o z de cada janela, em ordem crescente de janela."""
    partes = [f"{janela}d {br(zs[janela])}" for janela in sorted(zs) if zs[janela] is not None]
    return "z_log: " + (" | ".join(partes) if partes else "-")


def chart_url(base_url: str, ticker: str, trade_date: date) -> str:
    """Link da ficha do papel. Do celular, um toque entre o alerta e o grafico."""
    return f"{base_url.rstrip('/')}/papel/{ticker}?data={trade_date.isoformat()}"


def format_alert(payload: Mapping[str, Any], base_url: str) -> str:
    """Monta a mensagem do alerta, no formato da secao 4 do plano.

    Campo ausente vira "-": a mensagem nunca deixa de sair porque uma feature
    nao existe para aquele papel.
    """
    ticker = str(payload["ticker"])
    trade_date = payload["trade_date"]
    linhas = [
        f"⚡ {ticker} — volume {br(payload.get('rvol'), 1)}× o normal",
        # A data evita que o alerta seja lido contra o grafico do dia errado:
        # a borda direita do grafico raramente e o pregao do evento.
        f"Pregao de {trade_date.strftime('%d/%m/%Y')}",
        "",
        f"{money(payload.get('volume_financial'))} negociados",
        _z_por_janela(payload.get("z_by_window") or {}),
        f"z liquido do mercado: {br(payload.get('z_excess'))}",
        "",
        f"R$ {br(payload.get('close'))} ({pct(payload.get('ret_day'))})"
        f" | gap {pct(payload.get('gap'))}",
        f"Fechou a {br((payload.get('clv') or 0) * 100, 0)}% do range do dia"
        if payload.get("clv") is not None
        else "Fechou a - do range do dia",
        _faixa_do_ano(payload.get("pos252")),
        f"20 pregoes anteriores: {pct(payload.get('ret_prior_20'))}",
        f"Ticket medio: R$ {br(payload.get('avg_ticket'), 0)} (z {br(payload.get('ticket_z'), 1)})",
        "",
        f'<a href="{chart_url(base_url, ticker, trade_date)}">→ abrir grafico</a>',
    ]
    return "\n".join(linhas)


def console_safe(text: str) -> str:
    """Texto degradado para a codificacao do terminal.

    O console do Windows e cp1252 e nao codifica o raio nem a seta. A mensagem
    que vai para o Telegram segue em UTF-8 e nao passa por aqui: isto e so para
    o `--dry-run` nao morrer com UnicodeEncodeError ao imprimir.
    """
    codificacao = sys.stdout.encoding or "utf-8"
    return text.encode(codificacao, errors="replace").decode(codificacao, errors="replace")


@dataclass(frozen=True)
class TelegramNotifier:
    """Envia alertas para um chat do Telegram."""

    token: str
    chat_id: str
    base_url: str = "http://localhost:3000"

    def send_text(self, text: str) -> bool:
        """Envia uma mensagem. Devolve True se o Telegram aceitou."""
        url = f"{API_BASE}/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            resposta = httpx.post(url, json=payload, timeout=TIMEOUT_SECONDS)
            resposta.raise_for_status()
        except httpx.HTTPError as exc:
            raise TelegramError(f"envio recusado: {exc}") from exc
        return True

    def send_event(self, payload: Mapping[str, Any]) -> bool:
        """Formata e envia um evento."""
        return self.send_text(format_alert(payload, self.base_url))

    def send_resumo(self, payload: Mapping[str, Any]) -> bool:
        """Formata e envia o resumo do pregao."""
        return self.send_text(format_resumo(payload, self.base_url))


@dataclass(frozen=True)
class ConsoleNotifier:
    """Escreve o alerta na saida padrao, sem tocar a rede.

    E o que o `--dry-run` usa e o que roda quando o Telegram nao esta
    configurado: melhor ver o alerta no terminal do que perde-lo em silencio.
    """

    base_url: str = "http://localhost:3000"
    sent: list[str] | None = None

    def send_text(self, text: str) -> bool:
        print(console_safe(text))
        print("-" * 40)
        if self.sent is not None:
            self.sent.append(text)
        return True

    def send_event(self, payload: Mapping[str, Any]) -> bool:
        return self.send_text(format_alert(payload, self.base_url))

    def send_resumo(self, payload: Mapping[str, Any]) -> bool:
        return self.send_text(format_resumo(payload, self.base_url))


# Largura util de um bloco <pre> no Telegram, num celular em retrato. Passar
# disso quebra a linha e desmonta a tabela: a primeira versao tinha 49 colunas
# e cada papel aparecia em duas linhas, com o volume caindo sozinho embaixo.
LARGURA_DO_CELULAR = 32


def volume_curto(valor: float | None) -> str:
    """Volume sem o "R$", que o cabecalho ja diz. Cada coluna conta aqui."""
    if valor is None:
        return "-"
    if abs(valor) >= 1e9:
        return f"{br(valor / 1e9, 1)} bi"
    if abs(valor) >= 1e6:
        return f"{br(valor / 1e6, 1)} mi"
    if abs(valor) >= 1e3:
        return f"{br(valor / 1e3, 1)} mil"
    return br(valor, 0)


def _linha_do_resumo(
    ticker: str,
    desvios: float | None,
    variacao: float | None,
    volume: float | None,
) -> str:
    """Uma linha da tabela, em 31 colunas.

    O preco saiu: nao cabia junto com o resto sem quebrar linha, e e o campo
    menos decisivo dos quatro. Quem quiser, ve na ficha do papel.
    """
    return f"{br(desvios):>6} {ticker:<6}{pct(variacao):>7}{volume_curto(volume):>11}"


def format_resumo(resumo: Mapping[str, Any], base_url: str | None = None) -> str:
    """Resumo diario: tabela dos papeis que mais se afastaram do proprio normal.

    Sem prosa e sem jargao nos cabecalhos. Os numeros sao os mesmos do alerta;
    quem le decide o que fazer com eles.

    A tabela vai dentro de <pre> porque o Telegram so alinha coluna em
    monoespacado, e cabe em 32 colunas para nao quebrar no celular. O que e
    enfeite -- titulo e link -- fica fora do bloco, onde o negrito funciona.
    """
    dia = resumo["trade_date"].strftime("%d/%m/%Y")
    linhas = list(resumo.get("linhas") or [])
    if not linhas:
        return f"📊 <b>Resumo do pregão</b>\n{dia}\n\nSem dados para este pregão."

    cabecalho = f"{'Desvio':>6} {'Papel':<6}{'Var.':>7}{'Volume':>11}"
    corpo = "\n".join(
        _linha_do_resumo(
            str(linha["ticker"]),
            linha.get("desvios"),
            linha.get("variacao"),
            linha.get("volume"),
        )
        for linha in linhas
    )

    partes = [
        "📊 <b>Resumo do pregão</b>",
        dia,
        "",
        f"<pre>{cabecalho}\n{corpo}</pre>",
    ]
    if base_url:
        partes.append(f'<a href="{base_url.rstrip("/")}">abrir o scanner</a>')
    return "\n".join(partes)
