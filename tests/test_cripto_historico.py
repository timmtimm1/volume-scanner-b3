"""O historico diario das moedas da analise: montar, juntar e a carga de cada noite."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from scanner.cripto.commodities import Contrato
from scanner.cripto.historico import (
    INICIO,
    Historico,
    RelatorioDaCarga,
    atualizar,
    de_barras,
    juntar,
    matrizes,
)
from scanner.semana.fontes import FonteIndisponivelError

ONTEM = date(2026, 11, 23)


def _barras(
    inicio: str, fim: str, preco: float = 10.0, *, sem: tuple[str, ...] = ()
) -> pd.DataFrame:
    dias = pd.date_range(inicio, fim, freq="D")
    dias = dias[~dias.isin(pd.to_datetime(list(sem)))]
    return pd.DataFrame(
        {
            "trade_date": dias,
            "close": preco + np.arange(len(dias), dtype="float64"),
            "volume_financial": 1000.0,
        }
    )


def _hist(moeda: str, inicio: str, fim: str, *, vivo: bool = True) -> Historico:
    h = de_barras(moeda, f"{moeda}USDT", "binance", vivo, _barras(inicio, fim))
    assert h is not None
    return h


class Busca:
    """Binance de mentira: devolve barras ate ONTEM e anota cada pedido."""

    def __init__(self, falha: set[str] | None = None, ate: date = ONTEM) -> None:
        self.pedidos: list[tuple[str, date]] = []
        self.falha = falha or set()
        self.ate = ate

    def __call__(self, moeda: str, par: str, desde: date) -> pd.DataFrame:
        self.pedidos.append((moeda, desde))
        if moeda in self.falha:
            raise FonteIndisponivelError("binance", "HTTP 500")
        comeco = max(desde, date(2020, 1, 1))
        return _barras(comeco.isoformat(), self.ate.isoformat())


def test_de_barras_guarda_um_valor_por_dia_com_nan_no_dia_sem_candle() -> None:
    h = de_barras(
        "ETH", "ETHUSDT", "binance", True, _barras("2026-01-01", "2026-01-10", sem=("2026-01-05",))
    )
    assert h is not None
    assert h.primeiro_dia == date(2026, 1, 1)
    assert h.ultimo_dia == date(2026, 1, 10)
    assert len(h.fechamentos) == 10
    assert np.isnan(h.fechamentos[4])
    assert h.serie().index[4] == pd.Timestamp("2026-01-05")


def test_de_barras_sem_nenhuma_barra_e_none() -> None:
    assert de_barras("X", "XUSDT", "binance", True, _barras("2026-01-02", "2026-01-01")) is None


def test_juntar_acrescenta_so_os_dias_novos_e_marca_a_segunda_fonte() -> None:
    h = _hist("XMR", "2024-01-01", "2024-02-20")
    novo = juntar(h, _barras("2024-02-15", "2024-03-05", preco=500.0), fonte="kraken")
    assert novo.ultimo_dia == date(2024, 3, 5)
    # Os dias que ja estavam nao mudam (o preco 500 nao entrou neles).
    assert novo.fechamentos[: len(h.fechamentos)] == pytest.approx(h.fechamentos)
    assert novo.fonte == "binance+kraken"
    assert (
        juntar(novo, _barras("2024-03-06", "2024-03-07"), fonte="kraken").fonte == "binance+kraken"
    )


def test_juntar_com_buraco_deixa_nan_entre_as_partes() -> None:
    h = _hist("XMR", "2024-01-01", "2024-02-20")
    novo = juntar(h, _barras("2024-12-04", "2024-12-10"), fonte="kraken")
    meio = novo.serie()["2024-02-21":"2024-12-03"]
    assert meio.isna().all()
    assert len(meio) == (date(2024, 12, 3) - date(2024, 2, 21)).days + 1


def test_juntar_sem_dia_novo_devolve_o_mesmo() -> None:
    h = _hist("ETH", "2026-01-01", "2026-01-10")
    assert juntar(h, _barras("2026-01-05", "2026-01-10")) is h


def test_matrizes_alinham_as_moedas_no_mesmo_calendario() -> None:
    fech, vol = matrizes(
        [_hist("BTC", "2026-01-01", "2026-01-10"), _hist("NOVA", "2026-01-06", "2026-01-12")]
    )
    assert fech.index[0] == pd.Timestamp("2026-01-01")
    assert fech.index[-1] == pd.Timestamp("2026-01-12")
    assert fech["NOVA"].first_valid_index() == pd.Timestamp("2026-01-06")
    assert fech.loc["2026-01-11", "BTC"] != fech.loc["2026-01-11", "BTC"]  # NaN
    assert vol.shape == fech.shape


def _rodar(
    estado: dict[str, Historico],
    pares: dict[str, str],
    vivos: set[str],
    busca: Busca,
    kraken: Busca | None = None,
) -> tuple[dict[str, Historico], object]:
    return atualizar(
        estado,
        pares,
        vivos,
        ONTEM,
        binance=busca,
        kraken=kraken or Busca(),
        fora_da_binance={},
    )


def test_moeda_nova_vem_inteira_desde_2017() -> None:
    busca = Busca()
    estado, rel = _rodar({}, {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}, {"BTC", "ETH"}, busca)
    assert ("ETH", INICIO) in busca.pedidos
    assert estado["ETH"].ultimo_dia == ONTEM
    assert rel.novas == 2  # type: ignore[attr-defined]


def test_moeda_viva_pede_so_os_dias_depois_do_ultimo() -> None:
    busca = Busca()
    estado = {
        "BTC": _hist("BTC", "2020-01-01", "2026-11-20"),
        "ETH": _hist("ETH", "2020-01-01", "2026-11-20"),
    }
    novo, rel = _rodar(estado, {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}, {"BTC", "ETH"}, busca)
    assert ("ETH", date(2026, 11, 21)) in busca.pedidos
    assert novo["ETH"].ultimo_dia == ONTEM
    assert novo["ETH"].fechamentos[0] == estado["ETH"].fechamentos[0]
    assert rel.atualizadas == 2  # type: ignore[attr-defined]


def test_deslistada_e_moeda_em_dia_nao_geram_pedido() -> None:
    busca = Busca()
    estado = {
        "BTC": _hist("BTC", "2020-01-01", ONTEM.isoformat()),
        "MORTA": _hist("MORTA", "2020-01-01", "2023-05-01"),
    }
    novo, rel = _rodar(estado, {"BTC": "BTCUSDT", "MORTA": "MORTAUSDT"}, {"BTC"}, busca)
    assert busca.pedidos == []
    assert not novo["MORTA"].negociando
    assert novo["MORTA"].ultimo_dia == date(2023, 5, 1)
    assert (rel.em_dia, rel.paradas) == (1, 1)  # type: ignore[attr-defined]


def test_falha_numa_moeda_deixa_ela_como_estava() -> None:
    busca = Busca(falha={"ETH"})
    velho = _hist("ETH", "2020-01-01", "2026-11-20")
    estado = {"BTC": _hist("BTC", "2020-01-01", "2026-11-20"), "ETH": velho}
    novo, rel = _rodar(estado, {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}, {"BTC", "ETH"}, busca)
    assert novo["ETH"] is velho
    assert rel.falhas == ["ETH"]  # type: ignore[attr-defined]


def test_falha_no_btc_para_tudo() -> None:
    with pytest.raises(FonteIndisponivelError):
        _rodar({}, {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}, {"BTC", "ETH"}, Busca(falha={"BTC"}))


def test_btc_atrasado_para_tudo() -> None:
    with pytest.raises(FonteIndisponivelError, match="sem regua"):
        _rodar({}, {"BTC": "BTCUSDT"}, {"BTC"}, Busca(ate=ONTEM - timedelta(days=2)))


def test_moeda_fora_da_binance_continua_pela_kraken() -> None:
    estado = {
        "BTC": _hist("BTC", "2020-01-01", ONTEM.isoformat()),
        "XMR": _hist("XMR", "2019-03-15", "2024-02-20", vivo=False),
    }
    kraken = Busca()
    novo, _ = atualizar(
        estado,
        {"BTC": "BTCUSDT", "XMR": "XMRUSDT"},
        {"BTC"},
        ONTEM,
        binance=Busca(),
        kraken=kraken,
        fora_da_binance={"XMR": "XMRUSD"},
    )
    assert kraken.pedidos == [("XMR", date(2024, 2, 21))]
    assert novo["XMR"].ultimo_dia == ONTEM
    assert novo["XMR"].negociando
    assert novo["XMR"].fonte == "binance+kraken"


def test_moeda_que_sumiu_da_lista_fica_com_o_historico_e_parada() -> None:
    estado = {
        "BTC": _hist("BTC", "2020-01-01", ONTEM.isoformat()),
        "SUMIU": _hist("SUMIU", "2020-01-01", "2022-01-01"),
    }
    novo, _ = _rodar(estado, {"BTC": "BTCUSDT"}, {"BTC"}, Busca())
    assert "SUMIU" in novo
    assert not novo["SUMIU"].negociando


def _com_contratos(
    estado: dict[str, Historico], contratos: dict[str, Contrato], busca: Busca
) -> tuple[dict[str, Historico], RelatorioDaCarga]:
    return atualizar(
        estado,
        {"BTC": "BTCUSDT"},
        {"BTC"},
        ONTEM,
        binance=Busca(),
        kraken=Busca(),
        fora_da_binance={},
        futuros=busca,
        contratos=contratos,
    )


OURO = {"XAU": Contrato("XAUUSDT", date(2025, 12, 11))}


def test_contrato_novo_vem_desde_a_estreia_pelo_arquivo_de_futuros() -> None:
    futuros = Busca(ate=ONTEM - timedelta(days=1))  # o arquivo atrasa um dia
    estado, rel = _com_contratos({}, OURO, futuros)
    assert futuros.pedidos == [("XAU", date(2025, 12, 11))]
    assert estado["XAU"].fonte == "binance-futuros"
    assert estado["XAU"].par == "XAUUSDT"
    assert estado["XAU"].ultimo_dia == ONTEM - timedelta(days=1)
    assert estado["XAU"].negociando
    assert rel.novas == 2


def test_contrato_guardado_pede_so_os_dias_novos_e_nao_vira_parado() -> None:
    estado = {
        "BTC": _hist("BTC", "2020-01-01", ONTEM.isoformat()),
        "XAU": _hist("XAU", "2025-12-11", "2026-11-20"),
    }
    futuros = Busca()
    novo, _ = _com_contratos(estado, OURO, futuros)
    assert futuros.pedidos == [("XAU", date(2026, 11, 21))]
    assert novo["XAU"].ultimo_dia == ONTEM
    assert novo["XAU"].negociando


def test_falha_no_contrato_fica_como_estava_e_nao_para_a_carga() -> None:
    velho = _hist("XAU", "2025-12-11", "2026-11-20")
    estado = {"BTC": _hist("BTC", "2020-01-01", ONTEM.isoformat()), "XAU": velho}
    novo, rel = _com_contratos(estado, OURO, Busca(falha={"XAU"}))
    assert novo["XAU"] is velho
    assert rel.falhas == ["XAU"]


def test_ticker_do_contrato_que_aparece_a_vista_nao_mistura_as_series() -> None:
    futuros = Busca()
    novo, rel = atualizar(
        {},
        {"BTC": "BTCUSDT", "XAU": "XAUUSDT"},
        {"BTC", "XAU"},
        ONTEM,
        binance=Busca(),
        kraken=Busca(),
        fora_da_binance={},
        futuros=futuros,
        contratos=OURO,
    )
    assert futuros.pedidos == []
    assert novo["XAU"].fonte == "binance"
    assert rel.falhas == ["XAU (ticker repetido no mercado a vista)"]


def test_contratos_sem_a_busca_de_futuros_e_erro_de_quem_chama() -> None:
    with pytest.raises(ValueError, match="futuros"):
        atualizar(
            {},
            {"BTC": "BTCUSDT"},
            {"BTC"},
            ONTEM,
            binance=Busca(),
            kraken=Busca(),
            fora_da_binance={},
            contratos=OURO,
        )
