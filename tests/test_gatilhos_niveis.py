"""Motor de suporte e resistencia (scanner.gatilhos.niveis)."""

from __future__ import annotations

import dataclasses

import numpy as np
import numpy.typing as npt
import pytest

from scanner.gatilhos.niveis import (
    FUNDIDO,
    ROMPEU,
    Regras,
    Retrato,
    detectar,
    pivos,
)

F64 = npt.NDArray[np.float64]

# ATR fixo de 0,4: tolerancia de 0,2 (meio ATR) e furo ate 0,6 (1,5 ATR).
ATR = 0.4


def _barras(caminho: list[float], pavio: float = 0.05) -> tuple[F64, F64, F64, F64]:
    """Um papel: cada candle abre no fechamento anterior e fecha no ponto do caminho."""
    c = np.array(caminho, dtype=np.float64)
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.fmax(o, c) + pavio
    low = np.fmin(o, c) - pavio
    return o[:, None], h[:, None], low[:, None], c[:, None]


def _serra(fundos: list[float], topo: float = 12.0, meia: int = 5) -> list[float]:
    """Desce do topo ate cada fundo e volta, em `meia` pregoes para cada lado."""
    caminho = [topo]
    for f in fundos:
        caminho += list(np.linspace(topo, f, meia + 1)[1:])
        caminho += list(np.linspace(f, topo, meia + 1)[1:])
    return caminho


def _rodar(
    o: F64, h: F64, low: F64, c: F64, regras: Regras | None = None
) -> tuple[Retrato, object]:
    atr = np.full_like(c, ATR)
    atr[np.isnan(c)] = np.nan
    return detectar(h, low, c, atr, regras)


def test_pivos_respeitam_k_e_empate() -> None:
    low = np.array([5, 4, 3, 2, 3, 4, 5, 2, 3, 4, 5], dtype=np.float64)[:, None]
    fundo, _ = pivos(low, low + 1, 2)
    # dia 3 e fundo; dia 7 (mesmo preco 2) tambem, porque nao tem empate na janela dele
    assert list(np.nonzero(fundo[:, 0])[0]) == [3, 7]

    plano = np.array([5, 4, 3, 3, 4, 5, 6], dtype=np.float64)[:, None]
    fundo, _ = pivos(plano, plano + 1, 2)
    # fundo duplo colado: so o primeiro dia conta
    assert list(np.nonzero(fundo[:, 0])[0]) == [2]


def test_suporte_so_vale_depois_do_terceiro_toque_conhecido() -> None:
    caminho = [*_serra([10.0, 10.1, 9.95]), *([11.0] * 5)]
    o, h, low, c = _barras(caminho)
    ret, _ = _rodar(o, h, low, c)
    terceiro_fundo = 25  # 3o fundo no pregao 25 (5 + 10 + 10)
    k = Regras().pivo
    # na vespera da confirmacao o nivel tem 2 toques: nao vale
    assert np.isnan(ret.sup_preco[terceiro_fundo + k - 1, 0])
    # no dia da confirmacao passa a valer, com 3 toques
    assert ret.sup_forca[terceiro_fundo + k, 0] == 3
    esperado = np.mean([10.0 - 0.05, 10.1 - 0.05, 9.95 - 0.05])
    assert ret.sup_preco[terceiro_fundo + k, 0] == pytest.approx(esperado, abs=1e-5)


def test_rompimento_vira_resistencia_com_historico() -> None:
    caminho = [*_serra([10.0, 10.0, 10.0]), 10.5, 10.2, 9.5, 9.3, 9.2]
    o, h, low, c = _barras(caminho)
    ret, eventos = _rodar(o, h, low, c)
    dia = caminho.index(9.5)
    assert ret.rompeu_sup[dia, 0]
    assert not ret.rompeu_sup[dia - 1, 0]
    # no dia seguinte o mesmo preco e resistencia valendo pelos 3 toques antigos
    assert ret.res_forca[dia + 1, 0] == 3
    assert ret.res_preco[dia + 1, 0] == pytest.approx(9.95, abs=1e-5)
    seg = eventos.segmentos  # type: ignore[attr-defined]
    rompidos = seg[seg["motivo"] == ROMPEU]
    assert len(rompidos) == 1
    filho = seg[seg["origem"] == rompidos["seg"].iloc[0]]
    assert filho["lado"].iloc[0] == -1


