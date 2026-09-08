"""Parser COTAHIST.

O fixture `cotahist_sample.txt` sao 100 registros reais extraidos do
COTAHIST_A2026 da B3, mais header e trailer. Os valores esperados abaixo foram
lidos a mao do arquivo, campo por campo, nao gerados pelo parser.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import Engine, delete, text

from scanner.config import IngestConfig
from scanner.ingest.cotahist import (
    FIELDS,
    RECORD_LENGTH,
    TRADES_SENTINEL,
    LayoutError,
    PriceCheckError,
    detect_stride,
    parse_file,
)
from scanner.storage.engine import session_scope
from scanner.storage.models import DailyBar
from scanner.storage.repository import count_bars, upsert_bars

FIXTURE = Path(__file__).parent / "fixtures" / "cotahist_sample.txt"

# Registros do fixture, com CODBDI=02 e TPMERC=010, dos 100 totais.
REGISTROS_QUE_PASSAM = 82

CONFIG = IngestConfig()


@pytest.fixture
def barras() -> pd.DataFrame:
    frame, _ = parse_file(FIXTURE, CONFIG)
    return frame


def patch_records(destino: Path, inicio: int, valor: bytes) -> int:
    """Reescreve `valor` a partir da posicao `inicio` (0-indexada) de cada registro.

    Devolve quantos registros foram alterados. Os testes exigem que esse numero
    seja maior que zero: um patch que nao pega nada faria o teste passar sem
    testar nada -- foi exatamente o que aconteceu quando o fixture trocou de
    CRLF para LF e o split literal parou de casar.
    """
    linhas = FIXTURE.read_bytes().splitlines()
    saida: list[bytes] = []
    alterados = 0
    for r in linhas:
        if len(r) == RECORD_LENGTH and r[:2] == b"01":
            r = r[:inicio] + valor + r[inicio + len(valor) :]
            alterados += 1
        saida.append(r)
    destino.write_bytes(b"\n".join(saida) + b"\n")
    return alterados


def linha(frame: pd.DataFrame, ticker: str) -> pd.Series:
    achadas = frame[frame["ticker"] == ticker]
    assert len(achadas) == 1, f"{ticker}: {len(achadas)} linhas"
    return achadas.iloc[0]


def test_leve3_campo_a_campo(barras: pd.DataFrame) -> None:
    # Leitura manual do registro: PREABE 0000000003417, PREMAX ...3484,
    # PREMIN ...3316, PREMED ...3357, PREULT ...3350, TOTNEG 01954,
    # QUATOT 000000000000320100, VOLTOT 000000001074616400, FATCOT 0000001.
    r = linha(barras, "LEVE3")
    assert r["trade_date"] == pd.Timestamp("2026-01-02")
    assert r["open"] == pytest.approx(34.17)
    assert r["high"] == pytest.approx(34.84)
    assert r["low"] == pytest.approx(33.16)
    assert r["close"] == pytest.approx(33.50)
    assert r["avg_price"] == pytest.approx(33.57)
    assert r["volume_shares"] == 320_100
    assert r["volume_financial"] == pytest.approx(10_746_164.00)
    assert r["trades_count"] == 1954
    assert r["trades_censored"] is False or not bool(r["trades_censored"])


def test_fixture_tem_os_100_registros_esperados() -> None:
    # Guarda contra o fixture ser alterado sem querer: sem isto, varios testes
    # abaixo passariam medindo um arquivo que nao e mais o que se pensa.
    linhas = FIXTURE.read_bytes().splitlines()
    dados = [r for r in linhas if len(r) == RECORD_LENGTH and r[:2] == b"01"]
    assert len(dados) == 100
    assert linhas[0][:2] == b"00"  # header
    assert linhas[-1][:2] == b"99"  # trailer


def test_filtros_descartam_os_outros_codbdi(barras: pd.DataFrame) -> None:
    # O fixture tem 100 registros; 18 sao CODBDI 07/08 e devem sumir.
    assert len(barras) == REGISTROS_QUE_PASSAM


def test_header_e_trailer_nao_viram_barra(barras: pd.DataFrame) -> None:
    assert barras["ticker"].str.startswith("COTAHIST").sum() == 0


def test_fatcot_normaliza_o_preco(barras: pd.DataFrame) -> None:
    # GOLL54 tem FATCOT=1000: PREMED 609 e cotacao por lote de 1000 acoes.
    # Sem dividir, o preco sairia 1000x maior e a barra ficaria inconsistente.
    r = linha(barras, "GOLL54")
    assert r["avg_price"] == pytest.approx(0.00609)
    assert r["close"] == pytest.approx(0.00609)
    assert r["volume_shares"] == 14_428_000
    assert r["volume_financial"] == pytest.approx(87_961.23)


def test_barra_fica_internamente_consistente(barras: pd.DataFrame) -> None:
    # avg_price x volume_shares tem de reproduzir volume_financial em toda linha.
    esperado = barras["avg_price"] * barras["volume_shares"]
    desvio = (esperado - barras["volume_financial"]).abs() / barras["volume_financial"]
    assert desvio.max() < 0.05


def test_papel_de_centavos_so_passa_no_modo_truncation() -> None:
    # AZEV4 negociou a PREMED 0,21 com VOLTOT 829.970,00. Como PREMED e truncado
    # a 2 casas, o desvio relativo da 1,88% e estoura a tolerancia de 1%, sem que
    # haja nada errado com o parser.
    relativo = CONFIG.model_copy(
        update={"price_check_mode": "relative", "price_check_max_failure": 1.0}
    )
    _, rel = parse_file(FIXTURE, relativo)
    _, trunc = parse_file(FIXTURE, CONFIG.model_copy(update={"price_check_mode": "truncation"}))

    assert rel.price_failures > 0
    assert trunc.price_failures == 0


def test_validacao_no_modo_truncation_nao_falha_no_fixture() -> None:
    _, report = parse_file(FIXTURE, CONFIG)
    assert report.failure_rate == 0.0
    assert report.price_checked == REGISTROS_QUE_PASSAM


def test_parser_desalinhado_aborta_a_carga(tmp_path: Path) -> None:
    # Troca VOLTOT por um valor arbitrario em todas as linhas: e o que aconteceria
    # se as posicoes estivessem erradas. A carga tem de parar, nao seguir.
    alvo = tmp_path / "corrompido.txt"
    alterados = patch_records(alvo, 170, b"000000000000999999")
    assert alterados == 100, "o patch nao pegou os registros; o teste nao testaria nada"

    with pytest.raises(PriceCheckError, match="desalinhado"):
        parse_file(alvo, CONFIG)


def test_totneg_censurado_e_marcado(tmp_path: Path) -> None:
    # TOTNEG e N(05) e satura em 99999. Nenhum papel do universo real chegou la
    # (maximo observado em 2024-2026: 98.874), entao o caso e sintetico.
    alvo = tmp_path / "censurado.txt"
    alterados = patch_records(alvo, 147, str(TRADES_SENTINEL).encode())
    assert alterados == 100, "o patch nao pegou os registros; o teste nao testaria nada"

    frame, report = parse_file(alvo, CONFIG)

    assert report.censored_trades == len(frame)
    assert bool(frame["trades_censored"].all())
    assert int(frame["trades_count"].iloc[0]) == TRADES_SENTINEL


def test_largura_de_registro_errada_falha_alto(tmp_path: Path) -> None:
    alvo = tmp_path / "curto.txt"
    alvo.write_bytes(b"01" + b"x" * 100 + b"\r\n")
    with pytest.raises(LayoutError):
        parse_file(alvo, CONFIG)


def test_arquivo_inexistente_falha_alto(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="nao encontrado"):
        parse_file(tmp_path / "nao_existe.txt", CONFIG)


@pytest.mark.parametrize(
    ("head", "esperado"), [(b"x" * 245 + b"\r\n", 247), (b"x" * 245 + b"\n", 246)]
)
def test_detect_stride(head: bytes, esperado: int) -> None:
    assert detect_stride(head) == esperado


def test_stride_incompativel_falha_alto() -> None:
    with pytest.raises(LayoutError):
        detect_stride(b"x" * 100 + b"\n")


def test_posicoes_do_layout_nao_se_sobrepoem() -> None:
    ocupadas: set[int] = set()
    for nome, (inicio, fim) in FIELDS.items():
        faixa = set(range(inicio, fim + 1))
        assert not (faixa & ocupadas), f"{nome} sobrepoe outro campo"
        assert fim <= RECORD_LENGTH, f"{nome} passa do fim do registro"
        ocupadas |= faixa


@pytest.mark.db
def test_carga_e_idempotente(engine: Engine, barras: pd.DataFrame) -> None:
    # Secao 10, teste 7: rodar o pipeline duas vezes produz o mesmo estado.
    # Os tickers ganham prefixo de teste para a carga real nunca ser tocada.
    barras = barras.assign(ticker="ZZ" + barras["ticker"].str.slice(0, 6))
    tickers = sorted(barras["ticker"].unique())
    try:
        antes = count_bars(engine)
        upsert_bars(engine, barras)
        depois_da_primeira = count_bars(engine)

        with engine.connect() as c:
            carimbo = c.execute(
                text(
                    "SELECT ingested_at FROM volume_scanner.daily_bars "
                    "WHERE ticker = :t ORDER BY trade_date LIMIT 1"
                ),
                {"t": tickers[0]},
            ).scalar_one()

        upsert_bars(engine, barras)
        assert count_bars(engine) == depois_da_primeira
        assert depois_da_primeira - antes == len(barras)

        with engine.connect() as c:
            carimbo2 = c.execute(
                text(
                    "SELECT ingested_at FROM volume_scanner.daily_bars "
                    "WHERE ticker = :t ORDER BY trade_date LIMIT 1"
                ),
                {"t": tickers[0]},
            ).scalar_one()
        # Recarga nao mexe em ingested_at: o estado fica identico.
        assert carimbo == carimbo2
    finally:
        with session_scope(engine) as s:
            s.execute(delete(DailyBar).where(DailyBar.ticker.in_(tickers)))
