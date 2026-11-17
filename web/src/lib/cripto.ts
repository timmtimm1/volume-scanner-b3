/**
 * O que so existe em cripto: os nomes das moedas e o volume fora do normal do dia.
 *
 * Tudo aqui tem de ser chamado dentro de `noMercado("cripto", ...)`: as
 * consultas nomeiam o schema da B3 e a conexao troca pelo de cripto
 * (`mercado-servidor.ts`).
 */

import { conexaoDeAlertas } from "./db";

/** Ticker de moeda como a Binance escreve: letras e numeros (BTC, 1INCH, 1000SATS). */
export const MOEDA = /^[A-Z0-9]{1,15}$/;

/** Schema ou tabela que ainda nao existe: a carga de cripto nunca rodou neste banco. */
export function semCripto(erro: unknown): boolean {
  const codigo = (erro as { code?: string }).code;
  return codigo === "42P01" || codigo === "3F000";
}

export type Moeda = { ticker: string; nome: string; posicao: number | null; noTop: boolean };

export async function moedas(): Promise<Record<string, Moeda>> {
  const { rows } = await conexaoDeAlertas().query<{
    ticker: string;
    nome: string;
    posicao: number | null;
    no_top: boolean;
  }>(`SELECT ticker, nome, posicao, no_top FROM volume_scanner.moedas`);
  return Object.fromEntries(
    rows.map((r) => [r.ticker, { ticker: r.ticker, nome: r.nome, posicao: r.posicao, noTop: r.no_top }]),
  );
}

export type VolumeDaMoeda = {
  ticker: string;
  /** Desvio do volume do dia contra os 30 dias anteriores da propria moeda. */
  z: number;
  /** Volume do dia sobre a mediana recente. */
  rvol: number | null;
  fechamento: number;
  /** Variacao do fechamento contra o do dia anterior, como fracao. */
  variacao: number | null;
  volume: number;
};

/** Janela do desvio mostrado na aba: a mesma do resumo diario. */
const JANELA = 30;

/**
 * As moedas cujo volume do ultimo dia mais fugiu do proprio normal.
 *
 * E o detector de volume do scanner (z-score do log do volume contra os 30
 * dias ANTERIORES da propria moeda), lido como ranking: ele mostra onde olhar,
 * nao diz para onde o preco vai.
 */
export async function volumeDoDia(
  quantas = 8,
): Promise<{ dia: string | null; moedas: VolumeDaMoeda[] }> {
  const { rows } = await conexaoDeAlertas().query<{
    ticker: string;
    trade_date: Date | string;
    z_log: string;
    rvol: string | null;
    close: string;
    anterior: string | null;
    volume_financial: string;
  }>(
    `SELECT m.ticker, m.trade_date, m.z_log, m.rvol, b.close, b.volume_financial,
            (SELECT a.close FROM volume_scanner.daily_bars a
              WHERE a.ticker = m.ticker AND a.trade_date < m.trade_date
              ORDER BY a.trade_date DESC LIMIT 1) AS anterior
       FROM volume_scanner.volume_metrics m
       JOIN volume_scanner.daily_bars b USING (ticker, trade_date)
       JOIN volume_scanner.moedas c ON c.ticker = m.ticker AND c.no_top
      WHERE m.window_size = $1
        AND m.z_log IS NOT NULL
        AND m.trade_date = (SELECT max(trade_date) FROM volume_scanner.volume_metrics)
      ORDER BY m.z_log DESC
      LIMIT $2`,
    [JANELA, quantas],
  );
  const primeira = rows[0]?.trade_date;
  const dia =
    primeira === undefined
      ? null
      : primeira instanceof Date
        ? `${primeira.getFullYear()}-${`${primeira.getMonth() + 1}`.padStart(2, "0")}-${`${primeira.getDate()}`.padStart(2, "0")}`
        : String(primeira).slice(0, 10);
  return {
    dia,
    moedas: rows.map((r) => {
      const fechamento = Number(r.close);
      const anterior = r.anterior === null ? null : Number(r.anterior);
      return {
        ticker: r.ticker,
        z: Number(r.z_log),
        rvol: r.rvol === null ? null : Number(r.rvol),
        fechamento,
        variacao: anterior && anterior > 0 ? fechamento / anterior - 1 : null,
        volume: Number(r.volume_financial),
      };
    }),
  };
}