def test_nivel_fraco_rompido_some_em_vez_de_virar() -> None:
    # so dois fundos em 10: rompe, e nao nasce resistencia nenhuma em 10
    caminho = [*_serra([10.0, 10.0]), 10.5, 10.2, 9.5, 9.3, 9.2, 9.6, 9.8, 9.7]
    o, h, low, c = _barras(caminho)
    ret, eventos = _rodar(o, h, low, c)
    dia = caminho.index(9.5)
    assert not ret.rompeu_sup[dia, 0]
    seg = eventos.segmentos  # type: ignore[attr-defined]
    assert (seg["origem"] >= 0).sum() == 0
    assert np.isnan(ret.res_preco[dia + 1 :, 0]).all() or (ret.res_preco[dia + 1 :, 0] > 11).all()


def test_nivel_troca_de_papel_uma_vez_so() -> None:
    # suporte em 10 com 3 toques, rompe (vira resistencia), e depois rompe para cima
    caminho = [*_serra([10.0, 10.0, 10.0]), 10.5, 10.2, 9.5, 9.3, 9.6, 10.6, 11.0, 11.5, 11.8]
    o, h, low, c = _barras(caminho)
    ret, eventos = _rodar(o, h, low, c)
    volta = caminho.index(10.6)
    assert ret.rompeu_res[volta, 0]  # a resistencia (ex-suporte) valia e rompeu
    seg = eventos.segmentos  # type: ignore[attr-defined]
    nivel = seg[seg["origem"] >= 0]["nivel"].iloc[0]
    assert (seg["nivel"] == nivel).sum() == 2  # suporte -> resistencia, e acabou
    # depois do segundo rompimento, 10 nao e mais suporte
    assert not (np.abs(ret.sup_preco[volta + 1 :, 0] - 9.95) < 0.01).any()


def test_reteste_da_resistencia_rompida_toca_como_suporte() -> None:
    # tres topos em 12, rompe para cima, volta testar 12 por cima
    caminho = [10.0]
    for _ in range(3):
        caminho += list(np.linspace(10, 12, 6)[1:]) + list(np.linspace(12, 10, 6)[1:])
    caminho += [11.0, 12.0, 12.6, 13.0, 12.6, 12.25, 12.6, 13.0]
    o, h, low, c = _barras(caminho)
    ret, _ = _rodar(o, h, low, c)
    rompe = caminho.index(12.6)
    assert ret.rompeu_res[rompe, 0]
    reteste = len(caminho) - 3  # fecha 12,25 com minima 12,20: dentro da tolerancia
    assert ret.toca_forca[0, reteste, 0] >= 3
    assert ret.toca_virou[0, reteste, 0]
    assert not ret.toca_furou[0, reteste, 0]


def test_furou_e_voltou_conta_toque_sem_mexer_no_preco() -> None:
    caminho = [*_serra([10.0, 10.0, 10.0]), 11.0, 10.6]
    o, h, low, c = _barras(caminho)
    # dia do furo: minima 9,55 (0,4 abaixo da tolerancia), fecha 10,2
    o = np.vstack([o, [[10.6]], [[10.3]], [[10.8]], [[11.2]], [[11.5]]])
    c = np.vstack([c, [[10.2]], [[10.8]], [[11.2]], [[11.5]], [[11.8]]])
    h = np.fmax(o, c) + 0.05
    low = np.fmin(o, c) - 0.05
    dia_furo = len(caminho)
    low[dia_furo, 0] = 9.55
    ret, eventos = _rodar(o, h, low, c)
    assert ret.toca_furou[0, dia_furo, 0]
    toques = eventos.toques  # type: ignore[attr-defined]
    furo = toques[toques["dia"] == dia_furo]
    assert bool(furo["furo"].iloc[0])
    assert furo["preco_nivel"].iloc[0] == pytest.approx(9.95, abs=1e-5)


