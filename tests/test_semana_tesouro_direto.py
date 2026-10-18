"""Tesouro Direto: leitura do CSV e vertices por interpolacao, contra um recorte REAL.

O recorte (`tesouro_direto_recorte.csv`) e do arquivo oficial baixado em
18/10/2026, com todas as linhas de cinco datas: 13 e 14/10/2016 (LTN e NTN-F no
mesmo vencimento; o prefixado mais longo passa de 10 anos), 13/10/2017 (o mais
longo tem 9,2 anos: sem vertice de 10), e 09 e 15/10/2026.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import pytest

from scanner.semana.fontes import FonteIndisponivelError, tesouro_direto
from scanner.semana.fontes.tesouro_direto import (
    SERIES_PRE,
    SERIES_REAL,
    baixar_titulos,
    data_base_da_semana,
    interpolar,
    ler_csv,
    montar_curva,
    serie_semanal,
)

FIXTURE = Path(__file__).parent / "fixtures" / "semana" / "tesouro_direto_recorte.csv"


@pytest.fixture(scope="module")
def titulos() -> pd.DataFrame:
    return ler_csv(FIXTURE.read_bytes())


def _taxa(frame: pd.DataFrame, semana: date, serie: str) -> float | None:
    linha = frame[(frame["semana"] == semana) & (frame["serie"] == serie)]
    return None if linha.empty else float(linha["taxa"].iloc[0])


def test_so_entram_os_quatro_tipos_das_duas_curvas(titulos: pd.DataFrame) -> None:
    assert set(titulos["curva"]) == {"nominal", "real"}
    # Em 15/10/2026 o CSV tem 11 prefixados e 15 IPCA+ (alem de Selic, IGPM+,
    # Educa+ e Renda+, que nao entram); 3 e 5 repetem o vencimento de outro
    # titulo e saem, sobrando 8 e 10.
    contagem = titulos[titulos["data_base"] == "2026-10-15"].groupby("curva").size().to_dict()
    assert contagem == {"nominal": 8, "real": 10}


def test_mesmo_vencimento_vale_o_sem_cupom(titulos: pd.DataFrame) -> None:
    # 14/10/2016, vencimento 01/01/2021: LTN 11,29 e NTN-F 11,24. Fica a LTN.
    dia = titulos[(titulos["data_base"] == "2016-10-14") & (titulos["curva"] == "nominal")]
    em_2021 = dia[dia["vencimento"] == "2021-01-01"]
    assert len(em_2021) == 1
    assert em_2021["taxa"].iloc[0] == 11.29
    assert bool(em_2021["sem_cupom"].iloc[0])


def test_taxa_de_compra_e_se_vier_zero_a_de_venda() -> None:
    csv = (
        "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha\n"
        "Tesouro Prefixado;01/01/2027;28/01/2026;0,00;12,34\n"
        "Tesouro Prefixado;01/01/2028;28/01/2026;12,50;12,60\n"
        "Tesouro Prefixado;01/01/2029;28/01/2026;0,00;0,00\n"
    )
    t = ler_csv(csv)

    assert t["taxa"].tolist() == [12.34, 12.5]


def test_csv_sem_as_colunas_levanta() -> None:
    with pytest.raises(FonteIndisponivelError, match="ilegivel"):
        ler_csv("a;b\n1;2\n")


def test_csv_sem_titulos_levanta() -> None:
    cabecalho = "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha\n"
    with pytest.raises(FonteIndisponivelError, match="sem titulos"):
        ler_csv(cabecalho + "Tesouro Selic;01/03/2027;15/10/2026;0,01;0,02\n")


def test_interpola_linearmente_entre_os_vizinhos(titulos: pd.DataFrame) -> None:
    # Conta a mao: NTN-F 01/01/2025 (11,32%, 8,2163 anos) e 01/01/2027 (11,41%,
    # 10,2149 anos); 10 anos fica a (10-8,2163)/(10,2149-8,2163) do caminho.
    esperado = 11.32 + (10 - 8.216290) / (10.214921 - 8.216290) * (11.41 - 11.32)

    taxa = interpolar(titulos, "nominal", pd.Timestamp("2016-10-14"), 10)

    assert taxa == pytest.approx(esperado, abs=1e-4)
    assert taxa == pytest.approx(11.4003, abs=1e-4)


def test_pre_de_dez_anos_prolonga_a_reta_dos_dois_mais_longos(titulos: pd.DataFrame) -> None:
    # 13/10/2017: o prefixado mais longo (01/01/2027) tem 9,2183 anos. Os dois
    # mais longos: NTN-F 01/01/2025 (9,62%, 7,219713 anos) e NTN-F 01/01/2027
    # (9,79%, 9,218344 anos). Inclinacao = (9,79-9,62)/(9,218344-7,219713) =
    # 0,085060 pp por ano; faltam 10-9,218344 = 0,781656 ano: 9,79 + 0,066488.
    esperado = 9.79 + (9.79 - 9.62) / (9.218344 - 7.219713) * (10 - 9.218344)

    taxa = interpolar(titulos, "nominal", pd.Timestamp("2017-10-13"), 10)

    assert taxa == pytest.approx(esperado, abs=1e-4)
    assert taxa == pytest.approx(9.8565, abs=1e-4)
    frame = serie_semanal(titulos, date(2017, 10, 13), date(2017, 10, 13))
    assert _taxa(frame, date(2017, 10, 13), "pre_10a") == pytest.approx(esperado, abs=1e-4)


def test_nao_prolonga_alem_do_limite_nem_abaixo_do_menor_prazo() -> None:
    base = pd.Timestamp("2020-01-02")
    titulos = pd.DataFrame(
        {
            "curva": "nominal",
            "sem_cupom": True,
            "vencimento": pd.to_datetime(["2022-01-02", "2024-01-02"]),
            "data_base": base,
            "taxa": [10.0, 11.0],
        }
    )
    # Prazos: ~2,00 e ~4,00 anos. Alvo ate 4,00 + 1,2 prolonga; alem disso, NaN.
    assert interpolar(titulos, "nominal", base, 5.0) == pytest.approx(11.5, abs=0.01)
    assert pd.isna(interpolar(titulos, "nominal", base, 5.3))
    assert pd.isna(interpolar(titulos, "nominal", base, 1.0))


def test_serie_semanal_um_ponto_por_semana_e_serie(titulos: pd.DataFrame) -> None:
    frame = serie_semanal(titulos, date(2016, 10, 14), date(2016, 10, 28))

    # Semanas de 21 e 28/10/2016 nao tem dado no recorte: sem ponto.
    assert set(frame["semana"]) == {date(2016, 10, 14)}
    assert set(frame["serie"]) == {"pre_1a", "pre_2a", "pre_5a", "pre_10a", "ipca_5a", "ipca_10a"}
    assert set(frame["fonte"]) == {"tesouro_direto"}
    assert set(frame["data_base"]) == {date(2016, 10, 14)}
    assert _taxa(frame, date(2016, 10, 14), "pre_10a") == pytest.approx(11.4003, abs=1e-4)


def test_pre_de_um_ano_com_conta_a_mao(titulos: pd.DataFrame) -> None:
    # 14/10/2016: LTN 01/01/2017 (13,62%, 0,2163 anos) e 01/01/2018 (11,97%,
    # 1,2156 anos). 1 ano fica a (1-0,21629)/(1,215606-0,21629) do caminho.
    esperado = 13.62 + (1 - 0.216290) / (1.215606 - 0.216290) * (11.97 - 13.62)

    frame = serie_semanal(titulos, date(2016, 10, 14), date(2016, 10, 14))

    assert _taxa(frame, date(2016, 10, 14), "pre_1a") == pytest.approx(esperado, abs=1e-4)


def test_vertice_fora_da_faixa_nao_vira_ponto() -> None:
    # Frame sintetico: o prefixado mais longo vence em 5 anos, o Pre de 10 anos
    # esta 5 anos alem do maior prazo e nao entra; o de 5 anos entra.
    base = pd.Timestamp("2020-01-03")
    titulos = pd.DataFrame(
        {
            "curva": "nominal",
            "sem_cupom": True,
            "vencimento": pd.to_datetime(["2021-01-03", "2023-01-03", "2025-01-03"]),
            "data_base": base,
            "taxa": [9.0, 9.5, 10.0],
        }
    )

    frame = serie_semanal(titulos, date(2020, 1, 3), date(2020, 1, 3))

    assert "pre_10a" not in set(frame["serie"])
    assert "pre_5a" in set(frame["serie"])


def test_semana_pega_a_ultima_data_base_ate_a_sexta() -> None:
    datas = pd.DatetimeIndex(["2026-10-08", "2026-10-09", "2026-10-15"])

    # Sexta 16/10 sem dado no dia: vale quinta 15/10, que esta na semana.
    assert data_base_da_semana(datas, date(2026, 10, 16)) == pd.Timestamp("2026-10-15")
    assert data_base_da_semana(datas, date(2026, 10, 9)) == pd.Timestamp("2026-10-09")
    # Semana de 23/10 (segunda 19/10): o ultimo dado e de 15/10, de outra semana.
    assert data_base_da_semana(datas, date(2026, 10, 23)) is None
    # Antes do primeiro dado.
    assert data_base_da_semana(datas, date(2026, 10, 2)) is None


def test_curva_do_payload_tem_a_forma_antiga_mais_fonte(titulos: pd.DataFrame) -> None:
    historico = serie_semanal(titulos, date(2026, 10, 9), date(2026, 10, 16))

    curva = montar_curva(historico, date(2026, 10, 16), SERIES_PRE)

    assert curva["fonte"] == "tesouro_direto"
    assert curva["data"] == date(2026, 10, 15)  # a data base real, nao a sexta
    assert curva["data_anterior"] == date(2026, 10, 9)
    assert [v["du"] for v in curva["vertices"]] == [252, 504, 1260, 2520]
    assert [v["anos"] for v in curva["vertices"]] == [1.0, 2.0, 5.0, 10.0]
    um_ano = curva["vertices"][0]
    anterior = _taxa(historico, date(2026, 10, 9), "pre_1a")
    atual = _taxa(historico, date(2026, 10, 16), "pre_1a")
    assert anterior is not None and atual is not None
    assert um_ano["taxa"] == atual
    assert um_ano["taxa_anterior"] == anterior
    assert um_ano["variacao_bp"] == pytest.approx((atual - anterior) * 100)


def test_curva_real_tem_ipca_de_5_e_10_anos(titulos: pd.DataFrame) -> None:
    historico = serie_semanal(titulos, date(2026, 10, 9), date(2026, 10, 16))

    curva = montar_curva(historico, date(2026, 10, 16), SERIES_REAL)

    assert [v["anos"] for v in curva["vertices"]] == [5.0, 10.0]
    assert [v["du"] for v in curva["vertices"]] == [1260, 2520]


def test_vertice_sem_taxa_na_semana_sai_da_lista_e_sem_nenhum_levanta() -> None:
    # Frame sintetico (o prefixado mais longo vence em 5 anos): sem Pre de 10 anos.
    base = pd.Timestamp("2017-10-13")
    titulos = pd.DataFrame(
        {
            "curva": "nominal",
            "sem_cupom": True,
            "vencimento": pd.to_datetime(["2018-10-13", "2019-10-13", "2022-10-13", "2023-10-13"]),
            "data_base": base,
            "taxa": [7.0, 7.5, 9.0, 9.2],
        }
    )
    historico = serie_semanal(titulos, date(2017, 10, 13), date(2017, 10, 13))

    curva = montar_curva(historico, date(2017, 10, 13), SERIES_PRE)

    assert [v["anos"] for v in curva["vertices"]] == [1.0, 2.0, 5.0]
    assert curva["data_anterior"] is None
    assert curva["vertices"][0]["taxa_anterior"] is None
    assert curva["vertices"][0]["variacao_bp"] is None
    with pytest.raises(FonteIndisponivelError, match="semana de 2017-10-20"):
        montar_curva(historico, date(2017, 10, 20), SERIES_PRE)


def test_baixar_segue_o_redirecionamento_e_le_o_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "origem.test":
            return httpx.Response(302, headers={"Location": "https://destino.test/arquivo.csv"})
        return httpx.Response(200, content=FIXTURE.read_bytes())

    monkeypatch.setattr(tesouro_direto, "URL", "https://origem.test/x.csv")
    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as c:
        t = baixar_titulos(cliente=c)

    assert len(t) == 80


def test_baixar_com_erro_http_levanta() -> None:
    transporte = httpx.MockTransport(lambda _r: httpx.Response(503))
    with (
        httpx.Client(transport=transporte) as c,
        pytest.raises(FonteIndisponivelError, match="HTTP 503"),
    ):
        baixar_titulos(cliente=c)
