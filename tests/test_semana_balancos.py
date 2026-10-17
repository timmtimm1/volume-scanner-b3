"""Balancos: confirmados (Nasdaq, simulada) e provaveis (CVM, banco de teste)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pandas as pd
import pytest
from sqlalchemy import Engine, delete, update
from sqlalchemy.dialects.postgresql import insert

from scanner.semana.adrs import ADRS
from scanner.semana.balancos import confirmados, montar_balancos, provaveis
from scanner.storage import repository
from scanner.storage.models import CvmDocumento, Empresa, EmpresaTicker

FIXTURES = Path(__file__).parent / "fixtures" / "semana"
INICIO, FIM = date(2026, 10, 19), date(2026, 10, 23)

EMPRESAS = pd.DataFrame(
    {
        "cd_cvm": [906, 23264, 24112],
        "empresa": ["BANCO BRADESCO S.A.", "AMBEV S.A.", "AZUL S.A."],
        "tickers": [["BBDC3", "BBDC4"], ["ABEV3"], ["AZUL4"]],
    }
)


def _nasdaq(**especiais: int) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        adr = req.url.path.split("/")[-2]
        if adr in especiais:
            return httpx.Response(especiais[adr])
        arquivo = {
            "BBD": "nasdaq_bbd_confirmado.json",
            "AZUL": "nasdaq_azul_sem_data.json",
        }.get(adr, "nasdaq_abev_estimado.json")
        return httpx.Response(200, content=(FIXTURES / arquivo).read_bytes())

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_so_o_confirmado_entra_estimado_e_sem_data_ficam_de_fora() -> None:
    achados, avisos, anunciadas = confirmados(INICIO, FIM, EMPRESAS, cliente=_nasdaq(), pausa=0)

    assert avisos == []
    assert anunciadas == {906}
    assert achados == [
        {
            "empresa": "BANCO BRADESCO S.A.",
            "cd_cvm": 906,
            "tickers": ["BBDC3", "BBDC4"],
            "data": "2026-10-22",
            "horario": "após o fechamento",
            "trimestre": "3T26",
            "fonte": "Nasdaq",
        }
    ]


def test_confirmado_fora_da_semana_nao_entra_mas_conta_como_anunciado() -> None:
    achados, _, anunciadas = confirmados(
        date(2026, 10, 26), date(2026, 10, 30), EMPRESAS, cliente=_nasdaq(), pausa=0
    )

    assert achados == []
    # Bradesco anunciou 22/10: na semana de 26/10 ele nao e confirmado, e tambem
    # nao pode virar "provavel".
    assert anunciadas == {906}


def test_empresa_sem_papel_no_universo_nao_entra() -> None:
    achados, _, _ = confirmados(INICIO, FIM, EMPRESAS.iloc[1:], cliente=_nasdaq(), pausa=0)

    assert achados == []


def test_adr_que_falha_vira_aviso_e_os_outros_seguem() -> None:
    achados, avisos, _ = confirmados(
        INICIO, FIM, EMPRESAS, cliente=_nasdaq(SBS=500, PBR=429), pausa=0
    )

    assert [b["empresa"] for b in achados] == ["BANCO BRADESCO S.A."]
    assert avisos == [
        "Nasdaq sem resposta para PBR (Petrobras): HTTP 429",
        "Nasdaq sem resposta para SBS (Sabesp): HTTP 500",
    ]


def test_tabela_de_adrs_sem_repeticao() -> None:
    assert len({a.cd_cvm for a in ADRS.values()}) == len(ADRS) == 19
    assert len({a.cnpj for a in ADRS.values()}) == len(ADRS)
    assert ADRS["EMBJ"].empresa == "Embraer"  # EMBR e a EMBRAST, nao a Embraer


# --- provaveis, no banco -------------------------------------------------

# cd_cvm altos para nao colidir com empresas reais no banco de teste.
ENTREGOU_ANO_PASSADO, JA_ENTREGOU, FORA_DA_JANELA, FORA_DO_UNIVERSO, CONFIRMADA = (
    990101,
    990102,
    990103,
    990104,
    990105,
)
TODAS = [ENTREGOU_ANO_PASSADO, JA_ENTREGOU, FORA_DA_JANELA, FORA_DO_UNIVERSO, CONFIRMADA]
TICKERS = {
    ENTREGOU_ANO_PASSADO: ["ZZAA3", "ZZAA4"],
    JA_ENTREGOU: ["ZZBB3"],
    FORA_DA_JANELA: ["ZZCC3"],
    FORA_DO_UNIVERSO: ["ZZDD3"],
    CONFIRMADA: ["ZZEE3"],
}
UNIVERSO = ["ZZAA3", "ZZAA4", "ZZBB3", "ZZCC3", "ZZEE3"]  # ZZDD3 fica de fora


def _doc(cd: int, tipo: str, dt_refer: date, recebido: date) -> dict[str, object]:
    return {
        "cd_cvm": cd,
        "tipo": tipo,
        "dt_refer": dt_refer,
        "versao": 1,
        "recebido_original": recebido,
        "recebido_ultima": recebido,
        "escopo": "con",
        "layout": "geral",
    }


@pytest.fixture
def banco(engine: Engine) -> Iterator[Engine]:
    with engine.begin() as conn:
        conn.execute(delete(Empresa).where(Empresa.cd_cvm.in_(TODAS)))
        for cd in TODAS:
            conn.execute(
                insert(Empresa).values(
                    cd_cvm=cd, cnpj=f"{cd:014d}", nome=f"EMPRESA {cd} S.A.", nome_comercial=None
                )
            )
        conn.execute(
            update(Empresa)
            .where(Empresa.cd_cvm == ENTREGOU_ANO_PASSADO)
            .values(nome_comercial="ZEZE")
        )
        for cd, papeis in TICKERS.items():
            for t in papeis:
                conn.execute(
                    insert(EmpresaTicker).values(
                        ticker=t,
                        cd_cvm=cd,
                        fonte="fca",
                        verificado_em=datetime(2026, 10, 1, tzinfo=UTC),
                    )
                )
        docs = [
            # Entregou o 3T25 em 22/10/2025 (dentro de 20 a 24/10/2025) e nada ainda em 2026.
            _doc(ENTREGOU_ANO_PASSADO, "ITR", date(2025, 9, 30), date(2025, 10, 22)),
            # Entregou o 3T25 na janela E ja entregou o 3T26 (em 14/10/2026): nao e mais provavel.
            _doc(JA_ENTREGOU, "ITR", date(2025, 9, 30), date(2025, 10, 21)),
            _doc(JA_ENTREGOU, "ITR", date(2026, 9, 30), date(2026, 10, 14)),
            # Entregou fora da janela (13/11/2025).
            _doc(FORA_DA_JANELA, "ITR", date(2025, 9, 30), date(2025, 11, 13)),
            # Fora do universo.
            _doc(FORA_DO_UNIVERSO, "ITR", date(2025, 9, 30), date(2025, 10, 23)),
            # Entregou a DFP na janela de outro tipo de documento: rotulo "DFP 2024".
            _doc(CONFIRMADA, "DFP", date(2024, 12, 31), date(2025, 10, 24)),
        ]
        for d in docs:
            conn.execute(insert(CvmDocumento).values(**d))
    yield engine
    with engine.begin() as conn:
        conn.execute(delete(Empresa).where(Empresa.cd_cvm.in_(TODAS)))


@pytest.mark.db
def test_provaveis_so_quem_entregou_na_janela_e_ainda_nao_entregou(banco: Engine) -> None:
    achados = provaveis(banco, UNIVERSO, INICIO, FIM, date(2026, 10, 16), set())

    assert [(b["empresa"], b["tickers"], b["documento"], b["entregue_em"]) for b in achados] == [
        ("ZEZE", ["ZZAA3", "ZZAA4"], "ITR 3T25", "2025-10-22"),
        (f"EMPRESA {CONFIRMADA} S.A.", ["ZZEE3"], "DFP 2024", "2025-10-24"),
    ]
    assert [b["cd_cvm"] for b in achados] == [ENTREGOU_ANO_PASSADO, CONFIRMADA]


@pytest.mark.db
def test_provaveis_exclui_quem_anunciou_data(banco: Engine) -> None:
    achados = provaveis(banco, UNIVERSO, INICIO, FIM, date(2026, 10, 16), {ENTREGOU_ANO_PASSADO})

    assert [b["cd_cvm"] for b in achados] == [CONFIRMADA]


@pytest.mark.db
def test_provaveis_janela_e_de_364_dias_mesmos_dias_da_semana(banco: Engine) -> None:
    sexta = date(2026, 10, 16)

    # 23 a 27/10/2026 -> 24 a 28/10/2025: so a entrega de 24/10/2025 cai dentro (limite inclusivo).
    com_limite = provaveis(banco, UNIVERSO, date(2026, 10, 23), date(2026, 10, 27), sexta, set())
    # 26 a 30/10/2026 -> 27 a 31/10/2025: nenhuma.
    depois = provaveis(banco, UNIVERSO, date(2026, 10, 26), date(2026, 10, 30), sexta, set())

    assert [b["cd_cvm"] for b in com_limite] == [CONFIRMADA]
    assert depois == []


@pytest.mark.db
def test_papeis_por_empresa_agrupa_e_usa_o_nome_do_site(banco: Engine) -> None:
    frame = repository.papeis_por_empresa(banco, UNIVERSO)

    por = frame.set_index("cd_cvm")
    assert por["tickers"].map(list).to_dict()[ENTREGOU_ANO_PASSADO] == ["ZZAA3", "ZZAA4"]
    assert por.loc[ENTREGOU_ANO_PASSADO, "empresa"] == "ZEZE"
    assert por.loc[JA_ENTREGOU, "empresa"] == f"EMPRESA {JA_ENTREGOU} S.A."
    assert FORA_DO_UNIVERSO not in por.index


@pytest.mark.db
def test_universo_vazio_nao_consulta_nada(banco: Engine) -> None:
    assert provaveis(banco, [], INICIO, FIM, date(2026, 10, 16), set()) == []
    assert repository.papeis_por_empresa(banco, []).empty


@pytest.mark.db
def test_montar_balancos_junta_as_duas_listas(banco: Engine) -> None:
    resultado = montar_balancos(
        banco, UNIVERSO, INICIO, FIM, date(2026, 10, 16), cliente=_nasdaq(), pausa=0
    )

    assert set(resultado) == {"confirmados", "provaveis", "avisos"}
