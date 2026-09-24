"use client";

import { useEffect, useState } from "react";
import type { ResultadoDasNoticias } from "./noticias";

export type EstadoDasNoticias = {
  carregando: boolean;
  resultado: ResultadoDasNoticias | null;
  falhou: boolean;
};

/**
 * As manchetes do papel, buscadas uma vez quando a ficha abre.
 *
 * Sem intervalo, ao contrario do candle: o servidor guarda cada busca por 30
 * minutos, e ninguem fica com a ficha aberta esperando noticia chegar.
 */
export function useNoticias(ticker: string): EstadoDasNoticias {
  // O ticker vai junto: trocando de papel, as noticias do anterior deixam de
  // valer na hora, sem zerar estado dentro do efeito.
  const [estado, setEstado] = useState<{
    ticker: string;
    resultado: ResultadoDasNoticias | null;
    falhou: boolean;
  } | null>(null);

  useEffect(() => {
    const controle = new AbortController();
    (async () => {
      try {
        const r = await fetch(`/api/noticias/${ticker}/`, { signal: controle.signal });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const { resultado } = (await r.json()) as { resultado: ResultadoDasNoticias | null };
        setEstado({ ticker, resultado, falhou: resultado === null });
      } catch {
        if (!controle.signal.aborted) setEstado({ ticker, resultado: null, falhou: true });
      }
    })();
    return () => controle.abort();
  }, [ticker]);

  if (estado?.ticker !== ticker) return { carregando: true, resultado: null, falhou: false };
  return { carregando: false, resultado: estado.resultado, falhou: estado.falhou };
}
