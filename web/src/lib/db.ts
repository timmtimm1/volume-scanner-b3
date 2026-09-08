/**
 * Leitura do Postgres em tempo de build.
 *
 * O site e estatico: estas consultas rodam uma vez, quando o Actions dispara o
 * rebuild depois do scan do pregao. Nada disso vai para o navegador, e nao ha
 * API no ar -- e o que faz a pagina abrir instantanea no celular.
 *
 * A tela mostra eventos ABAIXO do limiar de alerta, para o filtro de z ter
 * faixa onde passear. O Telegram continua avisando so acima de `alert.threshold`
 * do config.yaml; `notificado` marca quais foram.
 *
 * O contexto da secao 3.2 vem de `daily_features`, que o pipeline grava para
 * todo pregao avaliado. `events.features` entra so como reserva: linha antiga,
 * gravada antes da tabela existir, ainda tem o contexto la.
 */

import { Pool } from "pg";
import type { Barra, Evento, Papel, Pregao, Universo } from "./types";

/** Piso do que o site carrega. Abaixo disso nao ha o que ler no grafico. */
export const Z_MINIMO_DO_SITE = 3.0;

/** Espelha `alert.min_volume_brl` do config.yaml. */
export const PISO_DE_VOLUME = 500_000;

let pool: Pool | null = null;

