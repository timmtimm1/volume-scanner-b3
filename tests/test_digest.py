"""Resumo diario do pregao."""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import pytest
from sqlalchemy import Engine, delete

from scanner.calendar import sessions_before
from scanner.config import AlertConfig, DigestConfig, ScannerConfig
from scanner.digest import Resumo, montar_resumo, payload_do_resumo, run_resumo
from scanner.features import compute_features
from scanner.metrics import compute_zscores
from scanner.notify.telegram import LARGURA_DO_CELULAR, ConsoleNotifier, format_resumo
from scanner.storage.engine import session_scope
from scanner.storage.models import DigestSend, Trade, TradeSnapshot
from scanner.storage.repository import digest_enviado, marcar_digest_enviado

FIM = date(2026, 6, 30)
SESSOES = 90
JANELA = 30
CONFIG = ScannerConfig(
    alert=AlertConfig(windows=[JANELA], threshold=6.0, min_volume_brl=500_000),
    digest=DigestConfig(top_n=3, window=JANELA),
)


def barras(tickers: Sequence[str], *, nivel: float = 2_000_000.0) -> pd.DataFrame:
    dias = sessions_before(FIM, SESSOES, inclusive=True)
    return pd.concat(
        [
            pd.DataFrame(
                {
                    "ticker": t,
                    "trade_date": dias,
                    "open": 10.0,
                    "high": 10.6,
                    "low": 9.4,
                    "close": [10.0 + (i % 5) * 0.1 for i in range(SESSOES)],
                    "avg_price": 10.1,
                    "volume_shares": 200_000,
                    "volume_financial": [
                        nivel * (1 + 0.1 * math.sin(i + j)) for i in range(SESSOES)
                    ],
                    "trades_count": 800,
                    "trades_censored": False,
                }
            )
            for j, t in enumerate(tickers)
        ],
        ignore_index=True,
    )


def com_spike(b: pd.DataFrame, ticker: str, fator: float) -> pd.DataFrame:
    saida = b.copy()
    saida["trade_date"] = pd.to_datetime(saida["trade_date"])
    alvo = (saida["ticker"] == ticker) & (saida["trade_date"] == pd.Timestamp(FIM))
    saida.loc[alvo, "volume_financial"] *= fator
    return saida


def resumir(b: pd.DataFrame, config: ScannerConfig = CONFIG) -> Resumo:
    metrics = compute_zscores(b, config.alert.windows)
    features = compute_features(b, max(config.alert.windows), metrics)
    return montar_resumo(metrics, b, features, config, FIM)


TRADES_COLUNAS = ["ticker", "quantidade", "resultado", "custo_comprado", "encerrado"]


def trades_frame(linhas: Sequence[dict[str, Any]]) -> pd.DataFrame:
    """DataFrame no formato que `trades_do_pregao` devolveria, para os testes de mensagem."""
    return pd.DataFrame(linhas, columns=TRADES_COLUNAS)


def test_ordena_por_desvios_nao_por_volume() -> None:
    # PEQU3 negocia menos em reais, mas foge muito mais do proprio normal.
    # E o ranking do resumo: desvio padrao, nao tamanho.
    b = barras(["GRAN3", "PEQU3"])
    b.loc[b["ticker"] == "GRAN3", "volume_financial"] *= 50
    b = com_spike(b, "PEQU3", 12.0)

    resumo = resumir(b)
    assert resumo.linhas.iloc[0]["ticker"] == "PEQU3"
    assert resumo.linhas.iloc[0]["volume_financial"] < resumo.linhas.iloc[1]["volume_financial"]


def test_entra_quem_nao_cruzou_o_limiar() -> None:
    # A razao do resumo existir: dia calmo nao pode virar silencio.
    resumo = resumir(barras(["AAAA3", "BBBB4", "CCCC3"]))
    assert not resumo.vazio
    assert resumo.cruzaram == 0
    assert not bool(resumo.linhas["notificado"].any())


