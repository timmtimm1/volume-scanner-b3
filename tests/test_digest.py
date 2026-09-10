"""Resumo diario do pregao."""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import Engine, delete

from scanner.calendar import sessions_before
from scanner.config import AlertConfig, DigestConfig, ScannerConfig
from scanner.digest import Resumo, montar_resumo, payload_do_resumo, run_resumo
from scanner.features import compute_features
from scanner.metrics import compute_zscores
from scanner.notify.telegram import LARGURA_DO_CELULAR, ConsoleNotifier, format_resumo
from scanner.storage.models import DigestSend
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