def test_lateralizacao_entre_suporte_e_resistencia() -> None:
    caminho = [*_serra([10.0] * 5, topo=11.5), 10.8, 10.8, 10.8]
    o, h, low, c = _barras(caminho)
    ret, _ = _rodar(o, h, low, c)
    fim = len(caminho) - 1
    assert ret.caixa_altura[fim, 0] == pytest.approx((11.55 - 9.95) / 9.95, abs=1e-3)
    estreita = dataclasses.replace(Regras(), caixa_max_pct=0.10)
    ret2, _ = _rodar(o, h, low, c, estreita)
    assert np.isnan(ret2.caixa_altura[fim, 0])


def test_niveis_colados_se_fundem() -> None:
    caminho = _serra([10.0, 10.3, 10.3])
    _, h, low, c = _barras(caminho)
    # ATR 0,4 (tolerancia 0,2): 9,95 e 10,25 nascem separados. Depois a
    # volatilidade dobra (tolerancia 0,4) e o toque seguinte em 10,25 os junta.
    atr = np.full_like(c, 0.4)
    atr[20:] = 0.8
    _, eventos = detectar(h, low, c, atr)
    seg = eventos.segmentos
    assert (seg["motivo"] == FUNDIDO).sum() == 1
    abertos = seg[seg["motivo"].isna()]
    assert (abertos["lado"] == 1).sum() == 1  # sobrou um suporte so (o outro e o topo, em 12)


def _passeio(dias: int, papeis: int, semente: int) -> tuple[F64, F64, F64, F64]:
    rng = np.random.default_rng(semente)
    ret = rng.normal(0, 0.02, size=(dias, papeis))
    c = 20 * np.exp(np.cumsum(ret, axis=0))
    o = c * np.exp(rng.normal(0, 0.005, size=c.shape))
    h = np.fmax(o, c) * (1 + np.abs(rng.normal(0, 0.01, size=c.shape)))
    low = np.fmin(o, c) * (1 - np.abs(rng.normal(0, 0.01, size=c.shape)))
    buraco = rng.random(c.shape) < 0.03
    for m in (o, h, low, c):
        m[buraco] = np.nan
    return o, h, low, c


def _campos(ret: Retrato, dia: int) -> dict[str, F64]:
    out = {}
    for f in dataclasses.fields(ret):
        v = getattr(ret, f.name)
        out[f.name] = v[:, dia] if v.ndim == 3 else v[dia]
    return out


def test_nada_olha_o_futuro() -> None:
    """O retrato do dia D e o mesmo com ou sem os pregoes depois de D."""
    _, h, low, c = _passeio(400, 6, semente=7)
    atr = np.full_like(c, 0.5)
    atr[np.isnan(c)] = np.nan
    cheio, _ = detectar(h, low, c, atr)
    for corte in (120, 251, 399):
        parcial, _ = detectar(h[: corte + 1], low[: corte + 1], c[: corte + 1], atr[: corte + 1])
        a, b = _campos(cheio, corte), _campos(parcial, corte)
        for nome in a:
            np.testing.assert_array_equal(a[nome], b[nome], err_msg=f"{nome} no dia {corte}")


def test_cada_papel_independe_dos_outros() -> None:
    """Rodar os papeis juntos da o mesmo que rodar cada um sozinho."""
    _, h, low, c = _passeio(300, 4, semente=11)
    atr = np.full_like(c, 0.5)
    atr[np.isnan(c)] = np.nan
    junto, _ = detectar(h, low, c, atr)
    for p in range(4):
        so, _ = detectar(h[:, [p]], low[:, [p]], c[:, [p]], atr[:, [p]])
        np.testing.assert_array_equal(junto.sup_preco[:, p], so.sup_preco[:, 0])
        np.testing.assert_array_equal(junto.toca_forca[:, :, p], so.toca_forca[:, :, 0])
        np.testing.assert_array_equal(junto.caixa_altura[:, p], so.caixa_altura[:, 0])


def test_dia_sem_negocio_nao_quebra_e_fica_vazio() -> None:
    _, h, low, c = _passeio(200, 2, semente=3)
    c[50:60, 0] = np.nan
    atr = np.full_like(c, 0.5)
    atr[np.isnan(c)] = np.nan
    ret, _ = detectar(h, low, c, atr)
    assert np.isnan(ret.sup_preco[50:60, 0]).all()
    assert not ret.rompeu_sup[50:60, 0].any()
