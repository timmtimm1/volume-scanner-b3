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

export type CaixaDaPagina = {
  id: string;
  nome: string;
  coluna: number;
  largura: number;
  /** So existe no computador: no celular a caixa nem ocupa lugar. */
  soComputador?: boolean;
  /** Acompanha a rolagem (como a previa do scanner), quando e a ultima da coluna. */
  fixa?: boolean;
};

export type PaginaDeCaixas = {
  trilhas: string[];
  caixas: CaixaDaPagina[];
};

/** Coluna que divide o que sobra; `minmax(0, ...)` deixa encolher abaixo do conteudo. */
const FLEXIVEL = "minmax(0,1fr)";

export const PAGINAS_DE_CAIXAS: Record<PaginaArrumavel, PaginaDeCaixas> = {
  semana: {
    trilhas: [FLEXIVEL, FLEXIVEL],
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
  inicio: {
    trilhas: ["320px", FLEXIVEL, "380px"],
    caixas: [
      { id: "resumo", nome: "Scanner do dia", coluna: 0, largura: 1 },
      { id: "distribuicao", nome: "Quanto cada papel fugiu", coluna: 0, largura: 1, soComputador: true },
      { id: "leitura", nome: "Leitura do mercado", coluna: 0, largura: 1, soComputador: true },
      { id: "eventos", nome: "Eventos do dia", coluna: 1, largura: 1 },
      { id: "previa", nome: "Prévia do papel", coluna: 2, largura: 1, soComputador: true, fixa: true },
    ],
  },
  ficha: {
    trilhas: ["300px", FLEXIVEL, "360px"],
    caixas: [
      { id: "identidade", nome: "Papel", coluna: 0, largura: 1 },
      { id: "grafico", nome: "Gráfico diário", coluna: 1, largura: 1 },
      { id: "desvio", nome: "Desvio do volume", coluna: 0, largura: 1 },
      { id: "numeros", nome: "Números do pregão", coluna: 0, largura: 1 },
      { id: "abas", nome: "Abas do papel", coluna: 2, largura: 1 },
      { id: "trade", nome: "Trade", coluna: 2, largura: 1 },
      { id: "alerta", nome: "Alertas", coluna: 2, largura: 1 },
    ],
  },
  historico: {
    trilhas: ["minmax(0,9fr)", "minmax(0,11fr)"],
    caixas: [
      { id: "tabela", nome: "Eventos", coluna: 0, largura: 1 },
      { id: "previa", nome: "Prévia do papel", coluna: 1, largura: 1, soComputador: true, fixa: true },
    ],
  },
  // Trades e detalhe do trade: uma coluna, como hoje; o Organizar so muda a ordem.
  trades: {
    trilhas: [FLEXIVEL],
    caixas: [
      { id: "abertos", nome: "Em aberto", coluna: 0, largura: 1 },
      { id: "encerrados", nome: "Encerrados", coluna: 0, largura: 1 },
    ],
  },
  trade: {
    trilhas: [FLEXIVEL],
    caixas: [
      { id: "resultado", nome: "Resultado por pregão", coluna: 0, largura: 1 },
      { id: "pregoes", nome: "Pregões marcados", coluna: 0, largura: 1 },
      { id: "operacoes", nome: "Operações", coluna: 0, largura: 1 },
    ],
  },
};

export function arranjoPadrao(pagina: PaginaDeCaixas): Arranjo {
  return pagina.caixas.map(({ id, coluna, largura }) => ({ id, coluna, largura }));
}
