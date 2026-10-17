"""Monta o bloco de dados de mercado do resumo semanal e a previa em texto.

O bloco de acoes e obrigatorio: sem o ultimo pregao da semana em `daily_bars`
nao ha resumo (`PregaoAusenteError`, para quem agenda tentar de novo). Todo o
resto vem de fontes externas e e opcional: uma que cai vira `{"erro": ...}` no
proprio bloco, e o resumo sai com o que deu. Nunca derrubar o resumo por causa
de cripto ou do Fed.

Unidades do payload, numa regra so: TAXA (juro, inflacao, yield) vai em % ao
ano, como a fonte publica -- `selic_meta`, `ipca_12m`, a curva da ANBIMA, os
Treasuries e o Fed. RETORNO (variacao de preco, CDI acumulado) vai em fracao:
0,051 e +5,1%. Pontos-base (`variacao_bp`) sao pontos-base.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
from sqlalchemy import Engine

from scanner.calendar import sessions_before
from scanner.config import ScannerConfig
from scanner.fundamentos.b3 import novo_cliente
from scanner.notify.telegram import br, pct
from scanner.semana.acoes import (
    PREGOES_DE_BASE,
    buscar_eventos_da_semana,
    ranking,
    variacoes_da_semana,
)
from scanner.semana.fontes import FonteIndisponivelError, anbima, bcb, cripto, fed, treasury, yahoo
from scanner.semana.periodo import Semana
from scanner.storage import repository
from scanner.universe import load_universe, tickers

logger = logging.getLogger(__name__)

VERSAO = 1

# Pausa entre emissores na B3: ~300 chamadas seguidas ao mesmo endpoint.
PAUSA_B3 = 0.1


class PregaoAusenteError(RuntimeError):
    """O ultimo pregao da semana ainda nao esta em `daily_bars`."""


def _limpo(valor: Any) -> Any:
    """JSON puro: NaN e infinito viram null, datas viram ISO, numpy vira Python."""
    if isinstance(valor, dict):
        return {str(k): _limpo(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_limpo(v) for v in valor]
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    if hasattr(valor, "item") and not isinstance(valor, str | bytes):
        valor = valor.item()
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    if valor is pd.NaT:
        return None
    return valor


def _linhas(frame: pd.DataFrame) -> list[dict[str, Any]]:
    colunas = [
        "ticker",
        "data_inicio",
        "preco_inicio",
        "data_fim",
        "preco_fim",
        "variacao",
        "variacao_bruta",
        "proventos_por_acao",
        "multiplicador",
        "ajustado",
        "conferido",
        "eventos_sem_ajuste",
    ]
    return [_limpo(linha) for linha in frame[colunas].to_dict(orient="records")]


def _isolado(bloco: str, funcao: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Roda a fonte; se ela falhar, o bloco vira `{"erro": motivo}`."""
    try:
        resultado: dict[str, Any] = funcao(*args, **kwargs)
        return resultado
    except FonteIndisponivelError as exc:
        logger.warning("[semana] bloco %s indisponivel: %s", bloco, exc)
        return {"erro": exc.motivo}
    # Excecao ampla de proposito: o resumo nao pode cair por causa de um bloco
    # opcional, nem por um bug de parse que ninguem previu. O erro vai para o
    # log com o traceback e para o bloco como texto.
    except Exception as exc:
        logger.exception("[semana] bloco %s falhou de forma inesperada", bloco)
        return {"erro": f"erro inesperado ({exc.__class__.__name__}: {exc})"}


def _bloco_acoes(engine: Engine, config: ScannerConfig, semana: Semana) -> dict[str, Any]:
    universo = tickers(load_universe(engine, semana.fim, config.universe))
    desde = sessions_before(semana.inicio, PREGOES_DE_BASE, inclusive=True)[0]
    barras = repository.barras_de_fechamento(engine, desde, semana.fim)

    cliente = novo_cliente()
    try:
        coleta = buscar_eventos_da_semana(engine, universo, semana, cliente, pausa=PAUSA_B3)
    finally:
        cliente.close()

    eventos = coleta.eventos.copy()
    if not eventos.empty:
        eventos["multiplicador"] = eventos["multiplicador"].astype(float)
    variacoes = variacoes_da_semana(
        barras, universo, semana, coleta.proventos, eventos, coleta.conferidos
    )
    altas, quedas, fora = ranking(variacoes, config.semana.acoes_por_lado)
    return {
        "altas": _linhas(altas),
        "quedas": _linhas(quedas),
        "fora_do_ranking": _linhas(fora),
        "avaliados": len(variacoes),
        "conferidos": int(variacoes["conferido"].sum()) if not variacoes.empty else 0,
        "falhas_b3": list(coleta.falhas),
    }


