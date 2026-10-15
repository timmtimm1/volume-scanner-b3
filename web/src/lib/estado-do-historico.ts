/**
 * O que o historico guarda para quem sai e volta: os filtros, quantas linhas
 * estavam abertas, o evento escolhido na previa e a altura da rolagem.
 *
 * Fica no `sessionStorage` da aba. Abrir a ficha e voltar devolve a tela como
 * estava; fechar a aba esquece.
 *
 * Modulo puro (sem import nenhum de runtime), testado com
 * `node --experimental-strip-types` -- mesmo padrao de `regua.ts`.
 */

export type OrdemDoZ = "desc" | "asc" | null;

export type EstadoDoHistorico = {
  corte: number;
  busca: string;
  desde: string;
  ate: string;
  ordemZ: OrdemDoZ;
  linhas: number;
  /** `chaveDoEvento` do evento na previa, ou null para o primeiro da lista. */
  selecionado: string | null;
  rolagem: number;
};

/** O teto do controle de z minimo da tela. */
export const TETO_DO_CORTE = 8;

/** Um evento e um papel num pregao: o par e unico no historico. */
export function chaveDoEvento(e: { ticker: string; tradeDate: string }): string {
  return `${e.ticker}|${e.tradeDate}`;
}

const DATA = /^\d{4}-\d{2}-\d{2}$/;

/**
 * O estado salvo, conferido campo a campo; null se nao ha nada salvo ou se o
 * texto nao e um estado (versao antiga, ou mexido a mao).
 *
 * Campo fora do lugar volta ao padrao em vez de invalidar tudo: um corte abaixo
 * do piso do site (o piso subiu desde que foi salvo) nao deve apagar a busca.
 */
export function lerEstadoDoHistorico(
  texto: string | null,
  minimo: number,
  linhasPorVez: number,
): EstadoDoHistorico | null {
  if (!texto) return null;
  let bruto: unknown;
  try {
    bruto = JSON.parse(texto);
  } catch {
    return null;
  }
  if (typeof bruto !== "object" || bruto === null || Array.isArray(bruto)) return null;
  const o = bruto as Record<string, unknown>;

  const corte =
    typeof o.corte === "number" && o.corte >= minimo && o.corte <= TETO_DO_CORTE
      ? o.corte
      : minimo;
  const busca = typeof o.busca === "string" ? o.busca.slice(0, 60) : "";
  const desde = typeof o.desde === "string" && DATA.test(o.desde) ? o.desde : "";
  const ate = typeof o.ate === "string" && DATA.test(o.ate) ? o.ate : "";
  const ordemZ: OrdemDoZ = o.ordemZ === "desc" || o.ordemZ === "asc" ? o.ordemZ : null;
  const linhas =
    typeof o.linhas === "number" && Number.isInteger(o.linhas) && o.linhas >= linhasPorVez
      ? o.linhas
      : linhasPorVez;
  const selecionado = typeof o.selecionado === "string" ? o.selecionado : null;
  const rolagem =
    typeof o.rolagem === "number" && Number.isFinite(o.rolagem) && o.rolagem > 0 ? o.rolagem : 0;

  return { corte, busca, desde, ate, ordemZ, linhas, selecionado, rolagem };
}

/** Se algum filtro difere do padrao -- e o que faz aparecer o "limpar filtros". */
export function temFiltro(
  e: Pick<EstadoDoHistorico, "corte" | "busca" | "desde" | "ate" | "ordemZ">,
  minimo: number,
): boolean {
  return e.corte !== minimo || e.busca.trim() !== "" || e.desde !== "" || e.ate !== "" || e.ordemZ !== null;
}
