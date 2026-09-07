"""Parser posicional do COTAHIST (secao 2 do plano).

Registro de largura fixa de 245 bytes. As posicoes abaixo sao 1-indexadas e
inclusivas, como no layout da B3, e foram conferidas contra um arquivo real.

Campos `V99` tem 2 decimais implicitos: leem-se como inteiro e dividem-se por 100.

FATCOT (fator de cotacao) nao esta na tabela da secao 2 do plano, mas e
necessario: em 0,5% das linhas o preco e cotado por lote de 100, 1.000 ou
1.000.000 de acoes. Os precos sao divididos por ele, senao a barra fica
internamente inconsistente e `close x volume_shares` erra por 1.000x.

PREMED e TRUNCADO a 2 casas, nunca arredondado: em 100% das linhas de um arquivo
real, `PREMED x QUATOT / FATCOT <= VOLTOT`. Isso torna a identidade de preco
inalcancavel dentro de 1% para papel abaixo de R$ 1,00, onde o erro de
quantizacao sozinho ja passa disso. Dai os dois modos de validacao.

A extracao e vetorizada: o arquivo vira uma matriz de bytes e cada campo e uma
fatia de colunas. Nenhum loop por linha.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import numpy as np
import numpy.typing as npt
import pandas as pd

from scanner.config import IngestConfig

RECORD_LENGTH = 245

# TOTNEG e N(05): 99999 e teto do campo, nao contagem real de negocios.
TRADES_SENTINEL = 99999

# nome -> (posicao inicial, posicao final), 1-indexado inclusivo.
FIELDS: dict[str, tuple[int, int]] = {
    "TIPREG": (1, 2),
    "DATA": (3, 10),
    "CODBDI": (11, 12),
    "CODNEG": (13, 24),
    "TPMERC": (25, 27),
    "PREABE": (57, 69),
    "PREMAX": (70, 82),
    "PREMIN": (83, 95),
    "PREMED": (96, 108),
    "PREULT": (109, 121),
    "TOTNEG": (148, 152),
    "QUATOT": (153, 170),
    "VOLTOT": (171, 188),
    "FATCOT": (211, 217),
}

BAR_COLUMNS = (
    "ticker",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "avg_price",
    "volume_shares",
    "volume_financial",
    "trades_count",
    "trades_censored",
)


class CotahistError(Exception):
    """Falha ao ler um arquivo COTAHIST."""


class LayoutError(CotahistError):
    """O arquivo nao tem a largura de registro esperada."""


class PriceCheckError(CotahistError):
    """VOLTOT ~= PREMED x QUATOT falhou acima do tolerado: parser desalinhado."""


@dataclass(frozen=True)
class IngestReport:
    """O que a leitura de um arquivo encontrou."""

    source: str
    total_records: int
    kept: int
    price_checked: int
    price_failures: int
    censored_trades: int

    @property
    def failure_rate(self) -> float:
        """Fracao das linhas checaveis que violou a identidade de preco."""
        return self.price_failures / self.price_checked if self.price_checked else 0.0

    def summary(self) -> str:
        """Uma linha para log e CLI."""
        return (
            f"{self.source}: {self.total_records:,} registros, {self.kept:,} apos filtros, "
            f"validacao de preco {1 - self.failure_rate:.3%} ok "
            f"({self.price_failures:,} falhas), {self.censored_trades:,} com TOTNEG censurado"
        )


@contextmanager
def open_records(path: Path) -> Iterator[IO[bytes]]:
    """Abre o .TXT do COTAHIST, esteja ele solto ou dentro do .ZIP da B3."""
    if path.suffix.upper() == ".ZIP":
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.upper().endswith(".TXT")]
            if len(names) != 1:
                raise LayoutError(f"{path.name} deveria ter exatamente um .TXT, tem {names}")
            with archive.open(names[0]) as handle:
                yield handle
    else:
        with path.open("rb") as handle:
            yield handle


def detect_stride(head: bytes) -> int:
    """Bytes por linha, incluindo a quebra: 246 com LF, 247 com CRLF."""
    newline = head.find(b"\n")
    if newline == -1:
        raise LayoutError("nenhuma quebra de linha nos primeiros bytes do arquivo")
    stride = newline + 1
    if stride - RECORD_LENGTH not in (1, 2):
        raise LayoutError(
            f"linha de {stride} bytes: esperado {RECORD_LENGTH} mais quebra de 1 ou 2 bytes"
        )
    return stride


def _field(matrix: npt.NDArray[np.uint8], name: str) -> npt.NDArray[np.bytes_]:
    """Uma coluna posicional da matriz de bytes, como array de bytes."""
    start, end = FIELDS[name]
    width = end - start + 1
    sliced: npt.NDArray[np.bytes_] = matrix[:, start - 1 : end].copy().view(f"S{width}")
    return sliced.ravel()


def _as_int(column: npt.NDArray[np.bytes_]) -> npt.NDArray[np.int64]:
    """Campo numerico zero-preenchido para inteiro."""
    return column.astype(np.int64)


def _read_matrix(handle: IO[bytes], stride: int, records: int) -> npt.NDArray[np.uint8] | None:
    """Le um bloco e devolve a matriz (linhas x stride), ou None no fim do arquivo."""
    buffer = handle.read(stride * records)
    if not buffer:
        return None
    if len(buffer) % stride:
        raise LayoutError(
            f"bloco de {len(buffer)} bytes nao e multiplo da linha de {stride}: "
            "o arquivo tem registro de largura irregular"
        )
    return np.frombuffer(buffer, dtype=np.uint8).reshape(-1, stride)


def _rows_from_matrix(
    matrix: npt.NDArray[np.uint8], config: IngestConfig
) -> tuple[pd.DataFrame, npt.NDArray[np.float64]]:
    """Barras do bloco mais o quantum de preco (0,01 / FATCOT) de cada linha."""
    keep = (
        (_field(matrix, "TIPREG") == config.tipreg.encode())
        & (_field(matrix, "CODBDI") == config.codbdi.encode())
        & (_field(matrix, "TPMERC") == config.tpmerc.encode())
    )
    selected = matrix[keep]
    if not len(selected):
        return pd.DataFrame(columns=list(BAR_COLUMNS)), np.zeros(0, dtype=float)

    trades = _as_int(_field(selected, "TOTNEG"))
    # Fator de cotacao: preco cotado por lote de FATCOT acoes.
    lot = _as_int(_field(selected, "FATCOT")).astype(float)
    frame = pd.DataFrame(
        {
            "ticker": np.char.strip(_field(selected, "CODNEG").astype(str)),
            "trade_date": pd.to_datetime(_field(selected, "DATA").astype(str), format="%Y%m%d"),
            "open": _as_int(_field(selected, "PREABE")) / 100.0 / lot,
            "high": _as_int(_field(selected, "PREMAX")) / 100.0 / lot,
            "low": _as_int(_field(selected, "PREMIN")) / 100.0 / lot,
            "close": _as_int(_field(selected, "PREULT")) / 100.0 / lot,
            "avg_price": _as_int(_field(selected, "PREMED")) / 100.0 / lot,
            "volume_shares": _as_int(_field(selected, "QUATOT")),
            "volume_financial": _as_int(_field(selected, "VOLTOT")) / 100.0,
            "trades_count": trades,
            "trades_censored": trades >= TRADES_SENTINEL,
        }
    )
    return frame, 0.01 / lot


def price_check(
    frame: pd.DataFrame, quantum: npt.NDArray[np.float64], config: IngestConfig
) -> tuple[int, int]:
    """(linhas checaveis, falhas) da validacao VOLTOT contra PREMED x QUATOT.

    `relative` e a regra literal do plano: desvio relativo dentro da tolerancia.
    `truncation` usa a aritmetica exata do campo truncado: VOLTOT tem de cair em
    [PREMED, PREMED + quantum) x QUATOT.
    """
    volume = frame["volume_financial"].to_numpy(dtype=float)
    checkable = volume > 0
    if not checkable.any():
        return 0, 0

    shares = frame["volume_shares"].to_numpy(dtype=float)
    floor = frame["avg_price"].to_numpy(dtype=float) * shares

    if config.price_check_mode == "truncation":
        ceiling = floor + quantum * shares
        # Folga de 1e-6 apenas para ruido de ponto flutuante, nao de tolerancia.
        ok = (volume >= floor * (1 - 1e-6)) & (volume <= ceiling * (1 + 1e-6))
    else:
        deviation = np.abs(floor - volume) / np.where(checkable, volume, 1.0)
        ok = deviation <= config.price_check_tolerance

    return int(checkable.sum()), int((checkable & ~ok).sum())


def parse_file(
    path: Path, config: IngestConfig, *, chunk_records: int = 200_000
) -> tuple[pd.DataFrame, IngestReport]:
    """Le um COTAHIST inteiro e devolve as barras filtradas mais o relatorio.

    Levanta `PriceCheckError` se a identidade de preco falhar acima do tolerado:
    isso significa parser desalinhado, e carregar seria pior do que abortar.
    """
    if not path.is_file():
        raise CotahistError(f"arquivo nao encontrado: {path}")

    blocks: list[pd.DataFrame] = []
    total = checked = failures = 0

    with open_records(path) as handle:
        stride = detect_stride(handle.read(RECORD_LENGTH + 2))
        handle.seek(0)

        while (matrix := _read_matrix(handle, stride, chunk_records)) is not None:
            total += int((_field(matrix, "TIPREG") == config.tipreg.encode()).sum())
            block, quantum = _rows_from_matrix(matrix, config)
            if block.empty:
                continue
            block_checked, block_failures = price_check(block, quantum, config)
            checked += block_checked
            failures += block_failures
            blocks.append(block)

    frame = (
        pd.concat(blocks, ignore_index=True) if blocks else pd.DataFrame(columns=list(BAR_COLUMNS))
    )
    report = IngestReport(
        source=path.name,
        total_records=total,
        kept=len(frame),
        price_checked=checked,
        price_failures=failures,
        censored_trades=int(frame["trades_censored"].sum()) if len(frame) else 0,
    )

    if report.failure_rate > config.price_check_max_failure:
        raise PriceCheckError(
            f"{path.name}: VOLTOT ~= PREMED x QUATOT falhou em "
            f"{report.failure_rate:.3%} das linhas, acima do teto de "
            f"{config.price_check_max_failure:.3%}. O parser esta desalinhado; "
            "carga abortada."
        )
    return frame, report
