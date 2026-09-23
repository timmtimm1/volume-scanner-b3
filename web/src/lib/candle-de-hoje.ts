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

/** Duas casas, a precisao da B3 -- a mesma que `montarCandle` da ao candle. */
function duasCasas(v: number | null): number | null {
  return v === null ? null : Math.round(v * 100) / 100;
}

/**
 * Se o "parcial" e, campo a campo, a barra que ja esta no grafico.
 *
 * Pregao em andamento nao reproduz a abertura, a maxima, a minima E o
 * fechamento do pregao anterior ao centavo. Quando os quatro batem, o que
 * chegou nao e um parcial: e o dia anterior servido de novo.
 *
 * `open`, `high` e `low` da barra podem ser nulos (papel com um negocio so no
 * dia). Nulo nunca e igual a um preco, entao a comparacao falha e o candle
 * passa -- na duvida, desenhar e melhor que esconder dado real.
 */
function ehCopiaDa(candle: CandleDeHoje, barra: Barra): boolean {
  return (
    duasCasas(barra.open) === candle.open &&
    duasCasas(barra.high) === candle.high &&
    duasCasas(barra.low) === candle.low &&
    duasCasas(barra.close) === candle.close
  );
}

/** Sabado ou domingo. Sem lista de feriados: ver `candleParcial`. */
function ehFimDeSemana(dia: string): boolean {
  const [ano, mes, d] = dia.split("-").map(Number);
  const semana = new Date(ano, mes - 1, d).getDay();
  return semana === 0 || semana === 6;
}

/**
 * O candle so e desenhado se for mesmo um pregao em andamento.
 *
 * Tres condicoes, e cada uma existe por um motivo diferente:
 *
 * 1. **Depois do ultimo pregao que o COTAHIST trouxe.** Se o dia oficial ja
 *    esta no grafico, o dado oficial vence.
 * 2. **Num dia que pode ser pregao.** Sabado e domingo saem por aritmetica de
 *    data. Feriado NAO tem lista aqui de proposito: o calendario da B3 mora em
 *    `scanner/calendar.py`, e uma segunda copia no TypeScript seria uma segunda
 *    verdade que um dia diverge. Feriado cai na condicao 3, que e mais geral.
 * 3. **Diferente da ultima barra fechada.** E a guarda que pega o resto: antes
 *    da abertura, no feriado, e no papel de giro menor cuja cotacao ainda nao
 *    andou hoje.
 *
 * A condicao 3 nasceu em 23/09/2026. A brapi carimba a cotacao com a hora da
 * RESPOSTA, nao com a do negocio, e naquela manha devolveu para VIVA3 o pregao
 * fechado de 22/09 inteiro -- 23,76 / 23,79 / 22,12 / 22,78 -- dizendo que era
 * de 23/09 as 10:19. A ficha desenhava isso como o candle de hoje: uma copia
 * exata do candle anterior, ao lado dele.
 *
 * A raiz disso foi corrigida em `cotacao.ts` (a brapi virou reserva), mas a
 * guarda fica: ela nao depende de qual fornecedor respondeu nem de a hora ser
 * honesta, e e o grafico que o usuario le para decidir.
 */
export function candleParcial(
  barras: Barra[],
  candle: CandleDeHoje | null,
): CandleDeHoje | null {
  if (!candle) return null;
  if (ehFimDeSemana(candle.dia)) return null;

  const ultima = barras.at(-1);
  if (ultima === undefined) return candle;
  if (candle.dia <= ultima.tradeDate) return null;
  if (ehCopiaDa(candle, ultima)) return null;
  return candle;
}
