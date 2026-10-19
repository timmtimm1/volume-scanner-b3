"""Monta o bloco de dados de mercado do resumo semanal e a previa em texto.

O bloco de acoes e obrigatorio: sem o ultimo pregao da semana em `daily_bars`
nao ha resumo (`PregaoAusenteError`, para quem agenda tentar de novo). Todo o
resto vem de fontes externas e e opcional: uma que cai vira `{"erro": ...}` no
proprio bloco, e o resumo sai com o que deu. Nunca derrubar o resumo por causa
de cripto ou do Fed.

Unidades do payload, numa regra so: TAXA (juro, inflacao, yield) vai em % ao
ano, como a fonte publica -- `selic_meta`, `ipca_12m`, a curva do Tesouro Direto, os
Treasuries e o Fed. RETORNO (variacao de preco, CDI acumulado) vai em fracao:
0,051 e +5,1%. Pontos-base (`variacao_bp`) sao pontos-base.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime, timedelta
from typing import Any, NamedTuple

import pandas as pd
from sqlalchemy import Engine

from scanner.calendar import is_holiday, sessions_before
from scanner.config import ScannerConfig
from scanner.fundamentos.b3 import novo_cliente
from scanner.notify.telegram import br, pct
from scanner.semana import agenda, balancos, noticias
from scanner.semana.acoes import (
    PREGOES_DE_BASE,
    buscar_eventos_da_semana,
    ranking,
    variacoes_da_semana,
)
from scanner.semana.fontes import (
    FonteIndisponivelError,
    bcb,
    cripto,
    fed,
    google_noticias,
    tesouro_direto,
    treasury,
    yahoo,
)
from scanner.semana.periodo import Semana, proxima_semana
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


def _bloco_agenda(inicio: date, fim: date, semana: Semana) -> dict[str, Any]:
    eventos, avisos = agenda.montar_agenda(inicio, fim, focus_ate=semana.fim)
    return {"agenda": eventos, "agenda_avisos": avisos}


def _bloco_balancos(
    engine: Engine, config: ScannerConfig, semana: Semana, inicio: date, fim: date
) -> dict[str, Any]:
    universo = tickers(load_universe(engine, semana.fim, config.universe))
    return balancos.montar_balancos(engine, universo, inicio, fim, semana.fim)


def _bloco_proxima_semana(engine: Engine, config: ScannerConfig, semana: Semana) -> dict[str, Any]:
    """Agenda macro e balanços da semana seguinte; cada parte falha sozinha."""
    inicio, fim = proxima_semana(semana)
    dias = [inicio + timedelta(days=i) for i in range(5)]
    # `is_holiday` e o calendario da B3: aqui interessa o dia util sem pregao.
    feriados = [d for d in dias if is_holiday(d)]
    parte_agenda = _isolado("agenda", _bloco_agenda, inicio, fim, semana)
    avisos: list[str] = list(parte_agenda.get("agenda_avisos", []))
    if "erro" in parte_agenda:
        avisos.append(f"agenda indisponível: {parte_agenda['erro']}")
    return {
        "inicio": inicio,
        "fim": fim,
        "feriados_b3": feriados,
        "agenda": parte_agenda.get("agenda", []),
        "agenda_avisos": avisos,
        "balancos": _isolado("balancos", _bloco_balancos, engine, config, semana, inicio, fim),
    }


def _bloco_noticias(config: ScannerConfig, semana: Semana, momento: datetime) -> dict[str, Any]:
    """As historias mais repetidas da semana; busca que falha vira aviso."""
    cfg = config.semana
    brutas, avisos = google_noticias.coletar(cfg.noticias_buscas, semana.segunda)
    inicio = noticias.inicio_da_semana(semana.segunda)
    historias, contagem = noticias.selecionar(brutas, inicio, momento, cfg.noticias_top)
    return {
        "janela": {"de": inicio, "ate": momento},
        "buscas": list(cfg.noticias_buscas),
        "historias": historias,
        "contagem": contagem,
        "avisos": avisos,
    }


def _tentar(bloco: str, funcao: Any, *args: Any) -> tuple[Any, str | None]:
    """(resultado, None), ou (None, motivo) se a fonte falhar. Mesma regra do `_isolado`."""
    try:
        return funcao(*args), None
    except FonteIndisponivelError as exc:
        logger.warning("[semana] %s indisponivel: %s", bloco, exc)
        return None, exc.motivo
    # Excecao ampla de proposito, pelo mesmo motivo do `_isolado`.
    except Exception as exc:
        logger.exception("[semana] %s falhou de forma inesperada", bloco)
        return None, f"erro inesperado ({exc.__class__.__name__}: {exc})"


def _historico_de_juros(
    config: ScannerConfig, semana: Semana
) -> tuple[pd.DataFrame, str | None, str | None]:
    """(serie semanal TD + Selic, erro do Tesouro Direto, erro da Selic).

    O Tesouro Direto e a Selic falham separado: sem Selic o grafico ainda tem os
    prefixados, e sem Tesouro a Selic ainda e gravada.
    """
    desde = config.semana.juros_desde
    td, erro_td = _tentar(
        "tesouro_direto",
        lambda: tesouro_direto.serie_semanal(tesouro_direto.baixar_titulos(), desde, semana.sexta),
    )
    selic, erro_selic = _tentar("selic_historica", bcb.selic_semanal, desde, semana.sexta)
    partes = [p for p in (td, selic) if p is not None and not p.empty]
    frame = (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=tesouro_direto.COLUNAS_SEMANAL)
    )
    return frame, erro_td, erro_selic


class HistoricoGravado(NamedTuple):
    """O que `gravar_historico_de_juros` gravou: semanas por serie e o erro de cada fonte."""

    por_serie: dict[str, int]
    erro_td: str | None
    erro_selic: str | None


def gravar_historico_de_juros(
    engine: Engine, config: ScannerConfig, semana: Semana
) -> HistoricoGravado:
    """So o historico de juros ate a `semana`, sem montar nem enviar o resumo.

    Enche o grafico da aba Semana sem mandar mensagem: logo depois do deploy, ou
    quando o BCB volta do ar. Falha de gravacao no banco sobe (quem chama decide).
    """
    historico, erro_td, erro_selic = _historico_de_juros(config, semana)
    if not historico.empty:
        repository.gravar_juros_historico(engine, historico)
    por_serie = {str(k): int(v) for k, v in historico["serie"].value_counts().sort_index().items()}
    return HistoricoGravado(por_serie, erro_td, erro_selic)


def _bloco_curva(
    historico: pd.DataFrame, erro: str | None, semana: Semana, series: tuple[str, ...]
) -> dict[str, Any]:
    if erro is not None:
        return {"erro": erro}
    return _isolado("curva", tesouro_direto.montar_curva, historico, semana.sexta, series)


def montar_dados_de_mercado(
    engine: Engine,
    config: ScannerConfig,
    semana: Semana,
    *,
    agora: datetime | None = None,
    gravar_juros: bool = False,
) -> dict[str, Any]:
    """O payload do resumo da semana (JSON puro).

    A serie historica de juros (10 anos, uma linha por semana) e baixada junto,
    porque a fonte vem inteira de qualquer jeito. Ela so e GRAVADA em
    `juros_historico` com `gravar_juros`: montar sem gravar nao escreve no banco.
    """
    if not repository.existe_barra_em(engine, semana.fim):
        raise PregaoAusenteError(
            f"o pregao de {semana.fim.isoformat()} ainda nao esta em daily_bars"
        )
    momento = (agora or datetime.now(UTC)).astimezone(UTC)
    cfg = config.semana

    acoes = _bloco_acoes(engine, config, semana)
    historico, erro_td, erro_selic = _historico_de_juros(config, semana)
    if gravar_juros and not historico.empty:
        _, erro_gravacao = _tentar(
            "juros_historico", repository.gravar_juros_historico, engine, historico
        )
        if erro_gravacao is not None:
            logger.error("[semana] historico de juros nao gravado: %s", erro_gravacao)
    if erro_selic is not None:
        logger.warning("[semana] Selic historica ausente desta rodada: %s", erro_selic)
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
            "curva": _bloco_curva(historico, erro_td, semana, tesouro_direto.SERIES_PRE),
            "curva_real": _bloco_curva(historico, erro_td, semana, tesouro_direto.SERIES_REAL),
            "indicadores": _isolado("indicadores", bcb.indicadores, semana),
        },
        "eua": {
            "treasuries": _isolado("treasuries", treasury.treasuries, semana, cfg.treasuries),
            "fed": _isolado("fed", fed.dot_plot, semana),
        },
        "noticias": _isolado("noticias", _bloco_noticias, config, semana, momento),
        "proxima_semana": _bloco_proxima_semana(engine, config, semana),
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
    linhas += [_linha_moeda(m) for m in bloco["altas"]] or ["  (nenhuma)"]
    linhas.append(" Maiores quedas (sem BTC e ETH)")
    linhas += [_linha_moeda(m) for m in bloco["quedas"]] or ["  (nenhuma)"]
    return linhas


def _previa_curva(titulo: str, curva: dict[str, Any]) -> list[str]:
    if (msg := _indisponivel(curva)) is not None:
        return [f"  {titulo}: {msg}"]
    anterior_data = curva["data_anterior"]
    contra = f" vs {_data_br(anterior_data)}" if anterior_data else ""
    linhas = [f"  {titulo} Tesouro Direto ({_data_br(curva['data'])}{contra})"]
    for v in curva["vertices"]:
        anterior = "-" if v["taxa_anterior"] is None else f"{br(v['taxa_anterior'], 4)}%"
        prazo = f"{br(v['anos'], 0)} {'ano' if v['anos'] == 1 else 'anos'}"
        linhas.append(
            f"    {prazo:>7} ({v['du']:>4} du)  {br(v['taxa'], 4):>8}% a.a."
            f"   antes {anterior}   {_bp(v['variacao_bp'], 1)}"
        )
    return linhas


def _previa_juros(juros: dict[str, Any]) -> list[str]:
    linhas = ["JUROS BRASIL"]
    linhas += _previa_curva("Curva prefixada", juros["curva"])
    if "curva_real" in juros:
        linhas += _previa_curva("Juro real IPCA+", juros["curva_real"])
    ind = juros["indicadores"]
    if (msg := _indisponivel(ind)) is not None:
        linhas.append(f"  Indicadores: {msg}")
    else:
        cdi_ate = f" (ate {_data_br(ind['cdi_data'])})" if ind["cdi_data"] else ""
        ipca_ref = f" (ref. {ind['ipca_referencia']})" if ind["ipca_referencia"] else ""
        linhas.append(f"  Selic meta {br(ind['selic_meta'])}% a.a.")
        linhas.append(
            f"  CDI acumulado: mes {pct(ind['cdi_mes'], 2)}, ano {pct(ind['cdi_ano'], 2)}{cdi_ate}"
        )
        linhas.append(f"  IPCA 12 meses {br(ind['ipca_12m'])}%{ipca_ref}")
        for campo, motivo in ind.get("erros", {}).items():
            linhas.append(f"  {campo} indisponivel: {motivo}")
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


DIAS_DA_SEMANA = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom")


def _dia_curto(iso: str) -> str:
    dia = date.fromisoformat(iso)
    return f"{DIAS_DA_SEMANA[dia.weekday()]} {dia.strftime('%d/%m')}"


def _linha_evento(e: dict[str, Any]) -> str:
    nome = e["evento"] + (f" ({e['detalhe']})" if e["detalhe"] else "")
    consenso = e["consenso"]
    focus = (
        f"   Focus: {br(consenso['mediana'], 2)}{consenso['unidade']}"
        if consenso is not None
        else ""
    )
    return f"  {_dia_curto(e['data'])}  {e['hora'] or '--:--'}  {e['pais']:<3} {nome}{focus}"


def _linha_balanco_confirmado(b: dict[str, Any]) -> str:
    quando = f"{_dia_curto(b['data'])}  {b['horario'] or 'sem horario'}"
    trimestre = f"   trimestre {b['trimestre']}" if b["trimestre"] else ""
    return f"  {quando}  {b['empresa']} ({', '.join(b['tickers'])}){trimestre}   [{b['fonte']}]"


def _previa_noticias(bloco: dict[str, Any]) -> list[str]:
    if (msg := _indisponivel(bloco)) is not None:
        return ["NOTÍCIAS DA SEMANA", f"  {msg}"]
    linhas = ["NOTÍCIAS DA SEMANA  (as histórias que mais veículos distintos deram)"]
    for h in bloco["historias"]:
        linhas.append(f"  {h['veiculos']:>2} veículos | {h['titulo']} ({h['fonte']})")
    if not bloco["historias"]:
        linhas.append("  (nenhuma)")
    c = bloco["contagem"]
    d = c["descartes"]
    linhas.append(
        f"  {c['recebidas']} recebidas, {c['distintas']} distintas, {c['na_semana']} na semana, "
        f"{c['na_imprensa']} na imprensa; descartes: boletim diário {d['boletim_diario']}, "
        f"não é notícia {d['nao_e_noticia']}, fora da imprensa {d['fora_da_imprensa']}, "
        f"fora da semana {d['fora_da_semana']}"
    )
    linhas += [f"  AVISO: {a}" for a in bloco["avisos"]]
    return linhas


def _previa_balancos(balancos_: dict[str, Any]) -> list[str]:
    if (msg := _indisponivel(balancos_)) is not None:
        return [f" Balanços: {msg}"]
    linhas = [" Balanços confirmados (a própria empresa anunciou a data; só quem tem ADR)"]
    linhas += [_linha_balanco_confirmado(b) for b in balancos_["confirmados"]] or ["  (nenhum)"]
    linhas.append(
        " Balanços prováveis (entregaram nesta semana do ano passado; tendência, não data)"
    )
    linhas += [
        f"  {b['empresa']} ({', '.join(b['tickers'])})   {b['documento']} entregue em "
        f"{_data_br(b['entregue_em'])}"
        for b in balancos_["provaveis"]
    ] or ["  (nenhum)"]
    linhas += [f"  AVISO: {a}" for a in balancos_.get("avisos", [])]
    return linhas


def _previa_proxima_semana(bloco: dict[str, Any]) -> list[str]:
    inicio, fim = date.fromisoformat(bloco["inicio"]), date.fromisoformat(bloco["fim"])
    linhas = [f"SEMANA QUE VEM ({inicio.strftime('%d/%m')} a {fim.strftime('%d/%m')})"]
    feriados = ", ".join(_data_br(d) for d in bloco["feriados_b3"]) or "nenhum"
    linhas.append(f"  Feriados B3 (dia útil sem pregão): {feriados}")
    linhas.append(" Agenda (horário de Brasília)")
    linhas += [_linha_evento(e) for e in bloco["agenda"]] or ["  (nenhum evento)"]
    linhas += [f"  AVISO: {a}" for a in bloco["agenda_avisos"]]
    linhas += _previa_balancos(bloco["balancos"])
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
        _previa_noticias(payload["noticias"]),
        _previa_proxima_semana(payload["proxima_semana"]),
    ]
    return "\n\n".join("\n".join(b) for b in blocos)
