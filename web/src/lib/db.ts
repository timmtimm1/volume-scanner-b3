/**
 * Leitura do Postgres em tempo de build.
 *
 * As telas de dado -- scanner, historico, papeis, ficha -- continuam sendo
 * geradas no build, uma vez por pregao, quando o Actions dispara o rebuild
 * depois do scan. Nada disso vai para o navegador, e e o que faz a pagina abrir
 * instantanea no celular.
 *
 * O que mudou com os alertas: existem agora rotas de API que rodam com o site
 * no ar, e elas reusam o mesmo pool daqui (`conexaoDeAlertas`). A separacao que
 * importa nao e mais "build ou runtime", e sim: dado do pregao e publico e
 * pre-renderizado; alerta e pessoal, exige sessao e e sempre lido na hora.
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
import { PISO_DE_VOLUME, UNIVERSO, Z_MINIMO_DO_SITE } from "./config";
import type { Barra, Evento, FaixaDeDesvio, Papel, Pregao, Universo } from "./types";

let pool: Pool | null = null;

/**
 * O mesmo pool, para as rotas de API dos alertas.
 *
 * Reusar em vez de abrir um segundo: o Neon cobra conexao, e duas piscinas no
 * mesmo processo dobrariam o consumo sem ganho nenhum.
 */
export function conexaoDeAlertas(): Pool {
  return conexao();
}

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
 * Eventos com z >= `Z_MINIMO_DO_SITE` em alguma janela, um por (papel, pregao).
 *
 * O z principal e o MAIOR entre as janelas, como a secao 6 do plano pede e como
 * o alerta decide (qualquer janela cruzando dispara). Antes era o da menor
 * janela que tivesse passado de 3, e as janelas abaixo de 3 nem vinham: um
 * evento com 60d em 6,3 e 30d em 5,5 aparecia com 5,5, abaixo da linha do
 * alerta que ja tinha chegado no Telegram. Medido no banco local: 21 de 117
 * eventos acima de 6.
 *
 * Por isso a consulta tem duas partes: `chaves` escolhe os pares que passam
 * (e aplica o limite, se houver), e a de fora traz TODAS as janelas desses
 * pares, para o "z por janela" da ficha nao perder nenhuma.
 *
 * `onde` filtra dentro de `chaves` e usa o alias `m`; seus parametros comecam
 * em $3 ($1 e o piso de volume, $2 o z minimo).
 */
