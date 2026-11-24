"""Candles dos contratos perpetuos pelo arquivo publico da Binance."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime

import httpx
import pandas as pd
import pytest

from scanner.cripto import futuros
from scanner.semana.fontes import FonteIndisponivelError

CABECALHO = (
    "open_time,open,high,low,close,volume,close_time,quote_volume,count,"
    "taker_buy_volume,taker_buy_quote_volume,ignore"
)
MS_POR_DIA = 86_400_000


def _ms(dia: date) -> int:
    return int(datetime(dia.year, dia.month, dia.day, tzinfo=UTC).timestamp() * 1000)


def _linha(dia: date, preco: float, *, micro: bool = False) -> str:
    abre = _ms(dia)
    fecha = abre + MS_POR_DIA - 1
    if micro:
        abre, fecha = abre * 1000, fecha * 1000 + 999
    return f"{abre},{preco},{preco + 1},{preco - 1},{preco},10,{fecha},{preco * 10},5,1,1,0"


def _zip(linhas: list[str], *, cabecalho: bool = True) -> bytes:
    corpo = "\n".join(([CABECALHO] if cabecalho else []) + linhas) + "\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as pacote:
        pacote.writestr("XAUUSDT-1d.csv", corpo)
    return buffer.getvalue()


def test_zip_com_e_sem_cabecalho_e_horario_em_microssegundo() -> None:
    dia = date(2026, 10, 1)
    com = futuros.zip_para_candles(_zip([_linha(dia, 4000.0)]))
    sem = futuros.zip_para_candles(_zip([_linha(dia, 4000.0)], cabecalho=False))
    micro = futuros.zip_para_candles(_zip([_linha(dia, 4000.0, micro=True)]))
    assert com == sem == micro
    assert com[0][0] == _ms(dia)
    assert com[0][4] == "4000.0"  # fechamento
    assert com[0][7] == "40000.0"  # volume em dolar


def test_arquivo_que_nao_e_zip_e_fonte_indisponivel() -> None:
    with pytest.raises(FonteIndisponivelError, match="nao e zip"):
        futuros.zip_para_candles(b"<html>")


class Arquivo:
    """O arquivo publico de mentira: meses e dias publicados, o resto e 404."""

    def __init__(self, meses: set[str], dias: set[date], *, erro: int | None = None) -> None:
        self.meses = meses
        self.dias = dias
        self.erro = erro
        self.pedidos: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.pedidos.append(url.rsplit("/", 1)[-1])
        if self.erro is not None:
            return httpx.Response(self.erro)
        nome = url.rsplit("/", 1)[-1].removesuffix(".zip").removeprefix("XAUUSDT-1d-")
        if "/monthly/" in url and nome in self.meses:
            mes = date.fromisoformat(f"{nome}-01")
            dias = pd.date_range(mes, mes + pd.offsets.MonthEnd(0), freq="D")
            return httpx.Response(200, content=_zip([_linha(d.date(), 100.0) for d in dias]))
        if "/daily/" in url and date.fromisoformat(nome) in self.dias:
            return httpx.Response(200, content=_zip([_linha(date.fromisoformat(nome), 200.0)]))
        return httpx.Response(404)


AGORA = datetime(2026, 11, 25, 0, 20, tzinfo=UTC)  # a rodada da noite de 24/11


def _buscar(arquivo: Arquivo, desde: date, agora: datetime = AGORA) -> pd.DataFrame:
    with httpx.Client(transport=httpx.MockTransport(arquivo)) as cliente:
        return futuros.buscar_barras("XAU", "XAUUSDT", desde, agora=agora, cliente=cliente)


def test_meses_fechados_pelo_zip_do_mes_e_o_mes_corrente_dia_a_dia() -> None:
    dias = {date(2026, 11, d) for d in range(1, 24)}  # o de 24/11 ainda nao saiu
    arquivo = Arquivo({"2026-09", "2026-10"}, dias)
    barras = _buscar(arquivo, date(2026, 9, 15))
    assert barras["trade_date"].min() == pd.Timestamp("2026-09-15")  # o comeco do mes fica
    assert barras["trade_date"].max() == pd.Timestamp("2026-11-23")
    assert barras["trade_date"].is_unique
    assert len(barras) == (date(2026, 11, 23) - date(2026, 9, 15)).days + 1
    assert arquivo.pedidos[:2] == ["XAUUSDT-1d-2026-09.zip", "XAUUSDT-1d-2026-10.zip"]
    assert arquivo.pedidos[-1] == "XAUUSDT-1d-2026-11-24.zip"  # o 404 que para
    assert barras["volume_financial"].iloc[-1] == pytest.approx(2000.0)


def test_mes_que_acabou_de_fechar_sem_zip_vai_dia_a_dia() -> None:
    agora = datetime(2026, 12, 2, 0, 20, tzinfo=UTC)
    dias = {date(2026, 11, d) for d in range(1, 31)}
    barras = _buscar(Arquivo(set(), dias), date(2026, 11, 29), agora)
    assert list(barras["trade_date"].dt.day) == [29, 30]  # 01/12 ainda nao saiu


def test_dia_que_falta_para_tudo_sem_deixar_buraco() -> None:
    dias = {date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 4)}
    barras = _buscar(Arquivo(set(), dias), date(2026, 11, 1))
    assert list(barras["trade_date"].dt.day) == [1, 2]


def test_nada_novo_publicado_e_vazio() -> None:
    barras = _buscar(Arquivo(set(), set()), date(2026, 11, 24))
    assert barras.empty


def test_erro_que_nao_e_404_e_fonte_indisponivel() -> None:
    with pytest.raises(FonteIndisponivelError):
        _buscar(Arquivo(set(), set(), erro=500), date(2026, 11, 20))
