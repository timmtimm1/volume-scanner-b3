"use client";

import { useEffect, useState } from "react";
import type { Barra } from "./types";

export type BarrasDoPapel = {
  barras: Barra[];
  /** So a data: e o que o grafico usa para dourar o candle do evento. */
  eventos: { tradeDate: string }[];
};

/**
 * Um pedido por papel enquanto a pagina estiver aberta. Voltar a um papel ja
 * visto, ou chegar a um que foi buscado antes (os vizinhos da previa sao
 * pedidos adiantado), e instantaneo.
 */
const pedidos = new Map<string, Promise<BarrasDoPapel>>();

export function carregarBarras(ticker: string): Promise<BarrasDoPapel> {
  let pedido = pedidos.get(ticker);
  if (!pedido) {
    pedido = fetch(`/api/barras/${ticker}/`).then((r) => {
      if (!r.ok) throw new Error(`barras de ${ticker}: ${r.status}`);
      return r.json() as Promise<BarrasDoPapel>;
    });
    // Falhou, sai do cache: o proximo clique tenta de novo.
    pedido.catch(() => pedidos.delete(ticker));
    pedidos.set(ticker, pedido);
  }
  return pedido;
}

type Estado =
  | { ticker: string; dados: BarrasDoPapel; erro: false }
  | { ticker: string; dados: null; erro: true };

/**
 * As barras do papel da previa. `null` enquanto carrega -- inclusive no
 * instante em que o papel troca, para o grafico nunca mostrar as barras de um
 * papel com o nome de outro.
 */
export function useBarrasDoPapel(ticker: string): { dados: BarrasDoPapel | null; erro: boolean } {
  const [estado, setEstado] = useState<Estado | null>(null);

  useEffect(() => {
    let valendo = true;
    carregarBarras(ticker).then(
      (dados) => valendo && setEstado({ ticker, dados, erro: false }),
      () => valendo && setEstado({ ticker, dados: null, erro: true }),
    );
    return () => {
      valendo = false;
    };
  }, [ticker]);

  if (!estado || estado.ticker !== ticker) return { dados: null, erro: false };
  return { dados: estado.dados, erro: estado.erro };
}
