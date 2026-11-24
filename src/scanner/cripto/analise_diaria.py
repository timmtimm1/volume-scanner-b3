"""A rodada da noite da pagina Analise: carga do que falta, conta e troca das tabelas.

Roda pelo workflow `cripto-analise`, depois do `cripto`, com
`SCANNER_MERCADO=cripto`. Passos:

1. le o estado (`analise_moedas`) e a lista de pares da Binance, com os
   deslistados;
2. pede so os candles que faltam (`historico.atualizar`);
3. separa o que nao e cripto (`filtros.motivo_de_fora`) e calcula as tabelas
   (`analise.calcular`);
4. troca as quatro tabelas numa transacao.

E uma lente de leitura: nao alimenta alerta, setup, semaforo nem backtest.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import Engine

from scanner import mercado
from scanner.cripto import analise, filtros, historico, sazonal
from scanner.cripto.historico import BuscarBarras, Historico, RelatorioDaCarga


@dataclass
class RelatorioDaAnalise:
    dia: date
    pronto: bool = False
    carga: RelatorioDaCarga | None = None
    na_conta: int = 0
    fora: dict[str, list[str]] = field(default_factory=dict)
    linhas: dict[str, int] = field(default_factory=dict)
    # O que o estudo sazonal escolheu, uma linha por lado (para o log).
    estudo: list[str] = field(default_factory=list)
    dry_run: bool = False

    def summary(self) -> str:
        if self.pronto:
            return f"[pronto] a analise ate {self.dia} ja foi gravada; nada a fazer."
        fora = sum(len(v) for v in self.fora.values())
        motivos = ", ".join(f"{len(v)} {k}" for k, v in sorted(self.fora.items()))
        partes = [
            f"[analise] ate {self.dia}: {self.na_conta} criptos na conta ({fora} fora: {motivos})"
        ]
        if self.carga is not None:
            partes.append(f"carga: {self.carga.summary()}")
        if self.linhas:
            verbo = "calculadas" if self.dry_run else "gravadas"
            partes.append(
                f"{verbo} {self.linhas.get('anual', 0):,} linhas por ano, "
                f"{self.linhas.get('mensal', 0):,} por mes e "
                f"{self.linhas.get('movel', 0):,} na janela movel"
            )
        texto = "; ".join(partes)
        for linha in self.estudo:
            texto += f"\n[estudo] {linha}"
        # Quem ficou de fora e por que, por extenso: a regra das acoes tokenizadas
        # e por nome e data, e uma cripto nova poderia cair nela por engano.
        for motivo, moedas in sorted(self.fora.items()):
            texto += f"\n[analise] fora ({motivo}): {', '.join(sorted(moedas))}"
        return f"[dry-run] {texto}" if self.dry_run else texto


def separar(estado: Mapping[str, Historico]) -> tuple[list[Historico], dict[str, str]]:
    """As moedas que entram na conta e o motivo de cada uma que fica de fora."""
    entram: list[Historico] = []
    fora: dict[str, str] = {}
    for moeda, h in estado.items():
        motivo = filtros.motivo_de_fora(moeda, h.serie())
        if motivo is None:
            entram.append(h)
        else:
            fora[moeda] = motivo
    return entram, fora


def rodar(
    engine: Engine,
    *,
    ontem: date,
    pares: Mapping[str, str],
    negociando: set[str],
    binance: BuscarBarras,
    kraken: BuscarBarras,
    fora_da_binance: Mapping[str, str],
    so_se_faltar: bool = False,
    dry_run: bool = False,
    periodos: tuple[tuple[int, int], tuple[int, int]] | None = None,
) -> RelatorioDaAnalise:
    from scanner.storage.repository import (
        analise_em_dia,
        gravar_analise,
        ler_historicos_de_cripto,
    )

    if so_se_faltar and analise_em_dia(engine, ontem):
        return RelatorioDaAnalise(dia=ontem, pronto=True)

    estado, carga = historico.atualizar(
        ler_historicos_de_cripto(engine),
        pares,
        negociando,
        ontem,
        binance=binance,
        kraken=kraken,
        fora_da_binance=fora_da_binance,
    )
    entram, fora = separar(estado)
    fech, vol = historico.matrizes(entram)
    resultado = analise.calcular(fech, vol)
    estudo = sazonal.calcular(fech, vol, periodos or mercado.periodos())
    por_motivo: dict[str, list[str]] = defaultdict(list)
    for moeda, motivo in fora.items():
        por_motivo[motivo].append(moeda)

    if dry_run:
        linhas = {
            "anual": len(resultado.anual),
            "mensal": len(resultado.mensal),
            "movel": len(resultado.movel),
            "cesta": len(estudo.cesta),
            "janelas": len(estudo.janelas),
        }
    else:
        linhas = gravar_analise(engine, estado, fora, resultado, estudo)
    return RelatorioDaAnalise(
        dia=ontem,
        carga=carga,
        na_conta=len(entram),
        fora=dict(por_motivo),
        linhas=linhas,
        estudo=sazonal.escolhidas(estudo.janelas),
        dry_run=dry_run,
    )
