"use client";

import { useEffect, useMemo, useState } from "react";
// So tipos: um `import` de valor de "./setups" puxaria `pg` para o navegador.
import { PADROES_DOS_SETUPS } from "./config";
import {
  ehClassico,
  LETRA_DO_PADRAO,
  linhasDoSetup,
  NOME_DO_SETUP,
  type Preferencias,
  type Setup,
} from "./setups-tela";
import type { LinhaDeSetup, MarcaDeSetup } from "./types";

type Corpo = { setups: Setup[]; preferencias?: Preferencias };

export type SetupsDoPapel = {
  /** As setas, so dos setups com alerta ligado. */
  marcas: MarcaDeSetup[];
  /** Entrada, stop e alvo do setup em aberto (o mais recente). */
  linhas: LinhaDeSetup[];
};

const VAZIO: SetupsDoPapel = { marcas: [], linhas: [] };

/**
 * As setas e as linhas de preco dos setups deste papel no grafico da ficha.
 *
 * Mesma regra dos trades: so busca `/api/setups/?ticker=` quando `autenticado`
 * -- que `useAlertasDoPapel` ja descobre na ficha -- vira `true`. Visitante
 * nao gera o pedido e nao ve seta nenhuma; as linhas de suporte e resistencia,
 * que sao so leitura do grafico, aparecem para todos.
 *
 * So os setups com alerta ligado (aba Setups) aparecem: os outros ficariam
 * dezenas por papel e escondiam o candle.
 */
export function useSetupsDoPapel(ticker: string, autenticado: boolean | null): SetupsDoPapel {
  const [corpo, setCorpo] = useState<Corpo | null>(null);

  useEffect(() => {
    if (autenticado !== true) return;
    let cancelado = false;
    fetch(`/api/setups/?ticker=${ticker}`)
      .then(async (r) => {
        if (cancelado || !r.ok) return;
        const c = (await r.json()) as Corpo;
        if (!cancelado) setCorpo(c);
      })
      .catch(() => {
        // Sem rede: o grafico fica sem as setas, como para o visitante.
      });
    return () => {
      cancelado = true;
    };
  }, [ticker, autenticado]);

  return useMemo(() => {
    if (corpo === null) return VAZIO;
    const prefs = corpo.preferencias ?? PADROES_DOS_SETUPS;
    return {
      marcas: corpo.setups.filter((s) => prefs[s.categoria].alerta).map(paraMarca),
      linhas: linhasDoSetup(corpo.setups, prefs),
    };
  }, [corpo]);
}

export function paraMarca(
  s: Pick<Setup, "tradeDate" | "padroes" | "destaque" | "categoria" | "suporteTipo">,
): MarcaDeSetup {
  const classico = ehClassico(s.categoria);
  return {
    data: s.tradeDate,
    letras: classico
      ? NOME_DO_SETUP[s.categoria]
      : s.padroes.map((p) => LETRA_DO_PADRAO[p] ?? "?").join(""),
    destaque: s.destaque,
    forca: s.categoria === "forca",
    classico,
    suporte: s.suporteTipo,
  };
}
