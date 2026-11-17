"""Tendencia pela inclinacao das medias: a conta do pregao e a troca da tabela."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine, select

from scanner.storage.engine import session_scope
from scanner.storage.models import Tendencia
from scanner.storage.repository import gravar_tendencias
from scanner.tendencia import COLUNAS, COLUNAS_DE_MEDIA, calcular, run_tendencias

DIAS = pd.bdate_range("2025-01-02", periods=260)
ULTIMO = DIAS[-1].date()


def _serie(
    ticker: str,
    fech: np.ndarray,
    volume: float,
    datas: pd.DatetimeIndex = DIAS,
    abertura: np.ndarray | None = None,
) -> pd.DataFrame:
    if abertura is None:
        abertura = np.concatenate([[fech[0]], fech[:-1]])
    return pd.DataFrame(
        {
            "ticker": ticker,
            "trade_date": datas,
            "open": abertura,
            "high": np.maximum(abertura, fech) * 1.001,
            "low": np.minimum(abertura, fech) * 0.999,
            "close": fech,
            "volume_financial": volume,
        }
    )


def _barras() -> pd.DataFrame:
    i = np.arange(len(DIAS))
    sobe = 10 * 1.002**i
    cai = 50 * 0.998**i
    # Desdobramento 2:1 no meio: o preco cai pela metade de um dia para o outro,
    # mas a tendencia continua subindo -- o ajuste tem de enxergar isso.
    desd = 20 * 1.002**i
    desd[150:] = desd[150:] / 2
    # a abertura do dia do desdobramento ja vem na escala nova: e por esse
    # salto (abertura contra o fechamento anterior) que o ajuste o reconhece
    abertura_desd = np.concatenate([[desd[0]], desd[:-1]])
    abertura_desd[150] = desd[149] / 2
    partes = [
        _serie("SOBE3", sobe, 1e6),
        _serie("CAI3", cai, 1e6),
        _serie("NOVA3", 5 * 1.01 ** np.arange(30), 1e6, DIAS[-30:]),
        _serie("POUCO3", sobe, 1e4),
        _serie("PAROU3", sobe[:-1], 1e6, DIAS[:-1]),
        _serie("DESD3", desd, 1e6, abertura=abertura_desd),
    ]
    return pd.concat(partes, ignore_index=True)


@pytest.fixture(scope="module")
def tabela() -> pd.DataFrame:
    return calcular(_barras(), ULTIMO).set_index("ticker")


def test_colunas_e_so_quem_negociou_no_pregao(tabela: pd.DataFrame) -> None:
    assert list(tabela.reset_index().columns) == list(COLUNAS)
    assert "PAROU3" not in tabela.index
    assert set(tabela["trade_date"]) == {ULTIMO}


def test_subindo_tem_todas_as_medias_para_cima(tabela: pd.DataFrame) -> None:
    assert (tabela.loc["SOBE3", list(COLUNAS_DE_MEDIA)] == 1).all()
    assert tabela.loc["SOBE3", "variacao"] == pytest.approx(0.002, rel=1e-6)


def test_caindo_tem_todas_para_baixo(tabela: pd.DataFrame) -> None:
    assert (tabela.loc["CAI3", list(COLUNAS_DE_MEDIA)] == -1).all()


def test_sem_historico_vale_zero_e_nao_inventa_direcao(tabela: pd.DataFrame) -> None:
    nova = tabela.loc["NOVA3"]
    assert nova["mme9"] == 1 and nova["mme20"] == 1
    for coluna in ("mme50", "mme80", "mme200", "mma50", "mma80", "mma200"):
        assert nova[coluna] == 0, coluna


def test_liquidez_pela_mediana_de_60_pregoes(tabela: pd.DataFrame) -> None:
    assert bool(tabela.loc["SOBE3", "liquido"]) is True
    assert bool(tabela.loc["POUCO3", "liquido"]) is False  # R$ 10 mil por dia
    assert bool(tabela.loc["NOVA3", "liquido"]) is False  # 30 pregoes, menos que 48


def test_desdobramento_nao_vira_queda(tabela: pd.DataFrame) -> None:
    """Sem o ajuste, o preco pela metade derrubaria a media de 200 por meses."""
    assert (tabela.loc["DESD3", list(COLUNAS_DE_MEDIA)] == 1).all()
    assert tabela.loc["DESD3", "variacao"] == pytest.approx(0.002, rel=1e-6)


def test_pregao_avaliado_e_o_ultimo_ate_o_dia_pedido() -> None:
    """Pedir um dia antes do fim da serie avalia aquele dia, sem olhar o futuro."""
    dia = DIAS[200].date()
    t = calcular(_barras(), dia)
    assert set(t["trade_date"]) == {dia}
    assert "NOVA3" not in set(t["ticker"])  # so comecou a negociar depois


def test_sem_barras_nao_quebra() -> None:
    assert calcular(_barras().head(0), ULTIMO).empty
    relatorio = run_tendencias(None, ULTIMO, bars=_barras().head(0), dry_run=True)  # type: ignore[arg-type]
    assert relatorio.ativos == 0
    assert "nenhum ativo" in relatorio.summary()


def test_resumo_conta_pela_combinacao_padrao() -> None:
    relatorio = run_tendencias(None, ULTIMO, bars=_barras(), dry_run=True)  # type: ignore[arg-type]
    assert relatorio.ativos == 5
    assert relatorio.liquidos == 3  # SOBE3, CAI3 e DESD3
    assert relatorio.alta == 2 and relatorio.baixa == 1
    assert relatorio.summary().startswith("[dry-run] tendencia: 5 ativos nao gravados")


@pytest.mark.db
def test_gravar_troca_a_tabela_inteira(engine: Engine) -> None:
    primeira = calcular(_barras(), ULTIMO)
    assert gravar_tendencias(engine, primeira) == len(primeira)
    so_uma = primeira[primeira["ticker"] == "SOBE3"]
    assert gravar_tendencias(engine, so_uma) == 1

    with session_scope(engine) as s:
        linhas = s.execute(select(Tendencia)).scalars().all()
        assert [linha.ticker for linha in linhas] == ["SOBE3"]
        assert linhas[0].mme200 == 1
        assert linhas[0].liquido is True