def test_marca_quem_tambem_virou_alerta() -> None:
    b = com_spike(barras(["AAAA3", "BBBB4"]), "AAAA3", 40.0)
    resumo = resumir(b)
    linha = resumo.linhas[resumo.linhas["ticker"] == "AAAA3"].iloc[0]
    assert bool(linha["notificado"])
    assert resumo.cruzaram == 1


def test_respeita_o_top_n() -> None:
    resumo = resumir(barras(["AAAA3", "BBBB4", "CCCC3", "DDDD3", "EEEE3"]))
    assert len(resumo.linhas) == CONFIG.digest.top_n


def test_piso_de_volume_vale_no_resumo() -> None:
    # Mesmo piso do alerta: papel morto nao interessa aqui pela mesma razao.
    b = barras(["AAAA3"])
    b = pd.concat([b, barras(["MORT3"], nivel=3_000.0)], ignore_index=True)
    b = com_spike(b, "MORT3", 20.0)

    assert "MORT3" not in set(resumir(b).linhas["ticker"])


def test_pregao_sem_dado_devolve_vazio() -> None:
    resumo = resumir(barras(["AAAA3"]).iloc[:5])
    assert resumo.vazio


# --- Mensagem ----------------------------------------------------------------


def test_mensagem_traz_tabela_alinhada() -> None:
    payload = payload_do_resumo(resumir(barras(["AAAA3", "BBBB4", "CCCC3"])))
    texto = format_resumo(payload)

    assert "Resumo do preg" in texto and "30/06/2026" in texto
    assert "<pre>" in texto and "</pre>" in texto
    assert "Papel" in texto and "Desvio" in texto and "Volume" in texto


def test_nenhuma_linha_estoura_a_largura_do_celular() -> None:
    # O defeito que motivou o formato: com 49 colunas o Telegram quebrava cada
    # papel em duas linhas no celular e o volume caia sozinho embaixo.
    payload = payload_do_resumo(resumir(barras(["AAAA3", "BBBB4", "CCCC3"])))
    # Ticker de 6 letras e volume na casa do bilhao sao os campos mais largos.
    payload["linhas"][0]["ticker"] = "BPAC11"
    payload["linhas"][0]["volume"] = 1_895_862_313.0
    payload["linhas"][0]["variacao"] = -0.123

    texto = format_resumo(payload)
    tabela = texto[texto.index("<pre>") + len("<pre>") : texto.index("</pre>")]
    for linha in tabela.splitlines():
        assert len(linha) <= LARGURA_DO_CELULAR, f"{len(linha)} colunas: {linha}"


def test_link_do_site_so_aparece_quando_ha_endereco() -> None:
    payload = payload_do_resumo(resumir(barras(["AAAA3", "BBBB4"])))
    assert "<a href=" not in format_resumo(payload)
    assert 'href="https://exemplo.app"' in format_resumo(payload, "https://exemplo.app/")


def test_mensagem_nao_usa_jargao_nem_explica() -> None:
    # O pedido foi explicito: nomes do dia a dia, sem giria e sem prosa.
    texto = format_resumo(payload_do_resumo(resumir(barras(["AAAA3", "BBBB4"]))))
    for termo in ("z_log", "rvol", "sigma", "z-score", "baseline"):
        assert termo not in texto.lower(), f"jargao vazou: {termo}"


def test_mensagem_sem_dado_nao_quebra() -> None:
    texto = format_resumo({"trade_date": FIM, "linhas": []})
    assert "Sem dados" in texto


def test_notificador_recebe_o_resumo(capsys: pytest.CaptureFixture[str]) -> None:
    enviadas: list[str] = []
    payload = payload_do_resumo(resumir(barras(["AAAA3", "BBBB4"])))
    assert ConsoleNotifier(sent=enviadas).send_resumo(payload) is True
    assert len(enviadas) == 1
    assert "Resumo do preg" in capsys.readouterr().out