def montar_dados_de_mercado(
    engine: Engine, config: ScannerConfig, semana: Semana, *, agora: datetime | None = None
) -> dict[str, Any]:
    """O payload do resumo da semana (JSON puro)."""
    if not repository.existe_barra_em(engine, semana.fim):
        raise PregaoAusenteError(
            f"o pregao de {semana.fim.isoformat()} ainda nao esta em daily_bars"
        )
    momento = (agora or datetime.now(UTC)).astimezone(UTC)
    cfg = config.semana

    acoes = _bloco_acoes(engine, config, semana)
    payload: dict[str, Any] = {
        "versao": VERSAO,
        "semana": {
            "sexta": semana.sexta,
            "inicio": semana.inicio,
            "fim": semana.fim,
            "pregoes": list(semana.pregoes),
        },
        "gerado_em": momento,
        "acoes": acoes,
        "abertura": _isolado("abertura", yahoo.abertura, semana),
        "cripto": _isolado(
            "cripto",
            cripto.buscar_cripto,
            categorias_excluidas=cfg.cripto_categorias_excluidas,
            top=cfg.cripto_top,
            destaques=cfg.cripto_destaques,
            agora=momento,
        ),
        "juros_br": {
            "curva": _isolado("curva", anbima.curva_prefixada, semana, cfg.curva_vertices_du),
            "indicadores": _isolado("indicadores", bcb.indicadores, semana),
        },
        "eua": {
            "treasuries": _isolado("treasuries", treasury.treasuries, semana, cfg.treasuries),
            "fed": _isolado("fed", fed.dot_plot, semana),
        },
    }
    limpo: dict[str, Any] = _limpo(payload)
    return limpo


# --- previa em texto ------------------------------------------------------


