/**
 * Os sinais dos setups do estudo de cripto, lidos do banco.
 *
 * Tem de ser chamado dentro de `noMercado("cripto", ...)`: a consulta nomeia o
 * schema da B3 e a conexao troca pelo de cripto (`mercado-servidor.ts`).
 */

import { conexaoDeAlertas } from "./db";

export type SinalDoEstudo = {
  id: number;
  moeda: string;
  setup: string;
  timeframe: "1d" | "4h";
  lado: "compra" | "venda";
  sinalEm: string;
  fechamento: number;
  stop: number;
  alvo: number;
  prazoCandles: number;
  estado: "aguardando" | "aberto" | "alvo" | "stop" | "prazo";
  entrada: number | null;
  saida: number | null;
  saidaEm: string | null;
  resultadoR: number | null;
  atualizadoEm: string;
};

const TABELA_AUSENTE = "42P01";
const num = (v: unknown) => (v === null || v === undefined ? null : Number(v));
const iso = (v: unknown) => (v instanceof Date ? v.toISOString() : v === null ? null : String(v));

/** Os vivos (aguardando ou abertos) e os encerrados dos ultimos 30 dias. */
export async function sinaisDoEstudo(): Promise<SinalDoEstudo[]> {
  try {
    const { rows } = await conexaoDeAlertas().query(
      `SELECT * FROM volume_scanner.sinais_estudo
        WHERE estado IN ('aguardando', 'aberto') OR saida_em > now() - interval '30 days'
        ORDER BY sinal_em DESC`,
    );
    return rows.map((r) => ({
      id: Number(r.id),
      moeda: String(r.moeda),
      setup: String(r.setup),
      timeframe: r.timeframe,
      lado: r.lado,
      sinalEm: iso(r.sinal_em) ?? "",
      fechamento: Number(r.fechamento),
      stop: Number(r.stop),
      alvo: Number(r.alvo),
      prazoCandles: Number(r.prazo_candles),
      estado: r.estado,
      entrada: num(r.entrada),
      saida: num(r.saida),
      saidaEm: iso(r.saida_em),
      resultadoR: num(r.resultado_r),
      atualizadoEm: iso(r.atualizado_em) ?? "",
    }));
  } catch (erro) {
    // banco sem a migration 0026: sem a secao, em vez de derrubar a pagina
    if ((erro as { code?: string }).code === TABELA_AUSENTE) return [];
    throw erro;
  }
}