def test_payload_usa_nomes_do_dia_a_dia() -> None:
    payload = payload_do_resumo(resumir(barras(["AAAA3", "BBBB4"])))
    assert set(payload["linhas"][0]) == {
        "ticker",
        "desvios",
        "preco",
        "variacao",
        "volume",
    }


# --- Bloco "Seus trades" ------------------------------------------------------


def test_payload_sem_trades_nao_ganha_a_chave() -> None:
    # `trades=None` (o padrao) e a mesma coisa que nao passar nada: o payload
    # de quem nao sabe da fase 3 continua exatamente igual.
    resumo = resumir(barras(["AAAA3", "BBBB4"]))
    assert "trades" not in payload_do_resumo(resumo)
    assert "trades" not in payload_do_resumo(resumo, trades_frame([]))


def test_mensagem_sem_trades_e_identica_a_de_antes() -> None:
    resumo = resumir(barras(["AAAA3", "BBBB4"]))
    sem_argumento = format_resumo(payload_do_resumo(resumo))
    com_lista_vazia = format_resumo(payload_do_resumo(resumo, trades_frame([])))

    assert sem_argumento == com_lista_vazia
    assert "Seus trades" not in sem_argumento


def test_payload_com_trades_traz_resultado_pct() -> None:
    resumo = resumir(barras(["AAAA3"]))
    trades = trades_frame(
        [
            {
                "ticker": "PETR4",
                "quantidade": 70,
                "resultado": 1022.10,
                "custo_comprado": 5700.0,
                "encerrado": False,
            },
            # custo zero e degenerado (nao deveria acontecer), mas nao pode
            # quebrar o payload com uma divisao por zero.
            {
                "ticker": "ZERO3",
                "quantidade": 10,
                "resultado": 0.0,
                "custo_comprado": 0.0,
                "encerrado": False,
            },
        ]
    )
    payload = payload_do_resumo(resumo, trades)

    petr4 = next(t for t in payload["trades"] if t["ticker"] == "PETR4")
    assert petr4["quantidade"] == 70
    assert petr4["resultado"] == pytest.approx(1022.10)
    assert petr4["resultado_pct"] == pytest.approx(1022.10 / 5700.0)
    assert petr4["encerrado"] is False

    zero3 = next(t for t in payload["trades"] if t["ticker"] == "ZERO3")
    assert zero3["resultado_pct"] is None


def test_bloco_de_trades_traz_titulo_bolinhas_e_secao_de_encerrados() -> None:
    resumo = resumir(barras(["AAAA3"]))
    trades = trades_frame(
        [
            {
                "ticker": "PETR4",
                "quantidade": 70,
                "resultado": 1022.10,
                "custo_comprado": 5700.0,
                "encerrado": False,
            },
            {
                "ticker": "VALE3",
                "quantidade": 0,
                "resultado": -50.0,
                "custo_comprado": 1000.0,
                "encerrado": True,
            },
            {
                "ticker": "ITUB4",
                "quantidade": 10,
                "resultado": 0.0,
                "custo_comprado": 300.0,
                "encerrado": False,
            },
        ]
    )
    texto = format_resumo(payload_do_resumo(resumo, trades))

    assert "<b>Seus trades</b>" in texto
    assert "🟢" in texto  # PETR4, resultado positivo
    assert "🔴" in texto  # VALE3, resultado negativo
    assert "⚪" in texto  # ITUB4, resultado zero
    assert "encerrado hoje" in texto

    # abertos antes da secao de encerrados, que vem antes do encerrado em si
    assert texto.index("PETR4") < texto.index("encerrado hoje") < texto.index("VALE3")
    # 70 acoes aparece; VALE3 (encerrado) mostra "-" em vez de quantidade
    assert "70" in texto


