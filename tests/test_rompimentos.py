"""Alertas de rompimento de preco."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine

from scanner.cotacoes.base import Cotacao, ticker_valido
from scanner.notify.telegram import ConsoleNotifier, format_rompimento
from scanner.rompimentos import (
    Alerta,
    checar_rompimentos,
    payload_do_disparo,
    rompeu,
    selecionar_disparos,
)
from scanner.storage.repository import (
    alertas_ativos,
    apagar_alerta,
    criar_alerta,
    listar_alertas,
    marcar_disparado,
    reativar_alerta,
)

DIA = date(2026, 9, 4)


def alerta(preco: str, direcao: str = "acima", ticker: str = "PETR4") -> Alerta:
    return Alerta(
        id=1,
        ticker=ticker,
        trade_date=DIA,
        preco=Decimal(preco),
        direcao="acima" if direcao == "acima" else "abaixo",
        criado_em=datetime(2026, 9, 9, 10, 0, tzinfo=UTC),
    )


def cotacao(preco: str, ticker: str = "PETR4", fonte: str = "brapi") -> Cotacao:
    return Cotacao(ticker, Decimal(preco), fonte)


# --- A regra ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("direcao", "nivel", "preco", "esperado"),
    [
        ("acima", "38.50", "39.00", True),
        ("acima", "38.50", "38.00", False),
        ("abaixo", "38.50", "38.00", True),
        ("abaixo", "38.50", "39.00", False),
    ],
)
def test_rompeu_olha_so_para_o_lado_pedido(
    direcao: str, nivel: str, preco: str, esperado: bool
) -> None:
    assert rompeu(alerta(nivel, direcao), cotacao(preco)) is esperado


@pytest.mark.parametrize("direcao", ["acima", "abaixo"])
def test_tocar_o_nivel_exatamente_conta(direcao: str) -> None:
    # A escolha do usuario foi "tocou", nao "ultrapassou": o preco exato dispara.
    assert rompeu(alerta("38.50", direcao), cotacao("38.50")) is True


def test_papel_sem_cotacao_nao_dispara_nem_some() -> None:
    # Fornecedor fora do ar nao pode virar disparo nem cancelar o alerta:
    # ausencia de dado e "nao sei", nunca "nao rompeu" e nunca "rompeu".
    a = alerta("1.00")  # nivel baixissimo: dispararia com qualquer cotacao
    assert selecionar_disparos([a], {}) == []


def test_alerta_ja_disparado_nao_dispara_de_novo() -> None:
    disparado = Alerta(
        id=1,
        ticker="PETR4",
        trade_date=DIA,
        preco=Decimal("10.00"),
        direcao="acima",
        criado_em=datetime(2026, 9, 9, tzinfo=UTC),
        disparado_em=datetime(2026, 9, 9, 11, tzinfo=UTC),
    )
    assert selecionar_disparos([disparado], {"PETR4": cotacao("50.00")}) == []


# --- Mensagem -----------------------------------------------------------------


def test_mensagem_mostra_o_preco_que_disparou_e_nao_so_o_nivel() -> None:
    """O ponto do desenho: com pavio, o nivel sozinho nao diz se foi ruido."""
    disparos = selecionar_disparos([alerta("11.00")], {"PETR4": cotacao("11.25")})
    texto = format_rompimento(payload_do_disparo(disparos[0]))

    assert "11,00" in texto, "o nivel pedido"
    assert "11,25" in texto, "o preco que realmente disparou"
    assert "brapi" in texto, "de onde veio a cotacao"


def test_mensagem_diz_a_direcao_em_palavras() -> None:
    subiu = format_rompimento(
        payload_do_disparo(
            selecionar_disparos([alerta("11.00", "acima")], {"PETR4": cotacao("12.00")})[0]
        )
    )
    caiu = format_rompimento(
        payload_do_disparo(
            selecionar_disparos([alerta("11.00", "abaixo")], {"PETR4": cotacao("10.00")})[0]
        )
    )
    assert "subiu" in subiu and "caiu" not in subiu
    assert "caiu" in caiu and "subiu" not in caiu


# --- Guarda de ticker ---------------------------------------------------------


@pytest.mark.parametrize("bom", ["PETR4", "BPAC11", "VALE3", "TAEE11B"])
def test_ticker_valido_aceita_papel_da_b3(bom: str) -> None:
    assert ticker_valido(bom)


@pytest.mark.parametrize(
    "ruim",
    ["../../etc/passwd", "PETR4;rm -rf", "PETR4/../ITUB4", "", "petr4", "TOOLONGNAME1"],
)
def test_ticker_invalido_nao_chega_na_url(ruim: str) -> None:
    # Tickers vao no CAMINHO da URL dos fornecedores: um valor inesperado aqui
    # mudaria a rota chamada. Vale mais do que formatacao.
    assert not ticker_valido(ruim)


# --- Banco --------------------------------------------------------------------


@pytest.mark.db
def test_ciclo_de_vida_do_alerta(engine: Engine) -> None:
    novo = criar_alerta(engine, "PETR4", DIA, Decimal("38.50"), "acima")
    try:
        assert any(a.id == novo for a in alertas_ativos(engine))

        assert marcar_disparado(engine, novo, preco=Decimal("38.60"), fonte="brapi") is True
        assert all(a.id != novo for a in alertas_ativos(engine)), "sai dos ativos"

        gravado = next(a for a in listar_alertas(engine, "PETR4") if a.id == novo)
        assert gravado.preco_disparo == Decimal("38.60")
        assert gravado.fonte_disparo == "brapi"

        assert reativar_alerta(engine, novo) is True
        religado = next(a for a in listar_alertas(engine, "PETR4") if a.id == novo)
        assert religado.ativo and religado.preco_disparo is None
    finally:
        apagar_alerta(engine, novo)


@pytest.mark.db
def test_disparo_concorrente_marca_uma_vez_so(engine: Engine) -> None:
    # Duas passadas sobrepostas nao podem notificar duas vezes o mesmo alerta.
    novo = criar_alerta(engine, "VALE3", DIA, Decimal("70.00"), "abaixo")
    try:
        primeira = marcar_disparado(engine, novo, preco=Decimal("69.00"), fonte="brapi")
        segunda = marcar_disparado(engine, novo, preco=Decimal("68.00"), fonte="yahoo")
        assert (primeira, segunda) == (True, False)

        gravado = next(a for a in listar_alertas(engine, "VALE3") if a.id == novo)
        assert gravado.preco_disparo == Decimal("69.00"), "vence o primeiro disparo"
    finally:
        apagar_alerta(engine, novo)


@pytest.mark.db
def test_direcao_invalida_e_recusada(engine: Engine) -> None:
    with pytest.raises(ValueError, match="direcao invalida"):
        criar_alerta(engine, "PETR4", DIA, Decimal("10.00"), "para_os_lados")


# --- Ciclo completo -----------------------------------------------------------


@dataclass(frozen=True)
class ProvedorFalso:
    """Fornecedor de mentira, para o ciclo nao depender de rede."""

    precos: dict[str, str]
    nome: str = "falso"

    def cotacoes(self, tickers: Sequence[str]) -> dict[str, Cotacao]:
        return {
            t: Cotacao(t, Decimal(self.precos[t]), self.nome) for t in tickers if t in self.precos
        }


@pytest.mark.db
def test_checagem_dispara_avisa_e_desativa(engine: Engine) -> None:
    dispara = criar_alerta(engine, "PETR4", DIA, Decimal("38.00"), "acima")
    fica = criar_alerta(engine, "PETR4", DIA, Decimal("99.00"), "acima")
    try:
        enviadas: list[str] = []
        relatorio = checar_rompimentos(
            engine,
            ProvedorFalso({"PETR4": "38.10"}),
            notifier=ConsoleNotifier(sent=enviadas),
        )

        assert relatorio.disparados == 1
        assert len(enviadas) == 1
        assert "38,10" in enviadas[0], "a mensagem traz o preco real"

        ativos = {a.id for a in alertas_ativos(engine)}
        assert dispara not in ativos, "o que rompeu foi desativado"
        assert fica in ativos, "o que nao rompeu continua vigiando"
    finally:
        apagar_alerta(engine, dispara)
        apagar_alerta(engine, fica)


@pytest.mark.db
def test_dry_run_avisa_mas_nao_desativa(engine: Engine) -> None:
    novo = criar_alerta(engine, "PETR4", DIA, Decimal("38.00"), "acima")
    try:
        enviadas: list[str] = []
        checar_rompimentos(
            engine,
            ProvedorFalso({"PETR4": "38.10"}),
            notifier=ConsoleNotifier(sent=enviadas),
            dry_run=True,
        )
        assert len(enviadas) == 1
        assert novo in {a.id for a in alertas_ativos(engine)}
    finally:
        apagar_alerta(engine, novo)


@pytest.mark.db
def test_telegram_recusando_mantem_o_alerta_ativo(engine: Engine) -> None:
    """Se a mensagem nao sai, o alerta nao pode ser dado como avisado.

    O contrario perderia o aviso em silencio -- exatamente o que este sistema
    existe para nao fazer.
    """

    @dataclass
    class NotifierQueFalha:
        base_url: str = ""

        def send_rompimento(self, payload: object) -> bool:
            return False

    novo = criar_alerta(engine, "PETR4", DIA, Decimal("38.00"), "acima")
    try:
        relatorio = checar_rompimentos(
            engine, ProvedorFalso({"PETR4": "38.10"}), notifier=NotifierQueFalha()
        )
        assert relatorio.disparados == 0
        assert novo in {a.id for a in alertas_ativos(engine)}, "continua ativo para tentar de novo"
    finally:
        apagar_alerta(engine, novo)
