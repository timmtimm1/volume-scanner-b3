"""Download dos arquivos da B3, com atencao ao atraso de publicacao."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from scanner.ingest.download import (
    AindaNaoPublicadoError,
    DownloadError,
    annual_filename,
    daily_filename,
    download_daily,
)

DIA = date(2026, 9, 8)


class RespostaFalsa:
    """Resposta minima de httpx.stream, com status controlado."""

    def __init__(self, status: int, corpo: bytes = b"conteudo") -> None:
        self.status_code = status
        self._corpo = corpo

    def __enter__(self) -> RespostaFalsa:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=None)  # type: ignore[arg-type]

    def iter_bytes(self, _tamanho: int) -> list[bytes]:
        return [self._corpo]


def test_nomes_seguem_o_padrao_da_b3() -> None:
    # O diario e DDMMAAAA, nao AAAAMMDD -- errar isso da 404 silencioso.
    assert daily_filename(DIA) == "COTAHIST_D08092026.ZIP"
    assert annual_filename(2026) == "COTAHIST_A2026.ZIP"


def test_404_vira_erro_proprio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: RespostaFalsa(404))

    with pytest.raises(AindaNaoPublicadoError):
        download_daily(DIA, tmp_path, tentativas=1, espera=0)


def test_insiste_enquanto_o_arquivo_nao_saiu(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A B3 leva horas para publicar: 404 logo apos o fechamento quer dizer
    # "espere", nao "deu errado".
    chamadas: list[int] = []

    def stream(*_a: Any, **_k: Any) -> RespostaFalsa:
        chamadas.append(1)
        return RespostaFalsa(404 if len(chamadas) < 3 else 200)

    monkeypatch.setattr(httpx, "stream", stream)
    esperas: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: esperas.append(s))

    caminho = download_daily(DIA, tmp_path, tentativas=4, espera=300)
    assert caminho.is_file()
    assert len(chamadas) == 3
    assert esperas == [300, 300], "deveria ter esperado entre as tentativas"


def test_desiste_depois_do_limite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: RespostaFalsa(404))
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    with pytest.raises(AindaNaoPublicadoError):
        download_daily(DIA, tmp_path, tentativas=3, espera=0)


def test_erro_que_nao_e_404_sobe_na_hora(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Esperar nao conserta rede caida nem 500: so 404 tem retry.
    chamadas: list[int] = []

    def stream(*_a: Any, **_k: Any) -> RespostaFalsa:
        chamadas.append(1)
        raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(httpx, "stream", stream)

    with pytest.raises(DownloadError):
        download_daily(DIA, tmp_path, tentativas=4, espera=0)
    assert len(chamadas) == 1, "erro de rede nao deveria ser repetido"


def test_arquivo_em_cache_nao_e_rebaixado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pronto = tmp_path / daily_filename(DIA)
    pronto.write_bytes(b"ja baixado")

    def stream(*_a: Any, **_k: Any) -> RespostaFalsa:
        raise AssertionError("nao deveria ter ido a rede")

    monkeypatch.setattr(httpx, "stream", stream)
    assert download_daily(DIA, tmp_path).read_bytes() == b"ja baixado"


def test_arquivo_incompleto_nao_fica_no_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # O cache so recebe arquivo inteiro: um .part interrompido nao pode virar
    # cache valido e envenenar a carga do dia seguinte.
    def stream(*_a: Any, **_k: Any) -> RespostaFalsa:
        raise httpx.ReadTimeout("caiu no meio")

    monkeypatch.setattr(httpx, "stream", stream)

    with pytest.raises(DownloadError):
        download_daily(DIA, tmp_path, tentativas=1, espera=0)
    assert list(tmp_path.iterdir()) == []