def test_numeros_do_bloco_de_trades_em_formato_brasileiro() -> None:
    resumo = resumir(barras(["AAAA3"]))
    trades = trades_frame(
        [
            {
                "ticker": "PETR4",
                "quantidade": 70,
                "resultado": 1022.10,
                "custo_comprado": 5700.0,
                "encerrado": False,
            }
        ]
    )
    texto = format_resumo(payload_do_resumo(resumo, trades))

    assert "1.022,10" in texto
    assert "+17,9%" in texto  # 1022.10 / 5700 = 17,93...%


def test_link_de_trades_so_aparece_com_base_url() -> None:
    resumo = resumir(barras(["AAAA3"]))
    trades = trades_frame(
        [
            {
                "ticker": "PETR4",
                "quantidade": 70,
                "resultado": 100.0,
                "custo_comprado": 1000.0,
                "encerrado": False,
            }
        ]
    )
    payload = payload_do_resumo(resumo, trades)

    assert "abrir trades" not in format_resumo(payload)
    com_base = format_resumo(payload, "https://exemplo.app")
    assert 'href="https://exemplo.app/trades/"' in com_base
    assert "abrir trades" in com_base


def test_bloco_de_trades_nao_estoura_a_largura_do_celular() -> None:
    resumo = resumir(barras(["AAAA3"]))
    trades = trades_frame(
        [
            {
                "ticker": "BPAC11",
                "quantidade": 99_999,
                "resultado": -99_999.99,
                "custo_comprado": 100_000.0,
                "encerrado": False,
            },
            {
                "ticker": "PETR4",
                "quantidade": 0,
                "resultado": 12_345.67,
                "custo_comprado": 50_000.0,
                "encerrado": True,
            },
        ]
    )
    texto = format_resumo(payload_do_resumo(resumo, trades), "https://exemplo.app")

    bloco = texto[texto.index("<b>Seus trades</b>") :]
    tabela = bloco[bloco.index("<pre>") + len("<pre>") : bloco.index("</pre>")]
    for linha in tabela.splitlines():
        assert len(linha) <= LARGURA_DO_CELULAR, f"{len(linha)} colunas: {linha}"


def test_top_n_invalido_falha_alto() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DigestConfig(top_n=0)
    with pytest.raises(ValidationError):
        DigestConfig(top_n=100)


# --- Dedupe do envio, contra o Postgres real ---------------------------------
#
# O resumo ia de novo a cada execucao do `daily`. Nao por re-run manual: na
# terca depois de um feriado na segunda, `ultimo` resolve para a sexta que o
# sabado ja processou, e a mensagem chegava repetida sozinha.


