/**
 * As caixas de cada pagina arrumavel: nome, e onde ficam no arranjo padrao.
 *
 * O padrao e a ordem do celular: no celular as caixas ficam sempre nesta ordem,
 * uma embaixo da outra, qualquer que seja o arranjo do computador.
 *
 * `trilhas` sao as colunas da pagina no computador, em CSS. As laterais fixas
 * (300px, 360px) continuam fixas: o arranjo escolhe so onde cada caixa entra.
 */

import type { Arranjo, PaginaArrumavel } from "./arranjo";

export type CaixaDaPagina = { id: string; nome: string; coluna: number; largura: number };

export type PaginaDeCaixas = {
  trilhas: string[];
  caixas: CaixaDaPagina[];
};

const METADE = "minmax(0,1fr)";

/** So as paginas ja ligadas ao Organizar; as outras entram nas fases seguintes. */
export const PAGINAS_DE_CAIXAS: Partial<Record<PaginaArrumavel, PaginaDeCaixas>> = {
  semana: {
    trilhas: [METADE, METADE],
    caixas: [
      { id: "abertura", nome: "Abertura", coluna: 0, largura: 2 },
      { id: "acoes", nome: "Ações", coluna: 0, largura: 2 },
      { id: "noticias", nome: "Notícias da semana", coluna: 0, largura: 1 },
      { id: "cripto", nome: "Cripto", coluna: 1, largura: 1 },
      { id: "juros", nome: "Juros no Brasil", coluna: 0, largura: 1 },
      { id: "eua", nome: "EUA", coluna: 1, largura: 1 },
      { id: "semana-que-vem", nome: "Semana que vem", coluna: 0, largura: 1 },
      { id: "balancos", nome: "Balanços", coluna: 1, largura: 1 },
    ],
  },
};

export function arranjoPadrao(pagina: PaginaDeCaixas): Arranjo {
  return pagina.caixas.map(({ id, coluna, largura }) => ({ id, coluna, largura }));
}