def _data_br(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def _bp(valor: float | None, casas: int) -> str:
    """Pontos-base com sinal: a direcao e o que se le primeiro."""
    if valor is None:
        return "-"
    return f"{'+' if valor >= 0 else '-'}{br(abs(valor), casas)} bp"


def _indisponivel(bloco: dict[str, Any]) -> str | None:
    return f"indisponivel: {bloco['erro']}" if "erro" in bloco else None


def _linha_acao(posicao: int, a: dict[str, Any]) -> str:
    notas: list[str] = []
    if a["ajustado"]:
        partes = [f"bruta {pct(a['variacao_bruta'])}"]
        if a["proventos_por_acao"]:
            partes.append(f"proventos R$ {br(a['proventos_por_acao'], 4)}")
        if a["multiplicador"] != 1:
            partes.append(f"acoes x{br(a['multiplicador'], 4)}")
        notas.append("ajustada: " + ", ".join(partes))
    if not a["conferido"]:
        notas.append("eventos NAO conferidos")
    sufixo = f"   ({'; '.join(notas)})" if notas else ""
    return (
        f"  {posicao:>2}. {a['ticker']:<7} {pct(a['variacao']):>8}   "
        f"R$ {br(a['preco_inicio'])} -> R$ {br(a['preco_fim'])}{sufixo}"
    )


def _previa_acoes(acoes: dict[str, Any]) -> list[str]:
    linhas = [
        f"ACOES  (avaliados {acoes['avaliados']}, com eventos conferidos {acoes['conferidos']})"
    ]
    if acoes["falhas_b3"]:
        linhas.append(
            f"  B3 sem resposta para {len(acoes['falhas_b3'])} emissores: "
            + ", ".join(acoes["falhas_b3"])
        )
    for titulo, chave in (("Maiores altas", "altas"), ("Maiores quedas", "quedas")):
        linhas.append(f" {titulo}")
        linhas += [_linha_acao(i, a) for i, a in enumerate(acoes[chave], start=1)] or [
            "  (nenhuma)"
        ]
    if acoes["fora_do_ranking"]:
        linhas.append(" Fora do ranking (evento sem razao por acao)")
        linhas += [
            f"      {a['ticker']:<7} bruta {pct(a['variacao_bruta']):>8}   "
            f"R$ {br(a['preco_inicio'])} -> R$ {br(a['preco_fim'])}   ({a['eventos_sem_ajuste']})"
            for a in acoes["fora_do_ranking"]
        ]
    return linhas


def _previa_abertura(abertura: dict[str, Any]) -> list[str]:
    nomes = {
        "ibovespa": ("Ibovespa", 0),
        "dolar": ("Dolar", 4),
        "brent": ("Brent", 2),
        "ouro": ("Ouro", 2),
    }
    linhas = ["ABERTURA"]
    if (msg := _indisponivel(abertura)) is not None:
        return [*linhas, f"  {msg}"]
    for chave, (nome, casas) in nomes.items():
        ativo = abertura.get(chave, {"erro": "ausente"})
        if (msg := _indisponivel(ativo)) is not None:
            linhas.append(f"  {nome:<9} {msg}")
            continue
        linhas.append(
            f"  {nome:<9} {br(ativo['valor'], casas):>12} ({_data_br(ativo['data'])})   "
            f"semana {pct(ativo['semana'])}   mes {pct(ativo['mes'])}   ano {pct(ativo['ano'])}"
        )
    return linhas


def _linha_moeda(m: dict[str, Any]) -> str:
    return (
        f"  {m['rank']:>2}. {m['simbolo']:<7} US$ {br(m['preco'], 2 if m['preco'] >= 1 else 4):>12}"
        f"   7d {pct(m['variacao_7d'])}"
    )


def _previa_cripto(bloco: dict[str, Any]) -> list[str]:
    if (msg := _indisponivel(bloco)) is not None:
        return ["CRIPTO", f"  {msg}"]
    linhas = [f"CRIPTO  (coletado em {bloco['coletado_em']}; janela de 7 dias ate a coleta)"]
    for chave in ("btc", "eth"):
        if bloco[chave]:
            linhas.append(_linha_moeda(bloco[chave]))
    linhas.append(f" Top {len(bloco['moedas'])} sem stablecoins e tokenizados")
    linhas += [_linha_moeda(m) for m in bloco["moedas"]]
    linhas.append(" Maiores altas (sem BTC e ETH)")
    linhas += [_linha_moeda(m) for m in bloco["altas"]]
    linhas.append(" Maiores quedas (sem BTC e ETH)")
    linhas += [_linha_moeda(m) for m in bloco["quedas"]]
    return linhas


def _previa_juros(juros: dict[str, Any]) -> list[str]:
    linhas = ["JUROS BRASIL"]
    curva = juros["curva"]
    if (msg := _indisponivel(curva)) is not None:
        linhas.append(f"  Curva prefixada: {msg}")
    else:
        linhas.append(
            "  Curva prefixada ANBIMA "
            f"({_data_br(curva['data'])} vs {_data_br(curva['data_anterior'])})"
        )
        for v in curva["vertices"]:
            anterior = "-" if v["taxa_anterior"] is None else f"{br(v['taxa_anterior'], 4)}%"
            prazo = f"{br(v['anos'], 0)} {'ano' if v['anos'] == 1 else 'anos'}"
            linhas.append(
                f"    {prazo:>7} ({v['du']:>4} du)  {br(v['taxa'], 4):>8}% a.a."
                f"   antes {anterior}   {_bp(v['variacao_bp'], 1)}"
            )
    ind = juros["indicadores"]
    if (msg := _indisponivel(ind)) is not None:
        linhas.append(f"  Indicadores: {msg}")
    else:
        cdi_ate = f" (ate {_data_br(ind['cdi_data'])})" if ind["cdi_data"] else ""
        linhas.append(f"  Selic meta {br(ind['selic_meta'])}% a.a.")
        linhas.append(
            f"  CDI acumulado: mes {pct(ind['cdi_mes'], 2)}, ano {pct(ind['cdi_ano'], 2)}{cdi_ate}"
        )
        linhas.append(f"  IPCA 12 meses {br(ind['ipca_12m'])}% (ref. {ind['ipca_referencia']})")
    return linhas


def _previa_eua(eua: dict[str, Any]) -> list[str]:
    linhas = ["EUA"]
    tes = eua["treasuries"]
    if (msg := _indisponivel(tes)) is not None:
        linhas.append(f"  Treasuries: {msg}")
    else:
        linhas.append(f"  Treasuries ({_data_br(tes['data'])} vs {_data_br(tes['data_anterior'])})")
        for v in tes["vencimentos"]:
            linhas.append(
                f"    {v['prazo']:<5} {br(v['taxa'], 2):>6}%   antes {br(v['taxa_anterior'], 2)}%"
                f"   {_bp(v['variacao_bp'], 0)}"
            )
    f = eua["fed"]
    if (msg := _indisponivel(f)) is not None:
        linhas.append(f"  Fed (dot plot): {msg}")
    else:
        medianas = ", ".join(f"{m['periodo']} {br(m['taxa'], 1)}%" for m in f["medianas"])
        linhas.append(f"  Fed, mediana dos juros ({_data_br(f['data_projecao'])}): {medianas}")
    return linhas


def previa(payload: dict[str, Any]) -> str:
    """Texto simples para conferir o resumo a mao. Nao e a mensagem do Telegram."""
    s = payload["semana"]
    cabecalho = [
        f"RESUMO DA SEMANA DE {_data_br(s['sexta'])}",
        f"  base {_data_br(s['inicio'])} -> fim {_data_br(s['fim'])}, {len(s['pregoes'])} pregoes"
        f"   (gerado em {payload['gerado_em']})",
    ]
    blocos = [
        cabecalho,
        _previa_acoes(payload["acoes"]),
        _previa_abertura(payload["abertura"]),
        _previa_cripto(payload["cripto"]),
        _previa_juros(payload["juros_br"]),
        _previa_eua(payload["eua"]),
    ]
    return "\n\n".join("\n".join(b) for b in blocos)