@pytest.fixture
def limpa_digest(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as conn:
        conn.execute(delete(DigestSend).where(DigestSend.trade_date == FIM))


@pytest.mark.db
@pytest.mark.usefixtures("limpa_digest")
def test_resumo_nao_e_reenviado_no_mesmo_pregao(engine: Engine) -> None:
    b = barras(["AAAA3", "BBBB4"])
    enviadas: list[str] = []
    notifier = ConsoleNotifier(sent=enviadas)

    primeiro = run_resumo(engine, CONFIG, FIM, notifier=notifier, bars=b)
    assert primeiro.repetido is False
    assert len(enviadas) == 1

    segundo = run_resumo(engine, CONFIG, FIM, notifier=notifier, bars=b)
    assert segundo.repetido is True, "a segunda passada deveria reconhecer o carimbo"
    assert len(enviadas) == 1, "o resumo do mesmo pregao saiu duas vezes"


@pytest.mark.db
@pytest.mark.usefixtures("limpa_digest")
def test_dry_run_mostra_sem_carimbar(engine: Engine) -> None:
    b = barras(["AAAA3", "BBBB4"])
    enviadas: list[str] = []

    ensaio = run_resumo(
        engine, CONFIG, FIM, notifier=ConsoleNotifier(sent=enviadas), bars=b, dry_run=True
    )
    assert ensaio.repetido is False
    assert len(enviadas) == 1
    assert not digest_enviado(engine, FIM), "o ensaio nao pode carimbar"

    # E o envio de verdade continua acontecendo depois do ensaio.
    real = run_resumo(engine, CONFIG, FIM, notifier=ConsoleNotifier(sent=enviadas), bars=b)
    assert real.repetido is False
    assert len(enviadas) == 2


@pytest.mark.db
@pytest.mark.usefixtures("limpa_digest")
def test_telegram_recusando_nao_carimba(engine: Engine) -> None:
    """Se a mensagem nao sai, a proxima passada tem de tentar de novo.

    Carimbar antes do envio perderia o resumo em silencio numa falha de rede --
    exatamente o que este sistema existe para nao fazer.
    """

    class Recusa:
        def send_resumo(self, payload: dict[str, object]) -> bool:
            return False

    negado = run_resumo(engine, CONFIG, FIM, notifier=Recusa(), bars=barras(["AAAA3"]))
    assert negado.repetido is False
    assert not digest_enviado(engine, FIM)


@pytest.mark.db
@pytest.mark.usefixtures("limpa_digest")
def test_carimbo_e_idempotente(engine: Engine) -> None:
    assert marcar_digest_enviado(engine, FIM) is True
    assert marcar_digest_enviado(engine, FIM) is False, "a segunda chamada nao pode duplicar"
    assert digest_enviado(engine, FIM) is True


class NotifierCapturaPayload:
    """Fake notifier que guarda o payload inteiro, nao so o texto formatado.

    `ConsoleNotifier` guarda a mensagem ja formatada; aqui o teste quer
    inspecionar o dicionario que `run_resumo` monta antes de formatar, para
    verificar que a chave `trades` chegou com o conteudo certo.
    """

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def send_resumo(self, payload: dict[str, Any]) -> bool:
        self.payloads.append(dict(payload))
        return True


@pytest.fixture
def trade_com_snapshot_no_dia(engine: Engine) -> Iterator[str]:
    """Um trade aberto de verdade, com snapshot no pregao `FIM`."""
    ticker = "ZRUM1"
    with session_scope(engine) as s:
        s.execute(delete(Trade).where(Trade.ticker == ticker))
    with session_scope(engine) as s:
        trade = Trade(ticker=ticker, aberto_em=FIM)
        s.add(trade)
        s.flush()
        s.add(
            TradeSnapshot(
                trade_id=trade.id,
                trade_date=FIM,
                quantidade=70,
                preco_medio=Decimal("38.000000"),
                custo_comprado=Decimal("5700.00"),
                realizado=Decimal("152.00"),
                fechamento=Decimal("39.1000"),
                valor_posicao=Decimal("2737.00"),
                resultado=Decimal("229.00"),
            )
        )
    yield ticker
    with session_scope(engine) as s:
        s.execute(delete(Trade).where(Trade.ticker == ticker))


@pytest.mark.db
@pytest.mark.usefixtures("limpa_digest")
def test_run_resumo_leva_os_trades_do_pregao_ao_notificador(
    engine: Engine, trade_com_snapshot_no_dia: str
) -> None:
    ticker = trade_com_snapshot_no_dia
    b = barras(["AAAA3", "BBBB4"])
    notifier = NotifierCapturaPayload()

    primeiro = run_resumo(engine, CONFIG, FIM, notifier=notifier, bars=b)
    assert primeiro.repetido is False
    assert len(notifier.payloads) == 1

    trades_no_payload = notifier.payloads[0]["trades"]
    assert {t["ticker"] for t in trades_no_payload} == {ticker}
    linha = trades_no_payload[0]
    assert linha["quantidade"] == 70
    assert linha["resultado"] == pytest.approx(229.00)
    assert linha["encerrado"] is False

    # O resumo repetido continua sem reenviar -- o dedupe da fase 2 nao muda.
    segundo = run_resumo(engine, CONFIG, FIM, notifier=notifier, bars=b)
    assert segundo.repetido is True
    assert len(notifier.payloads) == 1
