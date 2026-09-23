/**
 * O que cada evento leva para o navegador na Tela 3.
 *
 * A tabela mostra 100 linhas por vez, mas o dado dos 1.000 eventos viaja
 * inteiro: os filtros de papel, periodo e faixa de z valem sobre todos, e isso
 * e proposital. O que NAO precisa viajar e a precisao que nenhuma celula
 * mostra.
 *
 * Tres campos saem de `daily_features`, que guarda o contexto num JSONB de
 * float64. Eles chegam aqui com a representacao inteira do double -- um
 * `zExcess` de 4.348801362190244 ocupa 18 caracteres para ser exibido como
 * "4,35". Os outros tres numeros (`zLog`, `rvol` e `volumeFinancial`) vem de
 * colunas `NUMERIC` e ja chegam quantizados pelo banco; arredondar nao mudaria
 * um byte, entao nao sao tocados.
 *
 * `zLog` em especial fica intacto de proposito. Ele e comparado com o limiar de
 * 6 sigma em dois lugares da tabela (a cor da linha e o contador do cabecalho),
 * e arredondar para as 2 casas que a tela mostra faria um 5,996 virar 6,00 --
 * um evento que o Telegram nao notificou apareceria como se tivesse cruzado.
 *
 * Medido sobre o payload real de 1.000 eventos: 216,2 KB -> 179,6 KB cru,
 * 59,1 KB -> 37,6 KB comprimido (-36%).
 */

import type { Evento, LinhaDoHistorico } from "./types";

/** Arredonda preservando o nulo: campo ausente continua ausente, nunca vira 0. */
export function casas(v: number | null, n: number): number | null {
  if (v === null || !Number.isFinite(v)) return v;
  const fator = 10 ** n;
  return Math.round(v * fator) / fator;
}

/**
 * Quantas casas cada campo leva, e por que.
 *
 * A regra e sempre a mesma: o dobro do que a celula mostra, para nenhuma
 * diferenca de arredondamento aparecer na tela.
 */
const CASAS = {
  /** `percentual()` mostra 1 casa do percentual = 3 casas da fracao. */
  retDay: 4,
  /** `numero()` mostra 2 casas. */
  zExcess: 4,
} as const;

/**
 * O evento reduzido ao que a tabela do historico usa.
 *
 * So os campos que a tela le: o `Evento` inteiro tem o dobro deles, e a pagina
 * chegava a 689 KB com 400 eventos.
 */
export function linhaDoHistorico(e: Evento): LinhaDoHistorico {
  return {
    ticker: e.ticker,
    empresa: e.empresa,
    tradeDate: e.tradeDate,
    zLog: e.zLog,
    rvol: e.rvol,
    retDay: casas(e.retDay, CASAS.retDay),
    zExcess: casas(e.zExcess, CASAS.zExcess),
    // `reais(x, 0)` na tela: a celula nunca mostra centavos de ticket medio.
    avgTicket: e.avgTicket === null ? null : Math.round(e.avgTicket),
    volumeFinancial: e.volumeFinancial,
  };
}
