"use client";

import { useEffect, useState } from "react";
// So tipos: um `import` de valor de "./setups" puxaria `pg` para o navegador.
import { LETRA_DO_PADRAO, type Setup } from "./setups-tela";
import type { MarcaDeSetup } from "./types";

/**
 * As setas dos setups deste papel no grafico da ficha.
 *
 * Mesma regra dos trades: so busca `/api/setups/?ticker=` quando `autenticado`
 * -- que `useAlertasDoPapel` ja descobre na ficha -- vira `true`. Visitante
 * nao gera o pedido e nao ve seta nenhuma; as linhas de suporte e resistencia,
 * que sao so leitura do grafico, aparecem para todos.
 */
export function useSetupsDoPapel(ticker: string, autenticado: boolean | null): MarcaDeSetup[] {
  const [marcas, setMarcas] = useState<MarcaDeSetup[]>([]);

  useEffect(() => {
    if (autenticado !== true) return;
    let cancelado = false;
    fetch(`/api/setups/?ticker=${ticker}`)
      .then(async (r) => {
        if (cancelado || !r.ok) return;
        const corpo = (await r.json()) as { setups: Setup[] };
        if (!cancelado) setMarcas(corpo.setups.map(paraMarca));
      })
      .catch(() => {
        // Sem rede: o grafico fica sem as setas, como para o visitante.
      });
    return () => {
      cancelado = true;
    };
  }, [ticker, autenticado]);

  return marcas;
}

export function paraMarca(
  s: Pick<Setup, "tradeDate" | "padroes" | "destaque" | "categoria" | "suporteTipo">,
): MarcaDeSetup {
  return {
    data: s.tradeDate,
    letras: s.padroes.map((p) => LETRA_DO_PADRAO[p] ?? "?").join(""),
    destaque: s.destaque,
    forca: s.categoria === "forca",
    suporte: s.suporteTipo,
  };
}
