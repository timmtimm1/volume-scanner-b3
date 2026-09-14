"use client";

import { useEffect, useState } from "react";
import type { CandleDeHoje } from "./candle-de-hoje";

/**
 * A cada quanto a ficha aberta pergunta de novo. O servidor guarda cada
 * cotacao por 5 minutos, entao perguntar mais vezes so traria a mesma resposta.
 */
const INTERVALO_MS = 5 * 60 * 1000;

/**
 * O candle de agora do papel, buscado depois que a ficha estatica ja abriu.
 *
 * Busca ao abrir, a cada 5 minutos com a tela visivel e sempre que o app volta
 * para a frente -- no celular, e o caso de desbloquear a tela ou voltar do
 * Telegram. Com a tela escondida nao busca nada.
 *
 * Uma resposta vazia nao apaga o candle que ja estava na tela: fornecedor fora
 * do ar nao pode sumir com o dado, e a hora do candle mostra de quando ele e.
 */
export function useCandleDeHoje(ticker: string): CandleDeHoje | null {
  // O ticker vai junto do candle: trocando de papel, o candle do anterior deixa
  // de valer na hora, sem precisar zerar estado dentro do efeito.
  const [estado, setEstado] = useState<{ ticker: string; candle: CandleDeHoje } | null>(
    null,
  );

  useEffect(() => {
    let ativo = true;
    let controle: AbortController | null = null;

    async function buscar() {
      if (document.visibilityState !== "visible") return;
      controle?.abort();
      controle = new AbortController();
      try {
        const r = await fetch(`/api/cotacao/${ticker}/`, { signal: controle.signal });
        if (!r.ok) return;
        const { candle } = (await r.json()) as { candle: CandleDeHoje | null };
        if (ativo && candle) setEstado({ ticker, candle });
      } catch {
        // Rede falhou ou a busca foi cancelada pela seguinte: o grafico oficial
        // continua la, e a proxima passada tenta de novo.
      }
    }

    function aoVoltar() {
      if (document.visibilityState === "visible") void buscar();
    }

    void buscar();
    const relogio = setInterval(buscar, INTERVALO_MS);
    document.addEventListener("visibilitychange", aoVoltar);
    return () => {
      ativo = false;
      controle?.abort();
      clearInterval(relogio);
      document.removeEventListener("visibilitychange", aoVoltar);
    };
  }, [ticker]);

  return estado?.ticker === ticker ? estado.candle : null;
}
