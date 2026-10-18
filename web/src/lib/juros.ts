// A logica pura do grafico de juros da aba Semana: series, filtro por edicao,
// tons e leitura do cursor. Sem React e sem lightweight-charts, para testar em
// Node (`npm test`).

import type { HistoricoDeJuros, IdDaSerie, LinhaDeJuros } from "./types";

export type { IdDaSerie };

export type DefinicaoDaSerie = {
  id: IdDaSerie;
  /** No chip, na leitura do cursor e na tabela. */
  rotulo: string;
  /** Liga ao abrir: sete linhas juntas em 390px viram rabisco. */
  ligadaAoAbrir: boolean;
};

/** Na ordem da legenda: a Selic primeiro, depois os prefixados, depois o juro real. */
export const SERIES: readonly DefinicaoDaSerie[] = [
  { id: "selic", rotulo: "Selic", ligadaAoAbrir: true },
  { id: "pre_1a", rotulo: "Pré 1a", ligadaAoAbrir: true },
  { id: "pre_2a", rotulo: "Pré 2a", ligadaAoAbrir: false },
  { id: "pre_5a", rotulo: "Pré 5a", ligadaAoAbrir: false },
  { id: "pre_10a", rotulo: "Pré 10a", ligadaAoAbrir: true },
  { id: "ipca_5a", rotulo: "IPCA+ 5a", ligadaAoAbrir: false },
  { id: "ipca_10a", rotulo: "IPCA+ 10a", ligadaAoAbrir: true },
];

export type PontoDaSerie = { time: string; value: number };

export function ligadasAoAbrir(): Set<IdDaSerie> {
  return new Set(SERIES.filter((s) => s.ligadaAoAbrir).map((s) => s.id));
}

/**
 * As linhas do banco em forma compacta: uma lista de semanas (ordenada, sem
 * repetir) e, por serie, um vetor alinhado a ela com a taxa a 2 casas (o grafico
 * mostra 2) ou `null` onde a serie nao tem ponto. Serie desconhecida e ignorada.
 * A hora do ponto e a sexta nominal da semana, igual para todas as series: a
 * Selic e o Tesouro Direto tem datas-base diferentes, mas caem na mesma sexta.
 */
export function compactar(linhas: LinhaDeJuros[]): HistoricoDeJuros {
  const conhecidas = new Set<string>(SERIES.map((s) => s.id));
  const validas = linhas.filter((l) => conhecidas.has(l.serie) && Number.isFinite(l.taxa));
  const semanas = [...new Set(validas.map((l) => l.semana))].sort();
  const posicao = new Map(semanas.map((s, i) => [s, i]));
  const taxas = Object.fromEntries(
    SERIES.map((s) => [s.id, new Array<number | null>(semanas.length).fill(null)]),
  ) as HistoricoDeJuros["taxas"];
  for (const l of validas) {
    taxas[l.serie as IdDaSerie][posicao.get(l.semana) as number] = Math.round(l.taxa * 100) / 100;
  }
  return { semanas, taxas };
}

/** O valor de cada serie numa semana; `null` onde a serie nao tem ponto ali. */
export function valoresNaSemana(
  historico: HistoricoDeJuros,
  semana: string,
): Record<IdDaSerie, number | null> {
  const i = historico.semanas.indexOf(semana);
  const achar = (id: IdDaSerie) => (i < 0 ? null : (historico.taxas[id][i] ?? null));
  return {
    selic: achar("selic"),
    pre_1a: achar("pre_1a"),
    pre_2a: achar("pre_2a"),
    pre_5a: achar("pre_5a"),
    pre_10a: achar("pre_10a"),
    ipca_5a: achar("ipca_5a"),
    ipca_10a: achar("ipca_10a"),
  };
}

/** `#rrggbb` misturado com branco (t > 0) ou com preto (t < 0); |t| entre 0 e 1. */
export function misturar(hex: string, t: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const alvo = t >= 0 ? 255 : 0;
  const peso = Math.min(1, Math.abs(t));
  const canal = (v: number) => Math.round(v + (alvo - v) * peso);
  const r = canal((n >> 16) & 255);
  const g = canal((n >> 8) & 255);
  const b = canal(n & 255);
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

/** O azul de indicador do design (`design/README.md`): o juro real. */
export const AZUL_DO_JURO_REAL = "#7d9fe0";

/**
 * A cor de cada serie. Prefixados: familia do acento do tema, do mais claro
 * (1 ano) ao mais escuro (10 anos). IPCA+: familia do azul de indicador. Selic:
 * a tinta neutra. Nada de verde, vermelho (direcao de preco) nem ambar (interface).
 */
export function coresDasSeries(acento: string, tintaNeutra: string): Record<IdDaSerie, string> {
  return {
    selic: tintaNeutra,
    pre_1a: misturar(acento, 0.5),
    pre_2a: misturar(acento, 0.25),
    pre_5a: acento,
    pre_10a: misturar(acento, -0.4),
    ipca_5a: misturar(AZUL_DO_JURO_REAL, 0.45),
    ipca_10a: AZUL_DO_JURO_REAL,
  };
}

/** Lembra a escolha dos chips entre visitas; qualquer falha de armazenamento e ignorada. */
export const CHAVE_DAS_SERIES = "vs:juros-series";

export function lerEscolha(bruto: string | null): Set<IdDaSerie> {
  if (bruto === null) return ligadasAoAbrir();
  try {
    const lista: unknown = JSON.parse(bruto);
    if (!Array.isArray(lista)) return ligadasAoAbrir();
    const validos = new Set(SERIES.map((s) => s.id as string));
    const ids = lista.filter((x): x is IdDaSerie => typeof x === "string" && validos.has(x));
    // Tudo desligado e uma escolha valida (grafico vazio), mas uma lista vazia
    // vinda de armazenamento corrompido nao deve deixar a tela em branco.
    return ids.length > 0 ? new Set(ids) : ligadasAoAbrir();
  } catch {
    return ligadasAoAbrir();
  }
}

/**
 * Os pontos da serie em trechos contiguos: cada trecho e uma sequencia de
 * semanas seguidas COM valor.
 *
 * O grafico desenha um trecho por linha, e nao um ponto vazio entre eles: o
 * lightweight-charts liga com uma reta o que existe antes e depois de um ponto
 * vazio, e o Pre de 10 anos, por exemplo, nao existe em anos inteiros (nos anos
 * em que o titulo prefixado mais longo do Tesouro tem menos de 10 anos). Uma
 * reta ali seria uma taxa que ninguem observou.
 */
export function trechos(historico: HistoricoDeJuros, id: IdDaSerie): PontoDaSerie[][] {
  const saida: PontoDaSerie[][] = [];
  let atual: PontoDaSerie[] = [];
  historico.semanas.forEach((semana, i) => {
    const v = historico.taxas[id][i];
    if (v === null || v === undefined) {
      if (atual.length > 0) saida.push(atual);
      atual = [];
    } else {
      atual.push({ time: semana, value: v });
    }
  });
  if (atual.length > 0) saida.push(atual);
  return saida;
}
