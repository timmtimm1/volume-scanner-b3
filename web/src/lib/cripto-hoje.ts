/**
 * O dia de hoje das criptos, para a aba Cripto mostrar dado de agora.
 *
 * O banco tem so candles fechados (o pipeline roda as 21h). Ao abrir a aba ou
 * a ficha, o servidor pergunta a Binance o dia UTC em andamento
 * (`cripto-hoje-binance.ts`) e as contas abaixo decidem o que mostrar.
 *
 * So contas, sem rede e sem import de valor: os testes rodam este arquivo no Node.
 */

import type { Barra } from "./types";

/** O dia UTC em andamento de uma moeda, segundo a Binance. */
export type DiaDeHoje = {
  moeda: string;
  /** AAAA-MM-DD, o dia UTC (o candle diario vai das 21h as 21h de Brasilia). */
  dia: string;
  abertura: number;
  maxima: number;
  minima: number;
  ultimo: number;
  /** Volume do dia em dolar. */
  volume: number;
  /** Quando a Binance respondeu, ISO em UTC. */
  hora: string;
};

/**
 * O dia UTC em andamento na resposta do `Ticker` da Kraken. Nos campos em lista,
 * a posicao 0 e "hoje", desde a meia-noite UTC: o mesmo dia do candle diario.
 */
export function lerTickerDaKraken(dados: unknown, moeda: string, agora: string): DiaDeHoje | null {
  const corpo = dados as { error?: unknown[]; result?: Record<string, unknown> } | null;
  if (!corpo || (corpo.error?.length ?? 0) > 0 || !corpo.result) return null;
  const linhas = Object.values(corpo.result);
  if (linhas.length !== 1) return null;
  const r = linhas[0] as Record<string, unknown>;
  const zero = (campo: string) => Number((r[campo] as unknown[] | undefined)?.[0]);
  const dia = {
    moeda,
    dia: agora.slice(0, 10),
    abertura: Number(r.o),
    maxima: zero("h"),
    minima: zero("l"),
    ultimo: zero("c"),
    volume: zero("v") * zero("p"),
    hora: agora,
  };
  return [dia.abertura, dia.maxima, dia.minima, dia.ultimo].every((v) => Number.isFinite(v) && v > 0)
    ? dia
    : null;
}

/** O dia seguinte a `dia` (AAAA-MM-DD), em UTC. */
export function diaSeguinte(dia: string): string {
  const d = new Date(`${dia}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

export type SituacaoDeHoje =
  | { passou: true; maxima: number; ultimo: number; hora: string }
  | { passou: false; maxima: number; ultimo: number; hora: string; falta: number };

/**
 * A entrada armada no candle de `tradeDate` ja passou do preco de compra hoje?
 *
 * Vale so no dia da confirmacao, o seguinte ao candle. Entre as 21h e a hora
 * em que o pipeline roda, a lista ainda e a de ontem e "hoje" ja e outro dia:
 * comparar a maxima do dia novo com o gatilho de anteontem estaria errado, e
 * entao nao se mostra nada.
 */
export function situacaoDaEntrada(
  gatilho: number,
  tradeDate: string,
  hoje: DiaDeHoje | undefined,
): SituacaoDeHoje | null {
  if (!hoje || hoje.dia !== diaSeguinte(tradeDate)) return null;
  if (!(gatilho > 0) || !(hoje.maxima > 0) || !(hoje.ultimo > 0)) return null;
  if (hoje.maxima >= gatilho) {
    return { passou: true, maxima: hoje.maxima, ultimo: hoje.ultimo, hora: hoje.hora };
  }
  return {
    passou: false,
    maxima: hoje.maxima,
    ultimo: hoje.ultimo,
    hora: hoje.hora,
    falta: gatilho / hoje.ultimo - 1,
  };
}

/**
 * As barras do banco com o candle de hoje no fim, se ele ainda nao esta la.
 *
 * Entra como mais um candle: cripto negocia todo dia, entao nao ha a regra de
 * fim de semana e feriado do candle parcial das acoes (`candle-de-hoje.ts`).
 */
export function comCandleDeHoje(barras: Barra[], hoje: DiaDeHoje | undefined): Barra[] {
  if (!hoje) return barras;
  const ultima = barras.at(-1);
  if (ultima && hoje.dia <= ultima.tradeDate) return barras;
  return [
    ...barras,
    {
      tradeDate: hoje.dia,
      open: hoje.abertura,
      high: hoje.maxima,
      low: hoje.minima,
      close: hoje.ultimo,
      volumeFinancial: hoje.volume,
    },
  ];
}

/** "14:32" no horario de Brasilia, de uma hora ISO. */
export function horaEmBrasilia(iso: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Sao_Paulo",
  }).format(new Date(iso));
}
