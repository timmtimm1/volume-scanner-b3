"""Formato da mensagem e envio ao Telegram.

`format_alert` e puro, entao a maior parte destes testes nao toca a rede.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest

from scanner.notify.telegram import (
    ConsoleNotifier,
    TelegramError,
    TelegramNotifier,
    br,
    chart_url,
    console_safe,
    format_alert,
    money,
    pct,
)

BASE = "http://localhost:3000"

# O exemplo da secao 4 do plano, com todos os campos presentes.
EVENTO: dict[str, Any] = {
    "ticker": "XPTO3",
    "trade_date": date(2026, 3, 12),
    "rvol": 18.3,
    "z_by_window": {30: 7.42, 45: 7.88, 60: 8.11},
    "volume_financial": 47_200_000.0,
    "close": 12.84,
    "ret_day": -0.071,
    "clv": 0.78,
    "gap": -0.021,
    "range_norm": 0.035,
    "pos252": 0.06,
    "ret_prior_20": -0.243,
    "avg_ticket": 8420.0,
    "ticket_z": 3.1,
    "mkt_vol_z": 0.51,
    "z_excess": 7.60,
}


# --- Formatacao de numeros ---------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "casas", "esperado"),
    [
        (1234.5, 2, "1.234,50"),
        (0.5, 2, "0,50"),
        (1_000_000.0, 0, "1.000.000"),
        (18.3, 1, "18,3"),
        (None, 2, "-"),
    ],
)
def test_br(valor: float | None, casas: int, esperado: str) -> None:
    assert br(valor, casas) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"), [(-0.071, "-7,1%"), (0.104, "+10,4%"), (0.0, "+0,0%"), (None, "-")]
)
def test_pct(valor: float | None, esperado: str) -> None:
    assert pct(valor) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (47_200_000.0, "R$ 47,2 mi"),
        (2_400_000_000.0, "R$ 2,4 bi"),
        (47_200.0, "R$ 47,2 mil"),
        (940.0, "R$ 940,00"),
        (None, "-"),
    ],
)
def test_money(valor: float | None, esperado: str) -> None:
    assert money(valor) == esperado


def test_chart_url_leva_ticker_e_data() -> None:
    url = chart_url("http://exemplo.com/", "PETR4", date(2026, 3, 12))
    assert url == "http://exemplo.com/papel/PETR4?data=2026-03-12"


# --- Mensagem ----------------------------------------------------------------


def test_mensagem_bate_com_o_formato_do_plano() -> None:
    texto = format_alert(EVENTO, BASE)
    linhas = texto.split("\n")

    assert linhas[0] == "⚡ XPTO3 — volume 18,3× o normal"
    assert linhas[1] == "Pregao de 12/03/2026"
    assert "R$ 47,2 mi negociados" in texto
    assert "z_log: 30d 7,42 | 45d 7,88 | 60d 8,11" in texto
    assert "z liquido do mercado: 7,60" in texto
    assert "R$ 12,84 (-7,1%) | gap -2,1%" in texto
    assert "Fechou a 78% do range do dia" in texto
    assert "Faixa de 252d: 6% (perto da minima)" in texto
    assert "20 pregoes anteriores: -24,3%" in texto
    assert "Ticket medio: R$ 8.420 (z 3,1)" in texto


def test_mensagem_leva_o_link_da_ficha() -> None:
    texto = format_alert(EVENTO, BASE)
    assert 'href="http://localhost:3000/papel/XPTO3?data=2026-03-12"' in texto
    assert "abrir grafico" in texto


def test_z_por_janela_sai_em_ordem_crescente() -> None:
    embaralhado = {**EVENTO, "z_by_window": {60: 8.11, 30: 7.42, 45: 7.88}}
    assert "z_log: 30d 7,42 | 45d 7,88 | 60d 8,11" in format_alert(embaralhado, BASE)


@pytest.mark.parametrize(
    ("pos", "rotulo"),
    [(0.06, "(perto da minima)"), (0.94, "(perto da maxima)"), (0.5, "")],
)
def test_faixa_do_ano_ganha_leitura_em_palavras(pos: float, rotulo: str) -> None:
    texto = format_alert({**EVENTO, "pos252": pos}, BASE)
    linha = next(linha for linha in texto.split("\n") if linha.startswith("Faixa de 252d"))
    assert linha.endswith(rotulo) if rotulo else "(" not in linha


def test_feature_ausente_nao_impede_a_mensagem() -> None:
    # Papel recem-listado nao tem pos252 nem ticket_z. O alerta tem de sair.
    incompleto = {**EVENTO, "pos252": None, "ticket_z": None, "avg_ticket": None}
    texto = format_alert(incompleto, BASE)

    assert "XPTO3" in texto
    assert "Faixa de 252d: -" in texto
    assert "Ticket medio: R$ - (z -)" in texto


def test_sem_z_por_janela_a_linha_ainda_sai() -> None:
    assert "z_log: -" in format_alert({**EVENTO, "z_by_window": {}}, BASE)


def test_console_safe_degrada_sem_estourar() -> None:
    # O console do Windows e cp1252; o texto tem de sair de algum jeito.
    saida = console_safe("⚡ teste → fim")
    assert "teste" in saida
    assert isinstance(saida, str)


# --- Envio -------------------------------------------------------------------


class RespostaFalsa:
    def __init__(
        self,
        erro: Exception | None = None,
        status_code: int = 200,
        corpo: dict[str, Any] | None = None,
    ) -> None:
        self.erro = erro
        self.status_code = status_code
        self.corpo = corpo or {}

    def raise_for_status(self) -> None:
        if self.erro is not None:
            raise self.erro

    def json(self) -> dict[str, Any]:
        return self.corpo


def _notifier_sem_espera(esperas: list[float], **kwargs: Any) -> TelegramNotifier:
    """Relogio parado e sono anotado: nenhum teste espera de verdade."""
    return TelegramNotifier(
        token="TOKEN", chat_id="123", dormir=esperas.append, relogio=lambda: 1000.0, **kwargs
    )


def test_envio_monta_a_chamada_certa(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: dict[str, Any] = {}

    def falso_post(url: str, **kwargs: Any) -> RespostaFalsa:
        capturado["url"] = url
        capturado["json"] = kwargs["json"]
        return RespostaFalsa()

    monkeypatch.setattr(httpx, "post", falso_post)
    notifier = TelegramNotifier(token="TOKEN", chat_id="123", base_url=BASE)

    assert notifier.send_event(EVENTO) is True
    assert capturado["url"] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert capturado["json"]["chat_id"] == "123"
    assert capturado["json"]["parse_mode"] == "HTML"
    assert "XPTO3" in capturado["json"]["text"]


def test_falha_de_rede_vira_erro_explicito(monkeypatch: pytest.MonkeyPatch) -> None:
    def falso_post(url: str, **kwargs: Any) -> RespostaFalsa:
        return RespostaFalsa(httpx.HTTPError("503"))

    monkeypatch.setattr(httpx, "post", falso_post)
    notifier = TelegramNotifier(token="TOKEN", chat_id="123")

    with pytest.raises(TelegramError, match="recusado"):
        notifier.send_text("oi")


def test_console_notifier_guarda_o_que_enviou(capsys: pytest.CaptureFixture[str]) -> None:
    enviadas: list[str] = []
    assert ConsoleNotifier(base_url=BASE, sent=enviadas).send_event(EVENTO) is True
    assert len(enviadas) == 1
    assert "XPTO3" in capsys.readouterr().out


def test_mensagem_traz_a_data_do_pregao() -> None:
    # Sem a data, o alerta e lido contra a borda direita do grafico, que
    # raramente e o pregao do evento.
    texto = format_alert(EVENTO, BASE)
    assert "Pregao de 12/03/2026" in texto


def test_data_do_pregao_vem_de_trade_date_nao_de_hoje() -> None:
    outro = {**EVENTO, "trade_date": date(2024, 11, 5)}
    assert "Pregao de 05/11/2024" in format_alert(outro, BASE)


# --- Ritmo e 429 ---------------------------------------------------------------


def _responde_429(retry_after: float) -> RespostaFalsa:
    erro = httpx.HTTPStatusError("429", request=None, response=None)  # type: ignore[arg-type]
    return RespostaFalsa(erro, 429, {"parameters": {"retry_after": retry_after}})


def test_mensagens_seguidas_sao_espacadas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dezenas de alertas no mesmo pregao nao podem sair de uma vez so."""
    monkeypatch.setattr(httpx, "post", lambda *a, **k: RespostaFalsa())
    esperas: list[float] = []
    notifier = _notifier_sem_espera(esperas)

    notifier.send_text("um")
    notifier.send_text("dois")

    assert esperas == [1.0], "a segunda mensagem espera o intervalo; a primeira nao"


