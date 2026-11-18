/**
 * As marcas que o grafico deixa esconder: o candle dourado dos eventos de
 * volume e as setas dos setups. Pedido de 18/11/2026 para a ficha da moeda, onde
 * as duas juntas poluiam o grafico (em media 12 candles dourados e 14 setas por
 * moeda em 260 dias).
 *
 * Modulo puro, testado com `node --experimental-strip-types`; o hook que guarda
 * no navegador fica em `useMarcasDoGrafico.ts`.
 */

export type MarcasDoGrafico = { eventos: boolean; setups: boolean };

export const TUDO_LIGADO: MarcasDoGrafico = { eventos: true, setups: true };

/** O valor guardado, conferido campo a campo; o que nao for booleano fica ligado. */
export function lerMarcas(texto: string | null): MarcasDoGrafico {
  if (!texto) return TUDO_LIGADO;
  let o: unknown;
  try {
    o = JSON.parse(texto);
  } catch {
    return TUDO_LIGADO;
  }
  if (typeof o !== "object" || o === null || Array.isArray(o)) return TUDO_LIGADO;
  const r = o as Record<string, unknown>;
  return {
    eventos: typeof r.eventos === "boolean" ? r.eventos : true,
    setups: typeof r.setups === "boolean" ? r.setups : true,
  };
}