function conexao(): Pool {
  if (pool) return pool;
  const url = process.env.SCANNER_DATABASE_URL;
  if (!url) {
    throw new Error(
      "SCANNER_DATABASE_URL ausente. O build le o banco direto; sem a variavel " +
        "nao ha o que renderizar.",
    );
  }
  // O driver do Python usa o prefixo postgresql+psycopg://, que o `pg` nao entende.
  pool = new Pool({
    connectionString: url.replace(/^postgresql\+psycopg:\/\//, "postgresql://"),
    max: 4,
  });
  return pool;
}

function num(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function dia(v: unknown): string {
  if (v instanceof Date) {
    // Sem toISOString: ele converte para UTC e pode recuar um dia.
    const m = `${v.getMonth() + 1}`.padStart(2, "0");
    const d = `${v.getDate()}`.padStart(2, "0");
    return `${v.getFullYear()}-${m}-${d}`;
  }
  return String(v).slice(0, 10);
}

type LinhaEvento = {
  ticker: string;
  trade_date: Date;
  z_log: string;
  window_size: number;
  z_robust: string | null;
  rvol: string | null;
  close: string;
  volume_financial: string;
  trades_count: number | null;
  trades_censored: boolean;
  features: Record<string, number | null> | null;
  notificado: boolean;
};

/**
 * Eventos acima de `Z_MINIMO_DO_SITE`, um por (papel, pregao), com o z de cada
 * janela agrupado. A janela de referencia do z principal e a menor configurada,
 * que e a mais sensivel.
 */
async function lerEventos(where: string, params: unknown[]): Promise<Evento[]> {
  const { rows } = await conexao().query<LinhaEvento>(
    `SELECT m.ticker, m.trade_date, m.z_log, m.window_size, m.z_robust, m.rvol,
            b.close, b.volume_financial, b.trades_count, b.trades_censored,
            COALESCE(f.features, e.features) AS features,
            (e.id IS NOT NULL AND e.notified_at IS NOT NULL) AS notificado
       FROM volume_scanner.volume_metrics m
       JOIN volume_scanner.daily_bars b
         ON b.ticker = m.ticker AND b.trade_date = m.trade_date
       LEFT JOIN volume_scanner.events e
         ON e.ticker = m.ticker AND e.trade_date = m.trade_date
       LEFT JOIN volume_scanner.daily_features f
         ON f.ticker = m.ticker AND f.trade_date = m.trade_date
      WHERE m.z_log IS NOT NULL
        AND b.volume_financial >= $1
        AND ${where}
      ORDER BY m.trade_date DESC, m.z_log DESC`,
    [PISO_DE_VOLUME, ...params],
  );

  const porChave = new Map<string, Evento>();
  for (const r of rows) {
    const data = dia(r.trade_date);
    const chave = `${r.ticker}|${data}`;
    const z = num(r.z_log) ?? 0;
    let ev = porChave.get(chave);
    if (!ev) {
      const f = r.features ?? {};
      ev = {
        ticker: r.ticker,
        tradeDate: data,
        zLog: z,
        zByWindow: {},
        zRobust: num(r.z_robust),
        rvol: num(r.rvol),
        close: num(r.close) ?? 0,
        volumeFinancial: num(r.volume_financial) ?? 0,
        tradesCount: r.trades_count,
        tradesCensored: r.trades_censored,
        retDay: num(f.ret_day),
        clv: num(f.clv),
        gap: num(f.gap),
        rangeNorm: num(f.range_norm),
        pos252: num(f.pos252),
        retPrior20: num(f.ret_prior_20),
        avgTicket: num(f.avg_ticket),
        ticketZ: num(f.ticket_z),
        mktVolZ: num(f.mkt_vol_z),
        zExcess: num(f.z_excess),
        notificado: r.notificado,
      };
      porChave.set(chave, ev);
    }
    ev.zByWindow[r.window_size] = z;
    // O z principal e o da menor janela, a mais sensivel.
    const menor = Math.min(...Object.keys(ev.zByWindow).map(Number));
    ev.zLog = ev.zByWindow[menor];
    if (r.window_size === menor) {
      ev.zRobust = num(r.z_robust);
      ev.rvol = num(r.rvol);
    }
  }

  return [...porChave.values()].sort(
    (a, b) => b.tradeDate.localeCompare(a.tradeDate) || b.zLog - a.zLog,
  );
}

/** O pregao mais recente com dado carregado. */
export async function ultimoPregao(): Promise<Pregao> {
  const { rows } = await conexao().query<{
    trade_date: Date;
    avaliados: string;
  }>(
    `SELECT trade_date, COUNT(DISTINCT ticker) AS avaliados
       FROM volume_scanner.volume_metrics
      WHERE z_log IS NOT NULL
      GROUP BY trade_date ORDER BY trade_date DESC LIMIT 1`,
  );
  if (!rows.length) throw new Error("banco sem metricas: rode scanner metrics compute");

  const data = dia(rows[0].trade_date);
  const [{ rows: mkt }, { rows: not }] = await Promise.all([
    // De `daily_features`, nao de `events`: em pregao sem nenhum cruzamento a
    // tabela de eventos fica vazia e o z do mercado sumiria da tela.
    conexao().query<{ features: Record<string, number> | null }>(
      `SELECT features FROM volume_scanner.daily_features
        WHERE trade_date = $1 AND features ? 'mkt_vol_z' LIMIT 1`,
      [data],
    ),
    conexao().query<{ n: string }>(
      `SELECT COUNT(*) AS n FROM volume_scanner.events
        WHERE trade_date = $1 AND notified_at IS NOT NULL`,
      [data],
    ),
  ]);

  return {
    tradeDate: data,
    mktVolZ: num(mkt[0]?.features?.mkt_vol_z ?? null),
    avaliados: Number(rows[0].avaliados),
    notificados: Number(not[0]?.n ?? 0),
  };
}

/** Eventos do pregao, para a Tela 1. */
export async function eventosDoPregao(data: string): Promise<Evento[]> {
  return lerEventos("m.trade_date = $2 AND m.z_log >= $3", [data, Z_MINIMO_DO_SITE]);
}

/** Eventos de todo o historico disponivel, para a Tela 3. */
export async function eventosDoHistorico(limite = 400): Promise<Evento[]> {
  const todos = await lerEventos("m.z_log >= $2", [Z_MINIMO_DO_SITE]);
  return todos.slice(0, limite);
}

/** Barras e eventos de um papel, para a ficha. */
export async function papel(ticker: string, sessoes = 180): Promise<Papel> {
  const { rows } = await conexao().query(
    `SELECT trade_date, open, high, low, close, volume_financial
       FROM volume_scanner.daily_bars
      WHERE ticker = $1 ORDER BY trade_date DESC LIMIT $2`,
    [ticker, sessoes],
  );
  const barras: Barra[] = rows
    .map((r) => ({
      tradeDate: dia(r.trade_date),
      open: num(r.open),
      high: num(r.high),
      low: num(r.low),
      close: num(r.close) ?? 0,
      volumeFinancial: num(r.volume_financial) ?? 0,
    }))
    .reverse();

  const eventos = await lerEventos("m.ticker = $2 AND m.z_log >= $3", [
    ticker,
    Z_MINIMO_DO_SITE,
  ]);
  return { ticker, barras, eventos };
}

/** Papeis que ganham pagina estatica: os que tem ao menos um evento. */
export async function papeisComEvento(): Promise<string[]> {
  const { rows } = await conexao().query<{ ticker: string }>(
    `SELECT DISTINCT ticker FROM volume_scanner.volume_metrics
      WHERE z_log >= $1 ORDER BY ticker`,
    [Z_MINIMO_DO_SITE],
  );
  return rows.map((r) => r.ticker);
}

export async function fecharConexao(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = null;
  }
}

/**
 * Espelha `universe` do config.yaml.
 *
 * Estes numeros existem em dois lugares: aqui e no `config.yaml` que o Python
 * le. A regra e simples o bastante (mediana e cobertura) para o risco de
 * divergencia ser pequeno, e `scanner universe show` continua sendo a fonte de
 * verdade -- se um dia os dois discordarem, o Python esta certo.
 */
export const UNIVERSO = {
  janela: 60,
  pisoMediana: 500_000,
  coberturaMinima: 0.8,
} as const;

/** Papeis que o scanner acompanha, e por que cada um entrou. */
export async function universo(): Promise<Universo> {
  const { rows } = await conexao().query<{
    ticker: string;
    mediana: string;
    pregoes: string;
    ultimo: string | null;
  }>(
    `WITH janela AS (
       SELECT trade_date FROM (
         SELECT DISTINCT trade_date FROM volume_scanner.daily_bars
          ORDER BY trade_date DESC LIMIT $1
       ) t
     )
     SELECT b.ticker,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY b.volume_financial) AS mediana,
            COUNT(*) AS pregoes,
            (ARRAY_AGG(b.close ORDER BY b.trade_date DESC))[1] AS ultimo
       FROM volume_scanner.daily_bars b
       JOIN janela j ON j.trade_date = b.trade_date
      WHERE b.volume_financial > 0
      GROUP BY b.ticker
      ORDER BY mediana DESC`,
    [UNIVERSO.janela],
  );

  const todos = rows.map((r) => ({
    ticker: r.ticker,
    medianaVolume: num(r.mediana) ?? 0,
    pregoesNegociados: Number(r.pregoes),
    cobertura: Number(r.pregoes) / UNIVERSO.janela,
    ultimoFechamento: num(r.ultimo),
  }));

  return {
    papeis: todos.filter(
      (p) =>
        p.medianaVolume >= UNIVERSO.pisoMediana &&
        p.cobertura >= UNIVERSO.coberturaMinima,
    ),
    janela: UNIVERSO.janela,
    pisoMediana: UNIVERSO.pisoMediana,
    coberturaMinima: UNIVERSO.coberturaMinima,
    avaliados: todos.length,
  };
}
