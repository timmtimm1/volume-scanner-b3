/**
 * O nivel de um alerta criado ou arrastado no grafico: o preco arredondado ao
 * centavo e a direcao tirada do preco de agora.
 *
 * Modulo puro (so `import type`), testado com `node --experimental-strip-types`
 * -- mesmo padrao de `regua.ts`.
 */

import type { Direcao } from "./alertas";

/**
 * O centavo e o passo de preco na B3: o nivel salvo nunca tem mais casas.
 *
 * O `toPrecision` tira o ruido do ponto flutuante antes de arredondar: 32,495
 * vezes 100 da 3249,4999999999995, e o `Math.round` direto devolveria 32,49.
 */
export function nivelEmCentavos(preco: number): number {
  return Math.round(Number((preco * 100).toPrecision(12))) / 100;
}

/**
 * Acima do preco de agora o alerta vigia a subida; abaixo, a queda.
 *
 * E a mesma regra do clique no grafico do celular: um nivel igual ao preco
 * conta como "acima". Sem preco de referencia (papel sem barra nenhuma), a
 * direcao que o alerta ja tinha continua valendo.
 */
export function direcaoDoNivel(
  nivel: number,
  referencia: number | null,
  atual: Direcao = "acima",
): Direcao {
  if (referencia === null || !Number.isFinite(referencia)) return atual;
  return nivel >= referencia ? "acima" : "abaixo";
}

/**
 * O nivel digitado na lista de alertas, ou null se nao for um preco.
 *
 * Aceita virgula ou ponto como separador decimal e ignora o "R$" e os espacos
 * que vierem colados. Milhar nao e aceito: "1.234,50" e ambiguo, e acao na B3
 * que custa mais de mil reais por papel e excecao.
 */
export function lerNivelDigitado(texto: string): number | null {
  const limpo = texto.replace(/R\$/i, "").replace(/\s/g, "").replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(limpo)) return null;
  const valor = nivelEmCentavos(Number(limpo));
  return valor > 0 ? valor : null;
}
