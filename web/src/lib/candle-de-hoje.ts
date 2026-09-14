/**
 * O candle do pregao em andamento, montado a partir da cotacao de agora.
 *
 * O grafico da ficha vem do COTAHIST, que so traz o pregao depois que ele
 * fecha. Este candle cobre a distancia entre o ultimo pregao oficial e o
 * momento da cotacao. E so leitura: nao entra no z-score, no alerta de volume
 * nem nas bandas, e some sozinho quando o COTAHIST daquele dia chega.
 *
 * Modulo sem dependencia de servidor nem de navegador, usado pelos dois lados:
 * a rota monta o candle, a ficha decide se desenha.
 */

import type { Barra } from "./types";

export type Fonte = "brapi" | "yahoo";

export type CandleDeHoje = {
  ticker: string;
  /** Pregao da cotacao, AAAA-MM-DD no fuso da B3. */
  dia: string;
  open: number;
  high: number;
  low: number;
  close: number;
  /** Acoes negociadas ate a hora da cotacao. Os fornecedores nao dao o financeiro. */
  volumeAcoes: number | null;
  /** Hora da cotacao segundo o fornecedor, ISO em UTC. Nenhum dos dois e tempo real. */
  hora: string;
  fonte: Fonte;
};

// "en-CA" porque formata como AAAA-MM-DD, o mesmo formato de `Barra.tradeDate`.
const DIA_NA_B3 = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/Sao_Paulo",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const HORA_NA_B3 = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  hour: "2-digit",
  minute: "2-digit",
});

/** O dia em Sao Paulo, e nao o do servidor (UTC) nem o do celular. */
export function diaNaB3(instante: Date): string {
  return DIA_NA_B3.format(instante);
}

/** HH:MM em Sao Paulo. */
export function horaNaB3(iso: string): string {
  return HORA_NA_B3.format(new Date(iso));
}

/**
 * Preco positivo com duas casas, a precisao da B3. O Yahoo manda a abertura
 * como float cru (13.15999984741211), e o candle nao deve carregar esse ruido.
 */
function positivo(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) && n > 0 ? Math.round(n * 100) / 100 : null;
}

export type CamposDaCotacao = {
  preco: unknown;
  abertura: unknown;
  maxima: unknown;
  minima: unknown;
  volume: unknown;
  hora: Date | null;
};

/**
 * Candle a partir dos campos que brapi e Yahoo tem em comum.
 *
 * Sem preco ou sem hora nao ha candle: sem a hora nao da para saber de que
 * pregao e o preco. Abertura, maxima e minima que faltem caem no preco, e a
 * maxima e a minima sao alargadas para conter abertura e fechamento -- um
 * fornecedor atrasado pode trazer um preco novo com a maxima de minutos antes.
 */
export function montarCandle(
  ticker: string,
  fonte: Fonte,
  campos: CamposDaCotacao,
): CandleDeHoje | null {
  const close = positivo(campos.preco);
  const hora = campos.hora;
  if (close === null || hora === null || Number.isNaN(hora.getTime())) return null;

  const open = positivo(campos.abertura) ?? close;
  const high = Math.max(positivo(campos.maxima) ?? close, open, close);
  const low = Math.min(positivo(campos.minima) ?? close, open, close);
  const volume = Number(campos.volume);

  return {
    ticker,
    dia: diaNaB3(hora),
    open,
    high,
    low,
    close,
    volumeAcoes:
      campos.volume !== null && Number.isFinite(volume) && volume >= 0 ? volume : null,
    hora: hora.toISOString(),
    fonte,
  };
}

/**
 * Das duas cotacoes, a de hora mais nova. Empate fica com a primeira.
 *
 * As horas saem de `toISOString`, entao comparar o texto e comparar o instante.
 */
export function maisRecente(
  primeira: CandleDeHoje | null,
  segunda: CandleDeHoje | null,
): CandleDeHoje | null {
  if (!primeira) return segunda;
  if (!segunda) return primeira;
  return segunda.hora > primeira.hora ? segunda : primeira;
}

/**
 * O candle so e desenhado se for de um pregao que o COTAHIST ainda nao trouxe.
 *
 * Antes da abertura, no fim de semana ou num feriado, a "ultima cotacao" e de
 * um pregao que ja esta no grafico com o dado oficial -- e ele vence.
 */
export function candleParcial(
  barras: Barra[],
  candle: CandleDeHoje | null,
): CandleDeHoje | null {
  if (!candle) return null;
  const ultimo = barras.at(-1)?.tradeDate;
  return ultimo === undefined || candle.dia > ultimo ? candle : null;
}
