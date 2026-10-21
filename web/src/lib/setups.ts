/**
 * Setups, do lado do site: a leitura da tabela `setups` (fase 1) com o alerta
 * de confirmacao de cada um (fase 2) e o ultimo fechamento do papel.
 *
 * Roda em tempo de pedido, nunca no build: a aba e so de quem esta logado, e
 * o alerta muda durante o pregao. Toda funcao daqui e chamada depois de
 * `ehDono()`. O tipo e a separacao em secoes moram em `setups-tela.ts`, que
 * nao importa `pg` e pode ir para o navegador e para os testes.
 */

import { conexaoDeAlertas } from "./db";
import type { Setup } from "./setups-tela";

type Linha = {
  id: string | number;
  ticker: string;
  trade_date: Date | string;
  categoria: string;
  padroes: string[];
  toques: number;
  virou: boolean;
  furou: boolean;
  rvol: string | number;
  destaque: boolean;
  contexto: string[];
  fechamento: string | number;
  maxima: string | number;
  minima: string | number;
  suporte: string | number;
  // Ausente antes da migration 0015: vale como suporte horizontal.
  suporte_tipo?: string;
  resistencia: string | number | null;
  espaco_r: string | number | null;
  risco_pct: string | number;
  ao_vivo: boolean;
  estado: string;
  confirmado_em: Date | string | null;
  entrada: string | number | null;
  encerrado_em: Date | string | null;
  saida: string | number | null;
  r5: string | number | null;
  r10: string | number | null;
  r20: string | number | null;
  m5: string | number | null;
  m10: string | number | null;
  m20: string | number | null;
  rc5: string | number | null;
  rc10: string | number | null;
  rc20: string | number | null;
  alerta_preco: string | number | null;
  alerta_disparado_em: Date | string | null;
  alerta_preco_disparo: string | number | null;
  alerta_expira_em: Date | string | null;
  ultimo_fechamento: string | number | null;
  ultimo_pregao: Date | string | null;
  pregoes_desde: string | number | null;
};

function dia(v: Date | string | null): string | null {
  if (v === null) return null;
  if (v instanceof Date) {
    const m = `${v.getMonth() + 1}`.padStart(2, "0");
    const d = `${v.getDate()}`.padStart(2, "0");
    return `${v.getFullYear()}-${m}-${d}`;
  }
  return String(v).slice(0, 10);
}

const num = (v: string | number | null): number | null => (v === null ? null : Number(v));

function paraSetup(r: Linha): Setup {
  return {
    id: Number(r.id),
    ticker: r.ticker,
    tradeDate: dia(r.trade_date) ?? "",
    categoria: r.categoria === "forca" ? "forca" : r.categoria === "media" ? "media" : "reversao",
    padroes: r.padroes,
    toques: Number(r.toques),
    virou: r.virou,
    furou: r.furou,
    rvol: Number(r.rvol),
    destaque: r.destaque,
    contexto: r.contexto,
    fechamento: Number(r.fechamento),
    maxima: Number(r.maxima),
    minima: Number(r.minima),
    suporte: Number(r.suporte),
    suporteTipo: r.suporte_tipo ?? "nivel",
    resistencia: num(r.resistencia),
    espacoR: num(r.espaco_r),
    riscoPct: Number(r.risco_pct),
    aoVivo: r.ao_vivo,
    estado: r.estado as Setup["estado"],
    confirmadoEm: dia(r.confirmado_em),
    entrada: num(r.entrada),
    encerradoEm: dia(r.encerrado_em),
    saida: num(r.saida),
    r: { 5: num(r.r5), 10: num(r.r10), 20: num(r.r20) },
    m: { 5: num(r.m5), 10: num(r.m10), 20: num(r.m20) },
    rc: { 5: num(r.rc5), 10: num(r.rc10), 20: num(r.rc20) },
    alerta:
      r.alerta_preco === null
        ? null
        : {
            preco: Number(r.alerta_preco),
            disparadoEm: r.alerta_disparado_em
              ? new Date(r.alerta_disparado_em).toISOString()
              : null,
            precoDisparo: num(r.alerta_preco_disparo),
            expiraEm: dia(r.alerta_expira_em),
          },
    ultimoFechamento: num(r.ultimo_fechamento),
    ultimoPregao: dia(r.ultimo_pregao),
    pregoesDesde: num(r.pregoes_desde),
  };
}

/**
 * Todos os setups (ou os de um papel), do candle mais novo para o mais antigo.
 *
 * `pregoes_desde` conta os pregoes do papel depois da confirmacao: e o "dia N
 * de 20" do que esta em andamento. O ultimo fechamento vem de `daily_bars`, o
 * mesmo COTAHIST de tudo -- nao a cotacao do momento.
 */
export async function listarSetups(ticker?: string): Promise<Setup[]> {
  const filtro = ticker ? "WHERE s.ticker = $1" : "";
  const { rows } = await conexaoDeAlertas().query<Linha>(
    `SELECT s.*,
            a.preco AS alerta_preco,
            a.disparado_em AS alerta_disparado_em,
            a.preco_disparo AS alerta_preco_disparo,
            a.expira_em AS alerta_expira_em,
            b.close AS ultimo_fechamento,
            b.trade_date AS ultimo_pregao,
            CASE WHEN s.confirmado_em IS NULL THEN NULL ELSE (
              SELECT count(*) FROM volume_scanner.daily_bars d
               WHERE d.ticker = s.ticker AND d.trade_date > s.confirmado_em
            ) END AS pregoes_desde
       FROM volume_scanner.setups s
       LEFT JOIN volume_scanner.price_alerts a ON a.setup_id = s.id
       LEFT JOIN LATERAL (
         SELECT close, trade_date FROM volume_scanner.daily_bars d
          WHERE d.ticker = s.ticker ORDER BY trade_date DESC LIMIT 1
       ) b ON true
       ${filtro}
      ORDER BY s.trade_date DESC, s.rvol DESC`,
    ticker ? [ticker.toUpperCase()] : [],
  );
  return rows.map(paraSetup);
}
