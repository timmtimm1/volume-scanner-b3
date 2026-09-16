"use client";

import { useEffect, useState } from "react";
import type { TipoDeOperacao } from "./posicao";
// So o tipo: um `import` de valor de "./trades" puxaria `pg` para o navegador
// (o modulo importa `db.ts`, que abre o Pool do Postgres).
import type { TradeResumo } from "./trades";

export type EntradaDeRegistro = {
  tipo: TipoDeOperacao;
  data: string;
  quantidade: number;
  preco: number;
};

/**
 * Os trades deste papel: a mesma ideia de `useAlertasDoPapel`, para trades
 * reais em vez de alertas de preco.
 *
 * So busca `/api/trades/?ticker=` quando `autenticado` -- que `useAlertasDoPapel`
 * ja descobre na ficha -- vira `true`. Um visitante deslogado nunca gera esse
 * pedido, e trade real e dado pessoal como o alerta.
 *
 * `iniciais` existe so para a previa de desenvolvimento (`/previa-trades`),
 * onde nao ha sessao de verdade para a busca completar: sem ela a tela abriria
 * vazia. Nas paginas reais ninguem passa esse argumento.
 */
export function useTradesDoPapel(
  ticker: string,
  autenticado: boolean | null,
  iniciais: TradeResumo[] = [],
) {
  const [trades, setTrades] = useState<TradeResumo[]>(iniciais);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  /**
   * Busca ao abrir a ficha (quando ja autenticado) ou assim que o login
   * resolve. O `cancelado` descarta a resposta que chega tarde ao trocar de
   * papel depressa -- mesma cautela de `useAlertasDoPapel`.
   */
  useEffect(() => {
    if (autenticado !== true) return;
    let cancelado = false;
    fetch(`/api/trades/?ticker=${ticker}`)
      .then(async (r) => {
        if (cancelado || !r.ok) return;
        const corpo = (await r.json()) as { trades: TradeResumo[] };
        if (!cancelado) setTrades(corpo.trades);
      })
      .catch(() => {
        // Falha de rede: fica com o que ja tinha na tela, igual ao candle de hoje.
      });
    return () => {
      cancelado = true;
    };
  }, [ticker, autenticado]);

  /** Para recarregar sob demanda -- por exemplo, depois de um erro. */
  async function recarregar(): Promise<void> {
    try {
      const r = await fetch(`/api/trades/?ticker=${ticker}`);
      if (!r.ok) return;
      const corpo = (await r.json()) as { trades: TradeResumo[] };
      setTrades(corpo.trades);
    } catch {
      // Falha de rede: fica com o que ja tinha na tela.
    }
  }

  async function registrar(entrada: EntradaDeRegistro): Promise<TradeResumo> {
    setSalvando(true);
    setErro(null);
    try {
      const r = await fetch("/api/trades/operacoes/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, ...entrada }),
      });
      const corpo = (await r.json().catch(() => null)) as
        | { trade?: TradeResumo; erro?: string }
        | null;
      if (!r.ok || !corpo?.trade) {
        throw new Error(corpo?.erro ?? "não foi possível salvar");
      }
      const trade = corpo.trade;
      setTrades((atual) =>
        atual.some((t) => t.id === trade.id)
          ? atual.map((t) => (t.id === trade.id ? trade : t))
          : [trade, ...atual],
      );
      return trade;
    } catch (e) {
      const mensagem = e instanceof Error ? e.message : "algo deu errado";
      setErro(mensagem);
      throw e;
    } finally {
      setSalvando(false);
    }
  }

  return {
    trades,
    tradeAberto: trades.find((t) => t.encerradoEm === null) ?? null,
    autenticado,
    salvando,
    erro,
    registrar,
    recarregar,
  };
}

export type EstadoDosTrades = ReturnType<typeof useTradesDoPapel>;
