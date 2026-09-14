/**
 * Indicadores de leitura do grafico.
 *
 * Nao decidem nada e nao entram na regra de alerta -- servem para o olho, que e
 * quem interpreta o evento. A regra continua sendo o z-score de volume.
 */

import type { Barra } from "./types";

export type BandaBollinger = {
  tradeDate: string;
  media: number;
  superior: number;
  inferior: number;
  /** Largura relativa da banda. Banda abrindo = volatilidade expandindo. */
  largura: number;
};

/**
 * Bandas de Bollinger sobre o fechamento.
 *
 * Media movel simples de `periodo` pregoes, com bandas a `desvios` desvios
 * padrao. Diferente do baseline do z-score da secao 1 do plano, aqui a janela
 * INCLUI o dia corrente: a banda e uma leitura do proprio dia contra a
 * volatilidade recente, nao um teste em que o dia precisa ficar de fora.
 *
 * O desvio usa divisor `n` (populacional), como faz a formula classica de
 * Bollinger e como fazem as plataformas de grafico -- nao `n-1`.
 */
export function bollinger(
  barras: Barra[],
  periodo = 20,
  desvios = 2,
): BandaBollinger[] {
  if (periodo < 2) throw new Error("periodo minimo e 2");

  const saida: BandaBollinger[] = [];
  for (let i = periodo - 1; i < barras.length; i++) {
    const janela = barras.slice(i - periodo + 1, i + 1).map((b) => b.close);
    const media = janela.reduce((a, b) => a + b, 0) / periodo;
    const variancia =
      janela.reduce((acc, v) => acc + (v - media) ** 2, 0) / periodo;
    const dp = Math.sqrt(variancia);

    saida.push({
      tradeDate: barras[i].tradeDate,
      media,
      superior: media + desvios * dp,
      inferior: media - desvios * dp,
      largura: media > 0 ? (2 * desvios * dp) / media : 0,
    });
  }
  return saida;
}

/**
 * Quanto a banda abriu contra a propria media recente.
 *
 * Acima de 1 significa banda mais larga que o normal do papel -- o "abrindo"
 * que se ve no grafico, em numero.
 */
export function aberturaDaBanda(
  bandas: BandaBollinger[],
  referencia = 60,
): number | null {
  if (!bandas.length) return null;
  const atual = bandas[bandas.length - 1].largura;
  const janela = bandas.slice(-referencia);
  if (janela.length < 5) return null;

  const media = janela.reduce((a, b) => a + b.largura, 0) / janela.length;
  return media > 0 ? atual / media : null;
}

export type TipoDeMedia = "MMA" | "MME";

export type PontoDaMedia = { tradeDate: string; valor: number };

/**
 * Media movel aritmetica (MMA) do fechamento: a media simples dos ultimos
 * `periodo` pregoes, incluindo o dia.
 *
 * O primeiro ponto so existe quando ha `periodo` fechamentos. Antes disso nao
 * ha media -- desenhar uma media de menos dias seria outra linha com o mesmo
 * nome.
 */
export function mediaMovelAritmetica(barras: Barra[], periodo: number): PontoDaMedia[] {
  if (!Number.isInteger(periodo) || periodo < 2) throw new Error("periodo minimo e 2");
  const saida: PontoDaMedia[] = [];
  let soma = 0;
  for (let i = 0; i < barras.length; i++) {
    soma += barras[i].close;
    if (i >= periodo) soma -= barras[i - periodo].close;
    if (i >= periodo - 1) saida.push({ tradeDate: barras[i].tradeDate, valor: soma / periodo });
  }
  return saida;
}

/**
 * Media movel exponencial (MME) do fechamento, com fator 2/(periodo+1).
 *
 * A semente e a MMA dos `periodo` primeiros fechamentos -- a convencao das
 * plataformas de grafico. Comecar do primeiro fechamento puro faria a linha
 * depender de quantos pregoes vieram antes, e duas telas com janelas diferentes
 * mostrariam MMEs diferentes para o mesmo dia.
 */
export function mediaMovelExponencial(barras: Barra[], periodo: number): PontoDaMedia[] {
  if (!Number.isInteger(periodo) || periodo < 2) throw new Error("periodo minimo e 2");
  if (barras.length < periodo) return [];
  const k = 2 / (periodo + 1);
  let valor = barras.slice(0, periodo).reduce((a, b) => a + b.close, 0) / periodo;
  const saida: PontoDaMedia[] = [{ tradeDate: barras[periodo - 1].tradeDate, valor }];
  for (let i = periodo; i < barras.length; i++) {
    valor = barras[i].close * k + valor * (1 - k);
    saida.push({ tradeDate: barras[i].tradeDate, valor });
  }
  return saida;
}

export function mediaMovel(barras: Barra[], tipo: TipoDeMedia, periodo: number): PontoDaMedia[] {
  return tipo === "MMA"
    ? mediaMovelAritmetica(barras, periodo)
    : mediaMovelExponencial(barras, periodo);
}
