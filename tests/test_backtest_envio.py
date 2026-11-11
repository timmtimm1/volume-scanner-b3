"""O resultado da suite no banco (scanner.backtest.envio).

Os dois primeiros testes nao precisam do Postgres; os outros usam o banco de
teste da `conftest` e pulam se ele nao estiver de pe.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine, delete, func, select

from scanner.backtest.envio import (
    COLUNAS_ESCOLHA,
    COLUNAS_RESULTADO,
    _linhas,
    amostra_de_trades,
    enviar,
    resumo_da_rodada,
)
from scanner.backtest.metricas import curva, escolher, grade, por_ano
from scanner.backtest.pacote import gravar_pacote, ler_pacote
from scanner.backtest.simulador import ABERTO, ALVO, STOP
from scanner.storage.engine import session_scope
from scanner.storage.models import (
    BacktestCurva,
    BacktestEscolha,
    BacktestResultado,
    BacktestRodada,
    BacktestTrade,
)


def _trades(n_por: int = 300, semente: int = 1) -> pd.DataFrame:
    """Trades falsos de dois setups e duas saidas, de 1996 a 2026."""
    rng = np.random.default_rng(semente)
    partes = []
    for setup in ("9.1", "forca"):
        for saida in ("alvo2", "mme9"):
            entrada = pd.to_datetime(
                rng.integers(
                    pd.Timestamp("1996-01-01").value, pd.Timestamp("2026-09-01").value, n_por
                )
            )
            r = rng.normal(0.05, 1.2, n_por)
            motivo = np.where(r > 0, ALVO, STOP).astype(np.int8)
            motivo[:3] = ABERTO
            partes.append(
                pd.DataFrame(
                    {
                        "setup": setup,
                        "saida": saida,
                        "ticker": rng.choice(["PETR4", "VALE3", "ITUB4"], n_por),
                        "data_sinal": entrada - pd.Timedelta(days=1),
                        "data_entrada": entrada,
                        "data_saida": entrada + pd.Timedelta(days=7),
                        "entrada": np.float32(20.0),
                        "stop": np.float32(19.0),
                        "risco_pct": np.float32(0.05),
                        "motivo": motivo,
                        "dias": np.int16(5),
                        "r": r.astype(np.float32),
                        "r_bruto": (r + 0.03).astype(np.float32),
                        "r_controle": rng.normal(0.0, 1.0, n_por).astype(np.float32),
                        "alta": rng.random(n_por) > 0.4,
                        "rvol": rng.uniform(0.5, 3.0, n_por).astype(np.float32),
                        "z": np.float32(0.0),
                    }
                )
            )
    t = pd.concat(partes, ignore_index=True)
    for c in ("setup", "saida", "ticker"):
        t[c] = t[c].astype("category")
    return t


def test_amostra_pega_os_mais_recentes_de_cada_combinacao() -> None:
    t = _trades()
    a = amostra_de_trades(t, por_combinacao=20)
    assert len(a) == 4 * 20
    for (setup, saida), parte in a.groupby(["setup", "saida"]):
        origem = t[(t["setup"] == setup) & (t["saida"] == saida)]
        assert parte["data_entrada"].min() >= origem["data_entrada"].nlargest(20).min()
    # preco de saida pelo R bruto: entrada + R x (entrada - stop)
    fechado = a[a["motivo"] != "aberto"].iloc[0]
    linha = t[
        (t["data_entrada"] == fechado["data_entrada"]) & (t["setup"] == fechado["setup"])
    ].iloc[0]
    assert fechado["preco_saida"] == pytest.approx(20.0 + float(linha["r_bruto"]), abs=1e-3)


def test_trade_aberto_vai_sem_saida() -> None:
    t = _trades()
    a = amostra_de_trades(t, por_combinacao=len(t))
    abertos = a[a["motivo"] == "aberto"]
    assert len(abertos) == 4 * 3  # os 3 primeiros de cada combinacao estao abertos
    assert abertos["preco_saida"].isna().all()
    assert abertos["r"].isna().all()
    assert abertos["data_saida"].isna().all()
    assert a.loc[a["motivo"] != "aberto", "preco_saida"].notna().all()


@pytest.fixture
def limpo(engine: Engine) -> Iterator[Engine]:
    with session_scope(engine) as s:
        s.execute(delete(BacktestRodada))
    yield engine
    with session_scope(engine) as s:
        s.execute(delete(BacktestRodada))


def _enviar(engine: Engine, t: pd.DataFrame, manter: int = 2) -> int:
    g = grade(t)
    return enviar(
        engine,
        rodada=resumo_da_rodada(t, 0.0008, 60),
        grade=g,
        escolha=escolher(g),
        anos=por_ano(t),
        curva=curva(t),
        amostra=amostra_de_trades(t, por_combinacao=50),
        manter=manter,
    )


def test_pacote_guarda_a_rodada_como_ela_vai_para_o_banco(tmp_path: Path) -> None:
    """O pacote (JSON, sem os trades) tem de gerar as MESMAS linhas que a pasta do
    resultado geraria: e ele que o workflow `backtest-enviar` grava em producao."""
    t = _trades()
    g = grade(t)
    antes = {
        "rodada": resumo_da_rodada(t, 0.0008, 60),
        "grade": g,
        "escolha": escolher(g),
        "anos": por_ano(t),
        "curva": curva(t),
        "amostra": amostra_de_trades(t),
    }
    arquivo = tmp_path / "rodada.json.gz"
    gravar_pacote(arquivo, **antes)
    depois = ler_pacote(arquivo)

    assert depois["rodada"] == antes["rodada"]
    # o setup "9.1" continua texto: lido como numero, a rodada perderia a chave
    assert set(depois["grade"]["setup"]) == {"9.1", "forca"}
    for nome, colunas in (
        ("grade", COLUNAS_RESULTADO),
        ("escolha", COLUNAS_ESCOLHA),
        ("amostra", ("setup", "ticker", "data_sinal", "data_saida", "entrada", "r", "alta")),
    ):
        a, d = _linhas(antes[nome], colunas), _linhas(depois[nome], colunas)
        assert len(a) == len(d), nome
        for la, ld in zip(a, d, strict=True):
            for coluna in colunas:
                if isinstance(la[coluna], float):
                    assert ld[coluna] == pytest.approx(la[coluna], rel=1e-9), (nome, coluna)
                else:
                    assert ld[coluna] == la[coluna], (nome, coluna)


def test_pacote_incompleto_e_recusado(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="faltam tabelas"):
        gravar_pacote(tmp_path / "x.json.gz", rodada={}, grade=pd.DataFrame())


def test_rodada_inteira_vai_para_o_banco(limpo: Engine) -> None:
    t = _trades()
    rodada_id = _enviar(limpo, t)
    with session_scope(limpo) as s:
        r = s.get(BacktestRodada, rodada_id)
        assert r is not None
        assert r.trades == len(t[t["motivo"] != ABERTO])
        assert r.papeis == 3
        n_grade = s.scalar(
            select(func.count())
            .select_from(BacktestResultado)
            .where(BacktestResultado.rodada_id == rodada_id)
        )
        assert n_grade == 2 * 2 * 3 * 3  # setup x saida x grupo x periodo
        niveis = set(
            s.scalars(select(BacktestEscolha.nivel).where(BacktestEscolha.rodada_id == rodada_id))
        )
        assert niveis <= {"firme", "fraco", "falhou"}
        n_trades = s.scalar(
            select(func.count())
            .select_from(BacktestTrade)
            .where(BacktestTrade.rodada_id == rodada_id)
        )
        assert n_trades == 4 * 50
        assert s.scalar(
            select(func.count())
            .select_from(BacktestCurva)
            .where(BacktestCurva.rodada_id == rodada_id)
        )


def test_ficam_so_as_duas_ultimas_rodadas(limpo: Engine) -> None:
    t = _trades()
    ids = [_enviar(limpo, t) for _ in range(3)]
    with session_scope(limpo) as s:
        sobram = sorted(s.scalars(select(BacktestRodada.id)))
        assert sobram == ids[1:]
        # o cascade levou as filhas da rodada apagada
        orfas = s.scalar(
            select(func.count()).select_from(BacktestTrade).where(BacktestTrade.rodada_id == ids[0])
        )
        assert orfas == 0


def test_nan_vira_null(limpo: Engine) -> None:
    t = _trades(n_por=40)  # poucos trades: a escolha fica sem combinacao valida (minimo 100)
    rodada_id = _enviar(limpo, t)
    with session_scope(limpo) as s:
        e = s.scalars(select(BacktestEscolha).where(BacktestEscolha.rodada_id == rodada_id)).all()
        assert all(x.nivel == "falhou" and x.saida is None and x.exp_conferencia is None for x in e)


def test_trade_aberto_fica_sem_data_de_saida_no_banco(limpo: Engine) -> None:
    # regressao: NaT ia para o banco como 21/11/48113
    t = _trades()
    t.loc[t["motivo"] == ABERTO, "data_saida"] = pd.NaT
    t.loc[t["motivo"] == ABERTO, "data_entrada"] = pd.Timestamp("2026-10-01")  # entram na amostra
    rodada_id = _enviar(limpo, t)
    with session_scope(limpo) as s:
        abertos = s.scalars(
            select(BacktestTrade).where(
                BacktestTrade.rodada_id == rodada_id, BacktestTrade.motivo == "aberto"
            )
        ).all()
        assert abertos
        assert all(x.data_saida is None and x.preco_saida is None and x.r is None for x in abertos)