async function lerEventos(
  onde: string,
  params: unknown[],
  limite?: number,
): Promise<Evento[]> {
  const valores: unknown[] = [PISO_DE_VOLUME, Z_MINIMO_DO_SITE, ...params];
  let corte = "";
  if (limite !== undefined) {
    valores.push(limite);
    corte = `LIMIT $${valores.length}`;
  }

  const { rows } = await conexao().query<LinhaEvento>(
    `WITH chaves AS (
       SELECT m.ticker, m.trade_date, MAX(m.z_log) AS z_max
         FROM volume_scanner.volume_metrics m
         JOIN volume_scanner.daily_bars b
           ON b.ticker = m.ticker AND b.trade_date = m.trade_date
        WHERE b.volume_financial >= $1
          AND ${onde}
        GROUP BY m.ticker, m.trade_date
       HAVING MAX(m.z_log) >= $2
        ORDER BY m.trade_date DESC, z_max DESC
        ${corte}
     )
     SELECT m.ticker, m.trade_date, m.z_log, m.window_size, m.z_robust, m.rvol,
            b.close, b.volume_financial, b.trades_count, b.trades_censored,
            COALESCE(f.features, e.features) AS features,
            (e.id IS NOT NULL AND e.notified_at IS NOT NULL) AS notificado
       FROM chaves k
       JOIN volume_scanner.volume_metrics m
         ON m.ticker = k.ticker AND m.trade_date = k.trade_date
       JOIN volume_scanner.daily_bars b
         ON b.ticker = k.ticker AND b.trade_date = k.trade_date
       LEFT JOIN volume_scanner.events e
         ON e.ticker = k.ticker AND e.trade_date = k.trade_date
       LEFT JOIN volume_scanner.daily_features f
         ON f.ticker = k.ticker AND f.trade_date = k.trade_date
      WHERE m.z_log IS NOT NULL
      ORDER BY k.trade_date DESC, k.z_max DESC, m.window_size`,
    valores,
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
        zJanela: r.window_size,
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
    // As linhas vem por janela crescente: so troca com z estritamente maior,
    // e no empate fica a janela menor.
    if (z > ev.zLog) {
      ev.zLog = z;
      ev.zJanela = r.window_size;
    }
    // rvol e z robusto seguem vindo da menor janela, que e a que a ficha
    // rotula ("mediana de 30 pregoes").
    const menor = Math.min(...Object.keys(ev.zByWindow).map(Number));
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
  return lerEventos("m.trade_date = $3", [data]);
}

/**
 * Os eventos mais recentes, para a Tela 3.
 *
 * O limite vai no SQL. Antes a consulta trazia o historico inteiro e cortava
 * no JavaScript, a cada build.
 */
export async function eventosDoHistorico(limite = 1000): Promise<Evento[]> {
  return lerEventos("TRUE", [], limite);
}

/** Barras e eventos de um papel, para a ficha. */
export async function papel(ticker: string, sessoes = 180): Promise<Papel> {
  // As duas consultas em paralelo: o build faz isso para cada papel com ficha.
  const [{ rows }, eventos] = await Promise.all([
    conexao().query(
      `SELECT trade_date, open, high, low, close, volume_financial
         FROM volume_scanner.daily_bars
        WHERE ticker = $1 ORDER BY trade_date DESC LIMIT $2`,
      [ticker, sessoes],
    ),
    lerEventos("m.ticker = $3", [ticker]),
  ]);
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

/** Quantos papeis do pregao ficaram em cada faixa de desvio, pelo maior z entre as janelas. */
export async function distribuicaoDoPregao(data: string): Promise<FaixaDeDesvio[]> {
  const { rows } = await conexao().query<{ faixa: number; papeis: string }>(
    `SELECT LEAST(GREATEST(FLOOR(z)::int, 0), 6) AS faixa, COUNT(*) AS papeis
       FROM (
         SELECT m.ticker, MAX(m.z_log) AS z
           FROM volume_scanner.volume_metrics m
           JOIN volume_scanner.daily_bars b
             ON b.ticker = m.ticker AND b.trade_date = m.trade_date
          WHERE m.trade_date = $1 AND m.z_log IS NOT NULL AND b.volume_financial >= $2
          GROUP BY m.ticker
       ) t
      GROUP BY 1`,
    [data, PISO_DE_VOLUME],
  );
  const porFaixa = new Map(rows.map((r) => [Number(r.faixa), Number(r.papeis)]));
  return [0, 1, 2, 3, 4, 5, 6].map((faixa) => ({ faixa, papeis: porFaixa.get(faixa) ?? 0 }));
}

/**
 * Os ultimos `sessoes` pregoes de cada papel pedido, ate `data`, numa consulta.
 * Alimenta os mini-graficos do scanner: volume de cada linha e a previa.
 */
export async function barrasRecentes(
  tickers: string[],
  data: string,
  sessoes = 40,
): Promise<Record<string, Barra[]>> {
  if (tickers.length === 0) return {};
  const { rows } = await conexao().query(
    `SELECT ticker, trade_date, open, high, low, close, volume_financial
       FROM (
         SELECT b.*, ROW_NUMBER() OVER (PARTITION BY b.ticker ORDER BY b.trade_date DESC) AS n
           FROM volume_scanner.daily_bars b
          WHERE b.ticker = ANY($1) AND b.trade_date <= $2
       ) t
      WHERE n <= $3
      ORDER BY ticker, trade_date`,
    [tickers, data, sessoes],
  );
  const saida: Record<string, Barra[]> = {};
  for (const r of rows) {
    (saida[r.ticker] ??= []).push({
      tradeDate: dia(r.trade_date),
      open: num(r.open),
      high: num(r.high),
      low: num(r.low),
      close: num(r.close) ?? 0,
      volumeFinancial: num(r.volume_financial) ?? 0,
    });
  }
  return saida;
}