def test_429_espera_o_que_o_telegram_pede_e_tenta_de_novo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respostas = [_responde_429(3), RespostaFalsa()]
    chamadas: list[int] = []

    def falso_post(*_a: Any, **_k: Any) -> RespostaFalsa:
        chamadas.append(1)
        return respostas[len(chamadas) - 1]

    monkeypatch.setattr(httpx, "post", falso_post)
    esperas: list[float] = []

    assert _notifier_sem_espera(esperas).send_text("oi") is True
    assert len(chamadas) == 2
    assert 3.0 in esperas


def test_429_persistente_vira_erro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _responde_429(1))
    with pytest.raises(TelegramError, match="429"):
        _notifier_sem_espera([]).send_text("oi")


def test_429_com_espera_longa_demais_falha_na_hora(monkeypatch: pytest.MonkeyPatch) -> None:
    # Esperar uma hora estouraria o timeout do job sem avisar nada.
    chamadas: list[int] = []

    def falso_post(*_a: Any, **_k: Any) -> RespostaFalsa:
        chamadas.append(1)
        return _responde_429(3600)

    monkeypatch.setattr(httpx, "post", falso_post)
    esperas: list[float] = []
    with pytest.raises(TelegramError):
        _notifier_sem_espera(esperas).send_text("oi")
    assert len(chamadas) == 1
    assert 3600 not in esperas


def test_erro_do_telegram_nao_leva_o_token(monkeypatch: pytest.MonkeyPatch) -> None:
    segredo = "123456:SEGREDO-DO-BOT"
    url = f"https://api.telegram.org/bot{segredo}/sendMessage"
    erro = httpx.HTTPStatusError(f"Client error for url {url}", request=None, response=None)  # type: ignore[arg-type]
    monkeypatch.setattr(httpx, "post", lambda *a, **k: RespostaFalsa(erro, 400))

    notifier = TelegramNotifier(token=segredo, chat_id="123")
    with pytest.raises(TelegramError) as info:
        notifier.send_text("oi")
    assert segredo not in str(info.value)
