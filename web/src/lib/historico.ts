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

/**
 * Um papel na lista do historico: o evento mais recente dele (o que a linha
 * mostra e o grafico centraliza) e quantos eventos ele teve.
 */
export type PapelDoHistorico = LinhaDoHistorico & {
  /** Quantos eventos do papel passaram nos filtros. A linha mostra o ultimo. */
  eventos: number;
};

/**
 * Junta os eventos por papel: uma linha por papel, e nao uma por evento
 * (pedido de 18/11/2026). Antes um papel agitado aparecia cinco vezes seguidas
 * na lista; agora aparece uma, e os outros eventos dele ficam marcados no
 * grafico (o candle dourado).
 *
 * Recebe os eventos JA filtrados (z minimo, periodo, busca): a linha leva o
 * ultimo evento que passou, e a contagem e dos que passaram. A ordem da saida e
 * a do evento mais recente de cada papel, do mais novo para o mais antigo; no
 * mesmo pregao, a ordem em que chegaram (a do banco, maior z primeiro).
 */
export function agruparPorPapel(eventos: LinhaDoHistorico[]): PapelDoHistorico[] {
  const porPapel = new Map<string, PapelDoHistorico>();
  for (const e of eventos) {
    const atual = porPapel.get(e.ticker);
    if (!atual) {
      porPapel.set(e.ticker, { ...e, eventos: 1 });
    } else if (e.tradeDate > atual.tradeDate) {
      porPapel.set(e.ticker, { ...e, eventos: atual.eventos + 1 });
    } else {
      atual.eventos += 1;
    }
  }
  // `sort` e estavel: no mesmo pregao fica a ordem de chegada.
  return [...porPapel.values()].sort((a, b) =>
    a.tradeDate === b.tradeDate ? 0 : a.tradeDate > b.tradeDate ? -1 : 1,
  );
}
