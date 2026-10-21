"""Media movel como suporte em tendencia (scanner.gatilhos.medias)."""

from __future__ import annotations

import numpy as np
import pytest

from scanner.gatilhos.medias import RegrasDaMedia, media_movel, toques_na_media


def _alta_com_recuo(dias: int = 80) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Alta firme (+0,5% ao dia) e, no ultimo dia, um pavio ate a MMA 20."""
    c = 10 * 1.005 ** np.arange(dias)
    low = c * 0.995
    c = c[:, None]
    low = low[:, None]
    return c, low, np.full_like(c, 0.08)


def test_mme_converge_para_a_do_site() -> None:
    # semente diferente (primeiro fechamento x MMA dos 9 primeiros), mesma linha depois
    c = np.linspace(10, 20, 120)[:, None]
    mme = media_movel(c, "MME", 9)[:, 0]
    k = 2 / 10
    site = [c[:9, 0].mean()]
    for x in c[9:, 0]:
        site.append(x * k + site[-1] * (1 - k))
    assert mme[-1] == pytest.approx(site[-1], rel=1e-6)


def test_pavio_na_media_subindo_e_toque() -> None:
    c, low, atr = _alta_com_recuo()
    mm20 = media_movel(c, "MMA", 20)
    low[-1, 0] = mm20[-1, 0] + 0.02  # encosta na media, fecha la em cima
    _, toque = toques_na_media(low, c, atr, RegrasDaMedia(medias=(("MMA", 20),)))["mma20"]
    assert toque[0, -1, 0]
    assert not toque[0, -2, 0]  # o dia anterior ficou longe dela


def test_media_caindo_nao_e_suporte() -> None:
    c, low, atr = _alta_com_recuo()
    c = c[::-1].copy()  # a mesma serie em queda
    low = c * 0.995
    mm20 = media_movel(c, "MMA", 20)
    low[-1, 0] = mm20[-1, 0] + 0.02
    _, toque = toques_na_media(low, c, atr, RegrasDaMedia(medias=(("MMA", 20),)))["mma20"]
    assert not toque[:, -1, 0].any()


def test_fechar_abaixo_da_media_nao_e_toque() -> None:
    c, low, atr = _alta_com_recuo()
    mm20 = media_movel(c, "MMA", 20)
    c[-1, 0] = mm20[-1, 0] - 0.05
    low[-1, 0] = c[-1, 0] - 0.01
    _, toque = toques_na_media(low, c, atr, RegrasDaMedia(medias=(("MMA", 20),)))["mma20"]
    assert not toque[:, -1, 0].any()


def test_nada_olha_o_futuro() -> None:
    rng = np.random.default_rng(5)
    c = 20 * np.exp(np.cumsum(rng.normal(0.001, 0.02, size=(300, 3)), axis=0))
    low = c * (1 - np.abs(rng.normal(0, 0.01, size=c.shape)))
    atr = np.full_like(c, 0.4)
    cheio = toques_na_media(low, c, atr)
    for corte in (100, 250):
        parcial = toques_na_media(low[: corte + 1], c[: corte + 1], atr[: corte + 1])
        for nome_ in cheio:
            np.testing.assert_array_equal(cheio[nome_][1][:, corte], parcial[nome_][1][:, corte])
