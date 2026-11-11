/**
 * Entradas de hoje, do lado do banco: as linhas do backtest que o cartao usa e
 * os candles do mini grafico. Roda em tempo de pedido, depois de `ehDono()`.
 * As contas moram em `entradas.ts`, que nao importa `pg`.
 */

import type { Grupo, Saida } from "./backtest-tela";
import { conexaoDeAlertas } from "./db";
import type { Candle, LinhaDoBacktest } from "./entradas";

type Numero = number | string | null;

const num = (v: Numero | undefined): number | null =>
  v === null || v === undefined ? null : Number(v);

const COLUNA_AUSENTE = "42703";
const TABELA_AUSENTE = "42P01";

const COLUNAS = `setup, saida, grupo, periodo, n, acerto, ganho_medio, dias_medio,
                 expectativa, ic_baixo, diferenca`;

/**
 * A grade da rodada nos dois periodos do cartao: 2016-2026 (a nota) e o
 * historico inteiro (ganho medio, duracao, pior fase).
 *
 * As colunas da pior fase sao da migration 0020: num banco que ainda nao a
 * recebeu, a consulta cai para a versao sem elas e o cartao esconde a linha.
 */
export async function linhasDoBacktest(rodadaId: number): Promise<LinhaDoBacktest[]> {
  const consulta = (extra: string) =>
    conexaoDeAlertas().query<Record<string, Numero>>(
      `SELECT ${COLUNAS}${extra}
         FROM volume_scanner.backtest_resultados
        WHERE rodada_id = $1 AND periodo IN ('2016-2026', 'tudo')`,
      [rodadaId],
    );
  let rows: Record<string, Numero>[];
  try {
    ({ rows } = await consulta(", pior_sequencia, pior_recuo"));
  } catch (erro) {
    if ((erro as { code?: string }).code !== COLUNA_AUSENTE) throw erro;
    ({ rows } = await consulta(""));
  }
  return rows.map((r) => ({
    setup: String(r.setup),
    saida: r.saida as Saida,
    grupo: r.grupo as Grupo,
    periodo: r.periodo as LinhaDoBacktest["periodo"],
    n: Number(r.n),
    acerto: num(r.acerto),
    ganhoMedio: num(r.ganho_medio),
    diasMedio: num(r.dias_medio),
    expectativa: num(r.expectativa),
    icBaixo: num(r.ic_baixo),
    diferenca: num(r.diferenca),
    piorSequencia: num(r.pior_sequencia),
    piorRecuo: num(r.pior_recuo),
  }));
}

function dia(v: Date | string): string {
  if (v instanceof Date) {
    const m = `${v.getMonth() + 1}`.padStart(2, "0");
    const d = `${v.getDate()}`.padStart(2, "0");
    return `${v.getFullYear()}-${m}-${d}`;
  }
  return String(v).slice(0, 10);
}

/** Quantos candles o mini grafico mostra. */
export const CANDLES_DO_MINI = 30;

/**
 * Os ultimos candles de cada papel, do mais antigo para o mais novo. Uma
 * consulta para todos os papeis da lista. Barra sem abertura, maxima ou minima
 * (o COTAHIST antigo as vezes nao traz) fica de fora.
 */
export async function candlesDosPapeis(
  tickers: readonly string[],
  quantos = CANDLES_DO_MINI,
): Promise<Record<string, Candle[]>> {
  if (tickers.length === 0) return {};
  try {
    const { rows } = await conexaoDeAlertas().query<{
      ticker: string;
      trade_date: Date | string;
      open: Numero;
      high: Numero;
      low: Numero;
      close: Numero;
    }>(
      `SELECT ticker, trade_date, open, high, low, close
         FROM (
           SELECT ticker, trade_date, open, high, low, close,
                  row_number() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS ordem
             FROM volume_scanner.daily_bars
            WHERE ticker = ANY($1)
              AND trade_date >= CURRENT_DATE - 120
              AND open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL
         ) b
        WHERE ordem <= $2
        ORDER BY ticker, trade_date`,
      [[...new Set(tickers)], quantos],
    );
    const porPapel: Record<string, Candle[]> = {};
    for (const r of rows) {
      (porPapel[r.ticker] ??= []).push({
        dia: dia(r.trade_date),
        abre: Number(r.open),
        maxima: Number(r.high),
        minima: Number(r.low),
        fecha: Number(r.close),
      });
    }
    return porPapel;
  } catch (erro) {
    if ((erro as { code?: string }).code === TABELA_AUSENTE) return {};
    throw erro;
  }
}
