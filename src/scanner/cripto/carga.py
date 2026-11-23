"""A carga diaria de cripto: atualiza o ranking e baixa os candles que faltam.

E a etapa 1 do `scanner daily` quando o mercado e cripto, no lugar do COTAHIST.
Idempotente como ele: so pede a cada moeda os dias depois da ultima barra que
ela ja tem, e a gravacao sobrescreve.

O ranking (CoinGecko) pode falhar sem derrubar a carga: a API publica limita
requisicoes, e a lista das maiores muda devagar. Sem ela, valem as moedas ja
conhecidas e o relatorio diz que o ranking ficou o de antes. Sem a Binance nao
ha candle, e ai e falha de verdade.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta

import httpx
import pandas as pd
from sqlalchemy import Engine

from scanner import mercado
from scanner.config import CriptoConfig
from scanner.cripto import binance, kraken, universo
from scanner.semana.fontes import TIMEOUT_SEGUNDOS, FonteIndisponivelError
from scanner.storage.repository import gravar_moedas, moedas_para_carregar, upsert_bars


def carregar(
    engine: Engine,
    cfg: CriptoConfig,
    *,
    agora: datetime | None = None,
    cliente: httpx.Client | None = None,
    dormir: Callable[[float], None] = time.sleep,
) -> str:
    """Atualiza ranking e barras; devolve a linha de relatorio da etapa.

    Uma conexao so para a carga inteira: sao umas 55 requisicoes, e abrir uma
    por requisicao custava de 5 a 10 segundos cada (resolucao de nome) na
    medicao de 16/11/2026 -- 8 minutos de carga contra 20 segundos.
    """
    if cliente is None:
        with httpx.Client(timeout=TIMEOUT_SEGUNDOS) as proprio:
            return carregar(engine, cfg, agora=agora, cliente=proprio, dormir=dormir)
    ontem = binance.ultimo_dia_fechado(agora)
    pares = binance.buscar_pares(cliente=cliente)
    fora = mercado.MOEDAS_FORA_DA_BINANCE

    try:
        maiores = universo.buscar_maiores(
            pares,
            top=cfg.top,
            categorias_excluidas=cfg.categorias_excluidas,
            extras=fora,
            cliente=cliente,
            dormir=dormir,
        )
        gravar_moedas(engine, maiores)
        ranking = f"ranking: {len(maiores)} moedas"
    except FonteIndisponivelError as exc:
        ranking = f"ranking nao atualizado ({exc}); valem as moedas de antes"

    moedas = moedas_para_carregar(engine)
    if moedas.empty:
        raise FonteIndisponivelError(
            "coingecko", "sem ranking e sem moeda nenhuma no banco: nada para carregar"
        )

    partes: list[pd.DataFrame] = []
    paradas: list[str] = []
    for linha in moedas.to_dict("records"):
        ticker, par, ultima = str(linha["ticker"]), str(linha["par"]), linha["ultima"]
        if ticker not in pares and ticker not in fora:
            # Par suspenso ou deslistado: as barras antigas ficam, as novas nao vem.
            paradas.append(ticker)
            continue
        if pd.isna(ultima):
            desde = ontem - timedelta(days=cfg.dias_iniciais)
        else:
            desde = pd.Timestamp(ultima).date() + timedelta(days=1)
        if desde > ontem:
            continue
        if ticker in fora:
            # A Kraken fora do ar nao pode derrubar a carga das outras 50.
            try:
                partes.append(
                    kraken.buscar_barras(ticker, fora[ticker], desde, agora=agora, cliente=cliente)
                )
            except FonteIndisponivelError:
                paradas.append(ticker)
            continue
        partes.append(
            binance.buscar_barras(ticker, par, desde, agora=agora, cliente=cliente, dormir=dormir)
        )
        dormir(binance.PAUSA)

    cheias = [p for p in partes if not p.empty]
    gravadas = upsert_bars(engine, pd.concat(cheias, ignore_index=True)) if cheias else 0
    texto = (
        f"Binance ate {ontem.isoformat()}: {gravadas:,} barras de {len(cheias)} moedas; {ranking}"
    )
    if paradas:
        texto += f"; sem negociacao: {', '.join(sorted(paradas))}"
    return texto
