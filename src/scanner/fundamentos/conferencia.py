"""Conferencia dos fundamentos: o banco esta em dia com o que a CVM publicou?

Existe porque a carga falha em silencio de um jeito especifico: ela pergunta
"mudou?", ouve "nao" e segue -- e quem respondeu pode ter sido um cache. Em
15/11/2026 isso deixou o site sem os balancos do 3T26 na semana em que eles
sairam, e ninguem foi avisado: o log dizia "sem mudanca", que e a linha de um
dia normal.

A conferencia nao confia na carga. Faz duas perguntas por conta propria:

1. **Arquivo**: a data em que a CVM publicou cada zip (um HEAD direto na
   origem, sem cache e sem condicao) e mais nova do que a do arquivo que o
   banco processou? Se for, e a publicacao ja tem mais de algumas horas, a
   carga ficou para tras.
2. **Cobertura**: passado o prazo legal de entrega de um trimestre, quantas
   empresas que entregaram o trimestre anterior ja tem o novo no banco? Isso
   pega o que a pergunta 1 nao ve: arquivo "em dia" mas lido pela metade, ou
   uma mudanca de layout que fez o parser descartar os documentos novos.

Nada aqui grava: e so leitura, e pode rodar a qualquer hora. Quem decide o que
fazer com o resultado e o chamador (o CLI sai com 1, o workflow avisa no
Telegram).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Engine

from scanner.config import FundamentosConfig
from scanner.fundamentos.carga import url_do_zip
from scanner.fundamentos.cvm import CvmIndisponivelError, data_na_cvm
from scanner.storage import repository

# A conferencia roda logo depois da carga: qualquer zip mais novo na CVM do que
# no banco ja e atraso. A folga so cobre a corrida entre os dois passos -- a CVM
# republicar um arquivo nos minutos entre a carga ler e a conferencia perguntar
# (ela regrava os dez zips ao longo de quase uma hora, aos domingos de manha).
TOLERANCIA = timedelta(hours=1)

# Prazo legal de entrega, em dias depois do fim do trimestre (Resolucao CVM 80):
# 45 para o ITR; 90 para a DFP do exercicio (que e o "quarto trimestre").
PRAZO_ITR = 45
PRAZO_DFP = 90
# Depois do prazo ainda faltam a publicacao semanal da CVM (ate 7 dias) e a
# carga do dia seguinte.
FOLGA_DE_PUBLICACAO = 9
# Fracao minima das empresas que entregaram o trimestre anterior e ja tem o
# novo. Nao e 100%: toda temporada tem atrasados, empresas em recuperacao
# judicial e exercicio social que nao fecha em dezembro. Na base de 16/11/2026,
# dois dias depois do prazo do 3T26, a CVM tinha 593 de 674 (88%).
COBERTURA_MINIMA = 0.80


@dataclass(frozen=True)
class ArquivoConferido:
    """Um zip anual: quando a CVM o publicou e qual versao o banco processou."""

    tipo: str
    ano: int
    na_cvm: datetime | None
    no_banco: datetime | None

    def atrasado(self, agora: datetime, tolerancia: timedelta = TOLERANCIA) -> bool:
        """A CVM tem versao mais nova, publicada ha mais tempo do que a tolerancia."""
        if self.na_cvm is None:
            return False  # ainda nao publicado: nao ha o que estar atrasado
        if agora - self.na_cvm < tolerancia:
            return False
        return self.no_banco is None or self.na_cvm > self.no_banco


@dataclass(frozen=True)
class Trimestre:
    """Um trimestre cujo prazo de entrega (mais a folga) ja passou."""

    dt_refer: date
    tipo: str
    anterior: date


def _fim_do_trimestre(ano: int, trimestre: int) -> date:
    mes = trimestre * 3
    return date(ano, mes, 31 if mes in (3, 12) else 30)


def trimestre_esperado(hoje: date) -> Trimestre:
    """O trimestre mais recente que ja deveria estar no banco em `hoje`.

    Ex.: em 16/11/2026 ainda e o 2T26 -- o prazo do 3T26 venceu em 14/11, mas a
    CVM so publica no domingo e a carga le em seguida; a partir de 23/11 passa
    a ser o 3T26.
    """
    candidatos: list[Trimestre] = []
    for ano in (hoje.year - 1, hoje.year):
        for tri in (1, 2, 3, 4):
            fim = _fim_do_trimestre(ano, tri)
            tipo, prazo = ("DFP", PRAZO_DFP) if tri == 4 else ("ITR", PRAZO_ITR)
            if hoje >= fim + timedelta(days=prazo + FOLGA_DE_PUBLICACAO):
                anterior = _fim_do_trimestre(ano if tri > 1 else ano - 1, tri - 1 or 4)
                candidatos.append(Trimestre(dt_refer=fim, tipo=tipo, anterior=anterior))
    return max(candidatos, key=lambda t: t.dt_refer)


@dataclass
class Conferencia:
    """O resultado: uma linha por coisa conferida, e a lista do que esta errado."""

    linhas: list[str] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)

    @property
    def em_dia(self) -> bool:
        return not self.problemas


def _data(momento: datetime | None) -> str:
    return momento.astimezone(UTC).strftime("%d/%m/%Y %H:%M UTC") if momento else "nunca"


def conferir(
    engine: Engine,
    config: FundamentosConfig,
    *,
    agora: datetime | None = None,
    consultar: Callable[[str], datetime | None] = data_na_cvm,
) -> Conferencia:
    """Compara o banco com a CVM. `consultar` recebe a URL e devolve a data na CVM."""
    momento = agora if agora is not None else datetime.now(UTC)
    saida = Conferencia()

    for ano in range(config.ano_inicial, momento.year + 1):
        for tipo in ("ITR", "DFP"):
            url = url_do_zip(tipo, ano)
            try:
                na_cvm = consultar(url)
            except CvmIndisponivelError as exc:
                # Sem resposta da CVM nao da para afirmar atraso nem pontualidade.
                saida.linhas.append(f"{tipo} {ano}: CVM nao respondeu ({exc})")
                continue
            anterior = repository.buscar_arquivo_externo(engine, url)
            processado = anterior is not None and anterior["processado_em"] is not None
            no_banco = anterior["modificado_em"] if anterior and processado else None
            arquivo = ArquivoConferido(tipo=tipo, ano=ano, na_cvm=na_cvm, no_banco=no_banco)
            if na_cvm is None:
                saida.linhas.append(f"{tipo} {ano}: ainda nao publicado pela CVM")
            elif arquivo.atrasado(momento):
                texto = (
                    f"{tipo} {ano}: a CVM publicou em {_data(na_cvm)} e o banco tem a "
                    f"versao de {_data(no_banco)}"
                )
                saida.linhas.append(f"ATRASADO {texto}")
                saida.problemas.append(texto)
            else:
                saida.linhas.append(f"{tipo} {ano}: em dia (CVM de {_data(na_cvm)})")

    esperado = trimestre_esperado(momento.date())
    com_novo, com_anterior = repository.cobertura_do_trimestre(
        engine, esperado.dt_refer, esperado.anterior
    )
    rotulo = f"{esperado.tipo} de {esperado.dt_refer.strftime('%d/%m/%Y')}"
    if com_anterior == 0:
        # Banco novo ou sem historico: nao ha contra o que medir.
        saida.linhas.append(f"cobertura do {rotulo}: sem base de comparacao no banco")
    else:
        fracao = com_novo / com_anterior
        texto = (
            f"cobertura do {rotulo}: {com_novo} de {com_anterior} empresas que entregaram o "
            f"trimestre anterior ({fracao:.0%})"
        )
        if fracao < COBERTURA_MINIMA:
            saida.linhas.append(f"INCOMPLETO {texto}")
            saida.problemas.append(f"{texto}; o esperado e pelo menos {COBERTURA_MINIMA:.0%}")
        else:
            saida.linhas.append(texto)
    return saida
