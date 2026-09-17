"""Carga dos proventos, com banco: o que entra, o que e recusado e o que espera."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, delete, select
from sqlalchemy.dialects.postgresql import insert

from scanner.fundamentos import carga as carga_mod
from scanner.fundamentos.b3 import B3IndisponivelError, Detalhe, Papel, Provento
from scanner.storage import repository
from scanner.storage.models import DailyBar, Empresa, EmpresaTicker
from scanner.storage.models import Provento as ProventoModel

pytestmark = pytest.mark.db

UNIPAR = 11592
ISIN_ON, ISIN_PNB = "BRUNIPACNOR7", "BRUNIPACNPB8"
AGORA = datetime(2026, 9, 17, tzinfo=UTC)
PREGOES = [date(2026, 3, 18), date(2025, 11, 19), date(2025, 3, 19), date(2024, 12, 18)]


class B3Falsa:
    """Substitui as tres consultas da B3, guardando o que foi perguntado."""

    def __init__(self) -> None:
        self.detalhes: list[int] = []
        self.recentes_pedidos: list[str] = []
        self.historicos_pedidos: list[str] = []
        self.recentes: list[Provento] = []
        self.historicos: list[Provento] = []
        self.fora_do_ar = False
        # Imita a Ambev: o nome de pregao ("AMBEV S/A") devolve zero, e so o
        # nome da CVM ("AMBEV S.A.") acha o historico.
        self.so_pelo_nome_cvm = False

    def detalhe(self, _cliente: object, cd_cvm: int) -> Detalhe:
        self.detalhes.append(cd_cvm)
        return Detalhe(
            cd_cvm=cd_cvm,
            emissor="UNIP",
            nome_pregao="UNIPAR",
            papeis=(Papel("UNIP3", ISIN_ON), Papel("UNIP6", ISIN_PNB), Papel("XPTO9", "BRXPTO000")),
        )

    def recente(self, _cliente: object, emissor: str) -> list[Provento]:
        self.recentes_pedidos.append(emissor)
        if self.fora_do_ar:
            raise B3IndisponivelError("B3 fora do ar (teste)")
        return self.recentes

    def historico(self, _cliente: object, nome: str) -> list[Provento]:
        self.historicos_pedidos.append(nome)
        if self.so_pelo_nome_cvm and nome != "UNIPAR CARBOCLORO":
            return []
        return self.historicos


def _recente(isin: str, valor: str, dia: date) -> Provento:
    return Provento(
        classe=None,
        isin=isin,
        tipo="DIVIDENDO",
        valor=Decimal(valor),
        data_com=dia,
        data_aprovacao=None,
        data_pagamento=dia + timedelta(days=10),
    )


def _historico(classe: str, valor: str, dia: date, preco: str) -> Provento:
    return Provento(
        classe=classe,
        isin=None,
        tipo="DIVIDENDO",
        valor=Decimal(valor),
        data_com=dia,
        data_aprovacao=None,
        data_pagamento=None,
        preco_data_com=Decimal(preco),
    )


@pytest.fixture
def b3(monkeypatch: pytest.MonkeyPatch) -> B3Falsa:
    falsa = B3Falsa()
    monkeypatch.setattr(carga_mod, "novo_cliente", lambda: _ClienteDescartavel())
    monkeypatch.setattr(carga_mod, "detalhe_da_empresa", falsa.detalhe)
    monkeypatch.setattr(carga_mod, "proventos_recentes", falsa.recente)
    monkeypatch.setattr(carga_mod, "proventos_historicos", falsa.historico)
    return falsa


class _ClienteDescartavel:
    def close(self) -> None:
        return None


@pytest.fixture
def empresa(engine: Engine) -> Iterator[None]:
    """A Unipar ligada a dois papeis, com barras reais o bastante para conferir."""
    with engine.begin() as conn:
        conn.execute(
            insert(Empresa).values(cd_cvm=UNIPAR, cnpj="33958695000178", nome="UNIPAR CARBOCLORO")
        )
        conn.execute(
            insert(EmpresaTicker).values(
                [
                    {"ticker": t, "cd_cvm": UNIPAR, "fonte": "fca", "verificado_em": AGORA}
                    for t in ("UNIP3", "UNIP6")
                ]
            )
        )
        conn.execute(
            insert(DailyBar).values(
                [
                    {
                        "ticker": ticker,
                        "trade_date": dia,
                        "close": Decimal("50.0000"),
                        "volume_financial": Decimal("1000000.00"),
                    }
                    for ticker in ("UNIP3", "UNIP6")
                    for dia in PREGOES
                ]
            )
        )
    yield
    with engine.begin() as conn:
        conn.execute(delete(DailyBar).where(DailyBar.ticker.in_(["UNIP3", "UNIP6"])))
        conn.execute(delete(EmpresaTicker).where(EmpresaTicker.cd_cvm == UNIPAR))
        conn.execute(delete(Empresa).where(Empresa.cd_cvm == UNIPAR))


def _detalhar(engine: Engine, quando: datetime = AGORA) -> carga_mod.RelatorioFundamentos:
    relatorio = carga_mod.RelatorioFundamentos()
    carga_mod._detalhar_empresas(engine, quando, quando, pausa=0, relatorio=relatorio)
    return relatorio


def _carregar_recentes(engine: Engine, quando: datetime = AGORA) -> carga_mod.RelatorioFundamentos:
    relatorio = carga_mod.RelatorioFundamentos()
    carga_mod._proventos_recentes(engine, quando, quando, pausa=0, relatorio=relatorio)
    return relatorio


def _carregar_historico(engine: Engine, quando: datetime = AGORA) -> carga_mod.RelatorioFundamentos:
    relatorio = carga_mod.RelatorioFundamentos()
    carga_mod._proventos_historicos(engine, quando, quando, pausa=0, relatorio=relatorio)
    return relatorio


def _proventos(engine: Engine) -> list[tuple[str, date, Decimal, str]]:
    stmt = select(
        ProventoModel.ticker, ProventoModel.data_com, ProventoModel.valor, ProventoModel.fonte
    ).order_by(ProventoModel.ticker, ProventoModel.data_com)
    with engine.connect() as conn:
        return [(t, d, v, f) for t, d, v, f in conn.execute(stmt)]


def test_detalhe_guarda_isin_so_dos_nossos_papeis(
    engine: Engine, b3: B3Falsa, empresa: None
) -> None:
    _detalhar(engine)

    papeis = repository.papeis_da_empresa(engine, UNIPAR)
    assert {p["ticker"]: p["classe"] for p in papeis} == {"UNIP3": "ON", "UNIP6": "PNB"}
    # XPTO9 e da B3, mas nao esta ligado a esta empresa no nosso banco.
    assert "XPTO9" not in {p["ticker"] for p in papeis}

    with engine.connect() as conn:
        linha = conn.execute(
            select(Empresa.emissor_b3, Empresa.nome_pregao).where(Empresa.cd_cvm == UNIPAR)
        ).one()
    assert (linha.emissor_b3, linha.nome_pregao) == ("UNIP", "UNIPAR")


def test_recentes_entram_pelo_isin_e_por_papel(engine: Engine, b3: B3Falsa, empresa: None) -> None:
    _detalhar(engine)
    b3.recentes = [
        _recente(ISIN_ON, "5.48220258487", date(2026, 3, 18)),
        _recente(ISIN_PNB, "6.03042284335", date(2026, 3, 18)),
    ]

    _carregar_recentes(engine)

    assert [(t, v) for t, _, v, _ in _proventos(engine)] == [
        ("UNIP3", Decimal("5.48220258487")),
        ("UNIP6", Decimal("6.03042284335")),
    ]


def test_isin_de_fora_nao_grava_nada(engine: Engine, b3: B3Falsa, empresa: None) -> None:
    """A consulta dos recentes so aceita o codigo de emissor, que e chave fraca."""
    _detalhar(engine)
    b3.recentes = [_recente("BREMBRACNOR1", "1.00", date(2026, 3, 18))]

    _carregar_recentes(engine)

    assert _proventos(engine) == []


def test_rodar_de_novo_troca_a_janela_em_vez_de_duplicar(
    engine: Engine, b3: B3Falsa, empresa: None
) -> None:
    _detalhar(engine)
    b3.recentes = [_recente(ISIN_ON, "1.00", date(2026, 3, 18))]
    _carregar_recentes(engine)

    # A B3 corrige o valor do mesmo provento, e o dia seguinte reconsulta.
    b3.recentes = [_recente(ISIN_ON, "1.25", date(2026, 3, 18))]
    _carregar_recentes(engine, AGORA + timedelta(days=1))

    assert [(t, v) for t, _, v, _ in _proventos(engine)] == [("UNIP3", Decimal("1.25"))]


def test_parcelas_iguais_nao_sao_deduplicadas(engine: Engine, b3: B3Falsa, empresa: None) -> None:
    """Provento pago em parcelas aparece uma vez por parcela, com tudo igual."""
    _detalhar(engine)
    b3.recentes = [
        _recente(ISIN_ON, "0.02412675971", date(2026, 3, 18)),
        _recente(ISIN_ON, "0.02412675971", date(2026, 3, 18)),
        _recente(ISIN_ON, "0.02412675971", date(2026, 3, 18)),
    ]

    _carregar_recentes(engine)

    assert len(_proventos(engine)) == 3


def test_historico_aprovado_entra_so_antes_da_fronteira(
    engine: Engine, b3: B3Falsa, empresa: None
) -> None:
    _detalhar(engine)
    b3.recentes = [_recente(ISIN_ON, "1.00", date(2026, 3, 18))]
    _carregar_recentes(engine)

    b3.historicos = [
        _historico("ON", "1.00", date(2026, 3, 18), "50.00"),
        _historico("ON", "0.80", date(2025, 11, 19), "50.00"),
        _historico("ON", "0.70", date(2025, 3, 19), "50.00"),
        _historico("ON", "0.60", date(2024, 12, 18), "50.00"),
    ]
    _carregar_historico(engine)

    guardados = _proventos(engine)
    # A data de 18/03/2026 ja veio pelo ISIN: nao entra de novo pelo historico.
    assert [(d, f) for _, d, _, f in guardados] == [
        (date(2024, 12, 18), "historico"),
        (date(2025, 3, 19), "historico"),
        (date(2025, 11, 19), "historico"),
        (date(2026, 3, 18), "recente"),
    ]


def test_nome_de_pregao_vazio_tenta_o_nome_da_cvm(
    engine: Engine, b3: B3Falsa, empresa: None
) -> None:
    """A B3 nao acha o nome que ela mesma publica quando ele tem barra."""
    _detalhar(engine)
    b3.so_pelo_nome_cvm = True
    b3.historicos = [_historico("ON", "1.00", dia, "50.00") for dia in PREGOES]

    _carregar_historico(engine)

    assert b3.historicos_pedidos == ["UNIPAR", "UNIPAR CARBOCLORO"]
    assert len(_proventos(engine)) == len(PREGOES)


def test_historico_com_preco_de_outra_empresa_e_recusado(
    engine: Engine, b3: B3Falsa, empresa: None
) -> None:
    _detalhar(engine)
    b3.historicos = [_historico("ON", "1.00", dia, "12.30") for dia in PREGOES]

    relatorio = _carregar_historico(engine)

    assert _proventos(engine) == []
    assert any("reprovado" in linha for linha in relatorio.proventos)


def test_historico_sem_barra_para_comparar_e_recusado(
    engine: Engine, b3: B3Falsa, empresa: None
) -> None:
    """Sem prova nao entra: datas fora da janela de barras nao dao para conferir."""
    _detalhar(engine)
    b3.historicos = [_historico("ON", "1.00", date(2019, 5, 2), "30.00")]

    _carregar_historico(engine)

    assert _proventos(engine) == []


def test_consulta_nao_se_repete_dentro_da_validade(
    engine: Engine, b3: B3Falsa, empresa: None
) -> None:
    _detalhar(engine)
    b3.recentes = [_recente(ISIN_ON, "1.00", date(2026, 3, 18))]
    _carregar_recentes(engine)
    assert b3.recentes_pedidos == ["UNIP"]

    # Corte no passado: a empresa ja foi consultada depois dele.
    relatorio = carga_mod.RelatorioFundamentos()
    carga_mod._proventos_recentes(
        engine, AGORA, AGORA - timedelta(hours=20), pausa=0, relatorio=relatorio
    )

    assert b3.recentes_pedidos == ["UNIP"], "a mesma pergunta nao pode ser refeita no mesmo dia"


def test_b3_fora_do_ar_nao_apaga_o_que_ja_existe(
    engine: Engine, b3: B3Falsa, empresa: None
) -> None:
    _detalhar(engine)
    b3.recentes = [_recente(ISIN_ON, "1.00", date(2026, 3, 18))]
    _carregar_recentes(engine)
    antes = _proventos(engine)

    b3.fora_do_ar = True
    relatorio = carga_mod.RelatorioFundamentos()
    carga_mod._proventos_recentes(
        engine, AGORA + timedelta(days=1), AGORA + timedelta(days=1), pausa=0, relatorio=relatorio
    )

    assert _proventos(engine) == antes
    assert any("fora do ar" in aviso for aviso in relatorio.avisos)
