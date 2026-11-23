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

/** O ponto de partida da aba Cripto (23/11/2026): as setas so aparecem se a pessoa ligar. */
export const SEM_SETAS: MarcasDoGrafico = { eventos: true, setups: false };

/** O valor guardado, conferido campo a campo; o que nao for booleano fica no `padrao`. */
export function lerMarcas(
  texto: string | null,
  padrao: MarcasDoGrafico = TUDO_LIGADO,
): MarcasDoGrafico {
  if (!texto) return padrao;
  let o: unknown;
  try {
    o = JSON.parse(texto);
  } catch {
    return padrao;
  }
  if (typeof o !== "object" || o === null || Array.isArray(o)) return padrao;
  const r = o as Record<string, unknown>;
  return {
    eventos: typeof r.eventos === "boolean" ? r.eventos : padrao.eventos,
    setups: typeof r.setups === "boolean" ? r.setups : padrao.setups,
  };
}
