/**
 * A lista de moedas da aba Cripto (pedido de 23/11/2026): uma linha por moeda,
 * com busca e quatro filtros. Antes a aba mostrava um cartao por SETUP, e a
 * mesma moeda aparecia ate cinco vezes.
 *
 * So contas, sem rede e sem import de valor: os testes rodam este arquivo no Node.
 */

import type { DiaDeHoje } from "./cripto-hoje";
import type { Inclinacoes } from "./tendencia";

/** A moeda aberta quando a URL nao pede nenhuma. */
export const MOEDA_PADRAO = "BTC";

export type LinhaDaMoeda = {
  ticker: string;
  nome: string;
  /** Lugar no ranking de valor de mercado. */
  posicao: number | null;
  preco: number | null;
  /** Variacao do dia, como fracao. */
  variacao: number | null;
  /** Quantos setups estao armados nela agora. */
  setups: number;
  /** Tem trade aberto. */
  comTrade: boolean;
  /** Null quando a moeda ainda nao tem historico para as medias. */
  inclinacoes: Inclinacoes | null;
};

export type FiltroDaLista = "todas" | "sinal" | "alta" | "trades";

export const FILTROS_DA_LISTA: readonly { id: FiltroDaLista; nome: string }[] = [
  { id: "todas", nome: "Todas" },
  { id: "sinal", nome: "Com sinal" },
  { id: "alta", nome: "Em alta" },
  { id: "trades", nome: "Meus trades" },
];

function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .trim();
}

/** 0 = ticker exato, 1 = ticker comeca igual, 2 = nome comeca igual, 3 = contem, null = fora. */
function relevancia(l: LinhaDaMoeda, busca: string): number | null {
  const ticker = normalizar(l.ticker);
  const nome = normalizar(l.nome);
  if (ticker === busca) return 0;
  if (ticker.startsWith(busca)) return 1;
  if (nome.startsWith(busca)) return 2;
  if (ticker.includes(busca) || nome.includes(busca)) return 3;
  return null;
}

function passaNoFiltro(
  l: LinhaDaMoeda,
  filtro: FiltroDaLista,
  emAlta: (l: LinhaDaMoeda) => boolean,
): boolean {
  if (filtro === "sinal") return l.setups > 0;
  if (filtro === "alta") return emAlta(l);
  if (filtro === "trades") return l.comTrade;
  return true;
}

/**
 * As moedas que passam no filtro e na busca. Sem busca, na ordem recebida (valor
 * de mercado); com busca, o ticker exato vem primeiro: "sol" acha SOL antes de
 * uma moeda que so tem "sol" no meio do nome.
 */
export function filtrarMoedas(
  linhas: readonly LinhaDaMoeda[],
  busca: string,
  filtro: FiltroDaLista,
  emAlta: (l: LinhaDaMoeda) => boolean,
): LinhaDaMoeda[] {
  const noFiltro = linhas.filter((l) => passaNoFiltro(l, filtro, emAlta));
  const termo = normalizar(busca);
  if (termo === "") return noFiltro;
  return noFiltro
    .map((l, i) => ({ l, i, r: relevancia(l, termo) }))
    .filter((x): x is { l: LinhaDaMoeda; i: number; r: number } => x.r !== null)
    .sort((a, b) => a.r - b.r || a.i - b.i)
    .map((x) => x.l);
}

/** Quantas moedas cada filtro mostra, sem contar a busca. */
export function contarFiltros(
  linhas: readonly LinhaDaMoeda[],
  emAlta: (l: LinhaDaMoeda) => boolean,
): Record<FiltroDaLista, number> {
  return {
    todas: linhas.length,
    sinal: linhas.filter((l) => passaNoFiltro(l, "sinal", emAlta)).length,
    alta: linhas.filter((l) => passaNoFiltro(l, "alta", emAlta)).length,
    trades: linhas.filter((l) => passaNoFiltro(l, "trades", emAlta)).length,
  };
}

/**
 * Preco e variacao da linha. Com o dia de hoje da Binance, o preco e o de agora
 * e a variacao e contra o ultimo candle FECHADO; sem ele, vale o fechamento.
 */
export function precoDaLinha(
  fechamento: number | null,
  anterior: number | null,
  ultimoDia: string | null,
  hoje: DiaDeHoje | undefined,
): { preco: number | null; variacao: number | null } {
  const contra = (de: number | null, ate: number | null) =>
    de !== null && de > 0 && ate !== null ? ate / de - 1 : null;
  if (hoje && hoje.ultimo > 0) {
    // O pipeline ja gravou o candle de hoje: a base e o de ontem.
    const base = ultimoDia !== null && hoje.dia <= ultimoDia ? anterior : fechamento;
    return { preco: hoje.ultimo, variacao: contra(base, hoje.ultimo) };
  }
  return { preco: fechamento, variacao: contra(anterior, fechamento) };
}
