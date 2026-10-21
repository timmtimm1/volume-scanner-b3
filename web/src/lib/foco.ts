/**
 * Onde o grafico da ficha abre.
 *
 * `?data=` escolhe o evento de volume da ficha (e o grafico centra nele).
 * `?foco=` centra o grafico num pregao qualquer sem mudar o evento -- e o que
 * os links dos Setups usam: o candle do setup quase nunca e evento, e com
 * `?data=` a ficha caia no evento mais recente, as vezes meses antes.
 *
 * Com foco, o grafico mostra mais pregoes depois do dia: o setup em andamento
 * pode ter ate 20 pregoes de historia depois do candle.
 */

export const DEPOIS_DO_EVENTO = 14;
export const DEPOIS_DO_FOCO = 25;

export function focoDoGrafico(
  foco: string | null,
  datas: string[],
  evento: string | undefined,
): { dia: string | undefined; depois: number } {
  if (foco !== null && datas.includes(foco)) return { dia: foco, depois: DEPOIS_DO_FOCO };
  return { dia: evento, depois: DEPOIS_DO_EVENTO };
}
