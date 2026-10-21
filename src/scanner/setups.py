"""Setups: o ciclo de vida de cada gatilho filtrado da aba Setups.

Lente separada do alerta de volume: nada aqui toca a regra de 6 sigma da secao
4 do plano (ver a secao "Setups" do CLAUDE.md). A regra em si mora em
`scanner.gatilhos.regra`; este modulo so a roda toda noite e acompanha o que
acontece depois:

1. armado: o candle saiu nesta noite. Confirma se o pregao seguinte passar da
   maxima do candle;
2. confirmado: passou. A entrada de referencia e a maxima (ou a abertura, se o
   papel ja abriu acima dela). Fica em andamento ate fechar abaixo da minima do
   padrao (`stop`) ou completar o prazo (`prazo`);
3. nao_confirmou: o pregao seguinte nao passou da maxima.

Cada setup e gravado uma vez, na noite em que aparece, e o que foi mostrado
fica congelado. Recalcular a janela inteira toda noite daria resultados um
pouco diferentes para dias antigos -- o motor de suporte so enxerga o que esta
dentro dos 400 pregoes do banco --, e o historico da aba tem de ser o que o
usuario viu. Na estreia (tabela vazia), a janela inteira entra de uma vez com
`ao_vivo` falso, para a ficha ter as setas do passado.

Estado e resultados sao calculados de novo a cada noite a partir das barras:
assim uma noite perdida (B3 atrasada, Actions fora do ar) se resolve sozinha
na seguinte.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import cast

import numpy as np
import numpy.typing as npt
import pandas as pd
from sqlalchemy import Engine

from scanner.calendar import next_trading_day
from scanner.config import ScannerConfig
from scanner.gatilhos.regra import Analise, analisar, niveis, setups
from scanner.storage.repository import (
    atualizar_setups,
    carregar_setups,
    criar_alerta,
    gravar_setups,
    trocar_niveis,
    ultimos_por_categoria,
)

F64 = npt.NDArray[np.float64]
I64 = npt.NDArray[np.int64]

HORIZONTES = (5, 10, 20)
COLUNAS_AVANCO = ("id", "estado", "confirmado_em", "entrada", "encerrado_em", "saida")


def _posicoes(frame: pd.DataFrame, a: Analise) -> tuple[pd.DataFrame, I64, I64]:
    """Linha e coluna de cada setup nas matrizes; quem saiu da janela fica de fora."""
    col = pd.Series(range(len(a.m.tickers)), index=a.m.tickers)
    dia = pd.Series(range(len(a.m.datas)), index=pd.Index(a.m.datas.date))
    c = frame["ticker"].map(col)
    d = frame["trade_date"].map(dia)
    ok = c.notna() & d.notna()
    linhas = np.asarray(d[ok], dtype=np.int64)
    colunas = np.asarray(c[ok], dtype=np.int64)
    return frame[ok.to_numpy()], linhas, colunas


def _indice_de(datas: pd.Series, a: Analise) -> I64:
    dia = pd.Series(range(len(a.m.datas)), index=pd.Index(a.m.datas.date))
    return np.array(datas.map(dia).fillna(-1), dtype=np.int64)


def _fechamento_ff(a: Analise) -> F64:
    return pd.DataFrame(a.m.fechamento).ffill(limit=5).to_numpy(dtype=np.float64)


def _num(serie: pd.Series) -> F64:
    return pd.to_numeric(serie, errors="coerce").to_numpy(dtype=np.float64)


def avancar(abertos: pd.DataFrame, a: Analise, prazo: int) -> pd.DataFrame:
    """Novo estado dos setups armados e confirmados, so as linhas que mudaram.

    Precos gravados estao na escala do dia do candle; as matrizes, na escala do
    ultimo dia. `a.ajuste` faz a ponte, e o que volta para o banco e convertido
    de novo para a escala do dia em que aconteceu (entrada no dia da
    confirmacao, saida no dia do encerramento).
    """
    vazio = pd.DataFrame({c: pd.Series(dtype="object") for c in COLUNAS_AVANCO})
    if abertos.empty:
        return vazio
    f, d0, col = _posicoes(abertos, a)
    if f.empty:
        return vazio
    m = a.m
    ultimo = len(m.datas) - 1
    cff = _fechamento_ff(a)
    esc0 = a.ajuste[d0, col]
    maxima = _num(f["maxima"]) * esc0
    minima = _num(f["minima"]) * esc0
    estado = f["estado"].to_numpy(dtype=object).copy()
    dc = _indice_de(f["confirmado_em"], a)
    entrada = _num(f["entrada"]) * np.where(dc >= 0, a.ajuste[np.maximum(dc, 0), col], np.nan)
    fim = np.full(len(f), -1, dtype=np.int64)
    saida = np.full(len(f), np.nan)

    # armado -> confirmado ou nao_confirmou, olhando o pregao seguinte
    d1 = d0 + 1
    pode = (estado == "armado") & (d1 <= ultimo)
    d1c = np.minimum(d1, ultimo)
    with np.errstate(invalid="ignore"):
        confirma = pode & (m.maxima[d1c, col] > maxima)
    falha = pode & ~confirma
    estado[confirma] = "confirmado"
    dc[confirma] = d1[confirma]
    entrada[confirma] = np.fmax(m.abertura[d1c, col], maxima)[confirma]
    estado[falha] = "nao_confirmou"
    fim[falha] = d1[falha]

    # confirmado -> stop (fechou abaixo da minima do padrao) ou prazo
    andando = estado == "confirmado"
    passos = np.arange(prazo + 1)
    t = dc[:, None] + passos[None, :]
    dentro = (t <= ultimo) & (dc[:, None] >= 0)
    tt = np.clip(t, 0, ultimo)
    fech = cff[tt, col[:, None]]
    with np.errstate(invalid="ignore"):
        abaixo = dentro & andando[:, None] & (fech < minima[:, None])
    primeiro = np.argmax(abaixo, axis=1)
    para = andando & abaixo.any(axis=1)
    linhas = np.arange(len(f))
    estado[para] = "stop"
    fim[para] = (dc + primeiro)[para]
    saida[para] = fech[linhas, primeiro][para]
    vence = andando & ~para & (dc + prazo <= ultimo)
    estado[vence] = "prazo"
    fim[vence] = (dc + prazo)[vence]
    saida[vence] = fech[linhas, prazo][vence]

    mudou = estado != f["estado"].to_numpy(dtype=object)
    if not mudou.any():
        return vazio
    datas = m.datas.date
    escala_dc = np.where(dc >= 0, a.ajuste[np.maximum(dc, 0), col], np.nan)
    escala_fim = np.where(fim >= 0, a.ajuste[np.maximum(fim, 0), col], np.nan)
    out = pd.DataFrame(
        {
            "id": f["id"].to_numpy(),
            "estado": estado,
            "confirmado_em": [datas[i] if i >= 0 else None for i in dc],
            "entrada": entrada / escala_dc,
            "encerrado_em": [datas[i] if i >= 0 else None for i in fim],
            "saida": saida / escala_fim,
        }
    )
    return cast(pd.DataFrame, out[mudou].reset_index(drop=True))


def resultados(gravados: pd.DataFrame, a: Analise) -> pd.DataFrame:
    """Retornos de cada setup ate onde as barras alcancam.

    `r*`: do fechamento do candle. `m*`: media simples do universo liquido na
    mesma janela, para comparar com o mercado. `rc*`: da entrada confirmada ao
    fechamento `h` pregoes depois da confirmacao, como no estudo.
    """
    colunas = ["id", *(f"{p}{h}" for p in ("r", "m", "rc") for h in HORIZONTES)]
    if gravados.empty:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in colunas})
    f, d0, col = _posicoes(gravados, a)
    if f.empty:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in colunas})
    ultimo = len(a.m.datas) - 1
    cff = _fechamento_ff(a)
    dc = _indice_de(f["confirmado_em"], a)
    entrada = _num(f["entrada"]) * np.where(dc >= 0, a.ajuste[np.maximum(dc, 0), col], np.nan)
    out: dict[str, object] = {"id": f["id"].to_numpy()}
    with np.errstate(invalid="ignore", divide="ignore"):
        for h in HORIZONTES:
            alvo = d0 + h
            ok = alvo <= ultimo
            r = cff[np.minimum(alvo, ultimo), col] / cff[d0, col] - 1
            out[f"r{h}"] = np.where(ok, r, np.nan)
            # media do universo liquido de cada dia: uma conta por dia, nao por setup
            janela = np.full_like(cff, np.nan)
            janela[: len(cff) - h] = cff[h:] / cff[: len(cff) - h] - 1
            with warnings.catch_warnings():
                # os primeiros pregoes da janela ainda nao tem papel liquido
                warnings.simplefilter("ignore", RuntimeWarning)
                media = np.nanmean(np.where(a.liquido, janela, np.nan), axis=1)
            out[f"m{h}"] = np.where(ok, media[d0], np.nan)
            alvo_c = dc + h
            ok_c = (dc >= 0) & (alvo_c <= ultimo)
            rc = cff[np.clip(alvo_c, 0, ultimo), col] / entrada - 1
            out[f"rc{h}"] = np.where(ok_c, rc, np.nan)
    return pd.DataFrame(out)


def criar_alertas(engine: Engine, gravados: pd.DataFrame, config: ScannerConfig) -> int:
    """Um alerta "acima da maxima" para cada setup armado ao vivo nesta noite.

    O alerta vale so no pregao seguinte ao candle, que e quando o setup confirma
    ou nao, e nasce um centavo acima da maxima: a confirmacao pede passar dela,
    e tocar exatamente a maxima nao e passar. Setup retroativo (estreia, ou
    noite perdida) nao ganha alerta -- o pregao da confirmacao ja passou.
    """
    cfg = config.setups
    if not cfg.alerta or gravados.empty:
        return 0
    categorias = (
        ["reversao"]
        + (["forca"] if cfg.alerta_forca else [])
        + (["media"] if cfg.alerta_media else [])
    )
    alvo = gravados[gravados["ao_vivo"].astype(bool) & gravados["categoria"].isin(categorias)]
    # Poucos por noite (cerca de um por semana): um INSERT por setup basta.
    for linha in alvo.to_dict("records"):
        candle: date = linha["trade_date"]
        criar_alerta(
            engine,
            str(linha["ticker"]),
            candle,
            Decimal(str(round(float(linha["maxima"]) + 0.01, 2))),
            "acima",
            expira_em=next_trading_day(candle),
            setup_id=int(linha["id"]),
        )
    return len(alvo)


@dataclass(frozen=True)
class RelatorioDeSetups:
    """O que a etapa de setups fez num pregao."""

    dia: date
    estreia: bool = False
    gravados: int = 0
    armados: list[tuple[str, bool]] = field(default_factory=list)  # (ticker, destaque)
    media: list[str] = field(default_factory=list)
    forca: list[str] = field(default_factory=list)
    confirmados: list[str] = field(default_factory=list)
    nao_confirmaram: list[str] = field(default_factory=list)
    encerrados: int = 0
    em_andamento: int = 0
    niveis: int = 0
    alertas: int = 0
    dry_run: bool = False
    desligado: bool = False

    def summary(self) -> str:
        if self.desligado:
            return "setups desligados no config"
        prefixo = "[dry-run] " if self.dry_run else ""
        armados = ", ".join(f"{t}{' (destaque)' if d else ''}" for t, d in self.armados) or "nenhum"
        partes = [f"{prefixo}setups: armados hoje {armados}"]
        if self.media:
            partes.append(f"na media {', '.join(self.media)}")
        if self.forca:
            partes.append(f"forca {', '.join(self.forca)}")
        partes.append(f"{len(self.confirmados)} confirmado(s)")
        partes.append(f"{len(self.nao_confirmaram)} nao confirmou")
        partes.append(f"{self.encerrados} encerrado(s), {self.em_andamento} em andamento")
        partes.append(f"{self.niveis:,} niveis")
        if self.alertas:
            partes.append(f"{self.alertas} alerta(s) de confirmacao criado(s)")
        if self.estreia:
            partes.append(f"estreia: {self.gravados} setups retroativos gravados")
        elif self.gravados > len(self.armados) + len(self.media) + len(self.forca):
            partes.append(f"{self.gravados} gravados (retroativos de categoria nova)")
        return "; ".join(partes)


def run_setups(
    engine: Engine, config: ScannerConfig, dia: date, *, bars: pd.DataFrame, dry_run: bool = False
) -> RelatorioDeSetups:
    """A etapa do `scanner daily`: detecta, grava, avanca estados e troca os niveis.

    `bars` e o `contexto.bars` do pregao (todas as barras do banco). Em
    `dry_run` nada e gravado; o relatorio diz o que seria.
    """
    cfg = config.setups
    if not cfg.enabled:
        return RelatorioDeSetups(dia=dia, desligado=True)
    barras = bars[pd.to_datetime(bars["trade_date"]) <= pd.Timestamp(dia)]
    if barras.empty:
        return RelatorioDeSetups(dia=dia, dry_run=dry_run)

    a = analisar(barras, cfg, config.universe)
    todos = setups(a, cfg)
    # Cada categoria a partir do seu ultimo candle gravado: categoria nova (a
    # `media`, de 21/10/2026) grava a janela inteira na primeira noite.
    ultimos = ultimos_por_categoria(engine)
    estreia = not ultimos
    # poucas centenas de linhas: comparar data a data e mais simples que alinhar
    # datas com categorias ausentes num Series
    entra = [
        cat not in ultimos or dia_ > ultimos[cat]
        for cat, dia_ in zip(todos["categoria"], todos["trade_date"], strict=True)
    ]
    novos = todos[entra]
    novos = novos.assign(ao_vivo=novos["trade_date"] == dia, estado="armado")
    desenho = niveis(a, cfg)

    gravados = novos.head(0) if dry_run else gravar_setups(engine, novos)
    alertas = 0 if dry_run else criar_alertas(engine, gravados, config)
    abertos = carregar_setups(engine, abertos=True)
    mudancas = avancar(abertos, a, cfg.prazo_pregoes)
    if not dry_run:
        atualizar_setups(engine, mudancas)
        janela = carregar_setups(engine, desde=a.m.datas[0].date())
        atualizar_setups(engine, resultados(janela, a))
        trocar_niveis(engine, desenho)

    hoje = novos[novos["trade_date"] == dia]
    rev = hoje[hoje["categoria"] == "reversao"]
    confirmou = mudancas["confirmado_em"] == dia
    nao = mudancas["estado"] == "nao_confirmou"
    encerrou = mudancas["estado"].isin(["stop", "prazo"])
    tickers_mud = abertos.set_index("id")["ticker"] if not abertos.empty else pd.Series(dtype=str)
    # estado de cada aberto ao fim da noite: o de antes, trocado pelo que mudou
    final = abertos.set_index("id")["estado"].copy() if not abertos.empty else pd.Series(dtype=str)
    if not mudancas.empty:
        final.update(mudancas.set_index("id")["estado"])
    em_andamento = int((final == "confirmado").sum())
    return RelatorioDeSetups(
        dia=dia,
        estreia=estreia,
        gravados=len(gravados),
        armados=[(str(r.ticker), bool(r.destaque)) for r in rev.itertuples()],
        media=[str(t) for t in hoje.loc[hoje["categoria"] == "media", "ticker"]],
        forca=[str(t) for t in hoje.loc[hoje["categoria"] == "forca", "ticker"]],
        confirmados=[str(tickers_mud.get(i, "?")) for i in mudancas.loc[confirmou, "id"]],
        nao_confirmaram=[str(tickers_mud.get(i, "?")) for i in mudancas.loc[nao, "id"]],
        encerrados=int(encerrou.sum()),
        em_andamento=em_andamento,
        niveis=len(desenho),
        alertas=alertas,
        dry_run=dry_run,
    )
