/**
 * A tabela `tendencias` (migration 0028), lida pelo scanner e pela aba Cripto.
 *
 * So no servidor. Para cripto, chame dentro de `noMercado("cripto", ...)`: a
 * consulta nomeia o schema da B3 e a conexao troca pelo de cripto. Do mais
 * negociado para o menos.
 */

import { conexaoDeAlertas } from "./db";
import type { Inclinacao, Inclinacoes } from "./tendencia";

export type LinhaDeTendencia = {
  ticker: string;
  /** Acima do piso de liquidez do mercado (a regra do backtest). */
  liquido: boolean;
  fechamento: number;
  variacao: number | null;
  inclinacoes: Inclinacoes;
};

export type Tendencias = {
  /** O pregao (ou o dia do candle, em cripto) da tabela; null sem linha. */
  dia: string | null;
  linhas: LinhaDeTendencia[];
};

const TABELA_AUSENTE = "42P01";
const SCHEMA_AUSENTE = "3F000";

const inc = (v: unknown): Inclinacao => (Number(v) > 0 ? 1 : Number(v) < 0 ? -1 : 0);

function dia(v: unknown): string {
  if (v instanceof Date) {
    const m = `${v.getMonth() + 1}`.padStart(2, "0");
    const d = `${v.getDate()}`.padStart(2, "0");
    return `${v.getFullYear()}-${m}-${d}`;
  }
  return String(v).slice(0, 10);
}

/** `soLiquidos`: `tendenciaSoLiquidos(mercado)`, de `mercado.ts`. */
export async function lerTendencias(soLiquidos: boolean): Promise<Tendencias> {
  try {
    const { rows } = await conexaoDeAlertas().query(
      `SELECT * FROM volume_scanner.tendencias
        WHERE liquido OR NOT $1
        ORDER BY volume_mediano DESC NULLS LAST, ticker`,
      [soLiquidos],
    );
    return {
      dia: rows.length > 0 ? dia(rows[0].trade_date) : null,
      linhas: rows.map((r) => ({
        ticker: String(r.ticker),
        liquido: Boolean(r.liquido),
        fechamento: Number(r.fechamento),
        variacao: r.variacao === null ? null : Number(r.variacao),
        inclinacoes: {
          mme9: inc(r.mme9),
          mme20: inc(r.mme20),
          mme50: inc(r.mme50),
          mme80: inc(r.mme80),
          mme200: inc(r.mme200),
          mma9: inc(r.mma9),
          mma20: inc(r.mma20),
          mma50: inc(r.mma50),
          mma80: inc(r.mma80),
          mma200: inc(r.mma200),
        },
      })),
    };
  } catch (erro) {
    // banco sem a migration 0028 (ou sem o schema de cripto): sem painel, sem derrubar a pagina
    const codigo = (erro as { code?: string }).code;
    if (codigo === TABELA_AUSENTE || codigo === SCHEMA_AUSENTE) return { dia: null, linhas: [] };
    throw erro;
  }
}
