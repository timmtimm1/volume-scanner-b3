/**
 * Suportes e resistencias da ficha, prontos para virar linha no grafico.
 *
 * Mesma leitura do Laboratorio de Suportes: pontilhado antes do 3o toque
 * (`valeDesde`), cheio depois; tracejado no nivel que trocou de papel; mais
 * grosso enquanto ainda vale. Cada trecho e recortado aos pregoes que o
 * grafico tem, para a linha nao criar datas que nao existem nele.
 *
 * Sem React nem DOM, para os testes rodarem no Node.
 */

import type { NivelDoGrafico } from "./types";

export type Estilo = "cheio" | "pontilhado" | "tracejado";

export type TrechoDeNivel = {
  lado: "suporte" | "resistencia";
  preco: number;
  de: string;
  ate: string;
  estilo: Estilo;
  largura: 1 | 2;
};

/** Primeiro pregao do grafico em ou depois de `dia` (null se nao ha). */
function aPartirDe(datas: string[], dia: string): string | null {
  return datas.find((d) => d >= dia) ?? null;
}

/** Ultimo pregao do grafico em ou antes de `dia` (null se nao ha). */
function ateAo(datas: string[], dia: string): string | null {
  for (let i = datas.length - 1; i >= 0; i--) if (datas[i] <= dia) return datas[i];
  return null;
}

export function trechosDosNiveis(niveis: NivelDoGrafico[], datas: string[]): TrechoDeNivel[] {
  const trechos: TrechoDeNivel[] = [];
  for (const n of niveis) {
    const de = aPartirDe(datas, n.de);
    const ate = ateAo(datas, n.ate);
    if (de === null || ate === null || ate <= de) continue;
    const forte: 1 | 2 = n.ativo ? 2 : 1;
    const base = { lado: n.lado, preco: n.preco };
    if (n.virou) {
      trechos.push({ ...base, de, ate, estilo: "tracejado", largura: forte });
      continue;
    }
    const vale = n.valeDesde === null ? null : aPartirDe(datas, n.valeDesde);
    if (vale === null || vale > ate) {
      trechos.push({ ...base, de, ate, estilo: "pontilhado", largura: 1 });
      continue;
    }
    if (vale > de) trechos.push({ ...base, de, ate: vale, estilo: "pontilhado", largura: 1 });
    if (ate > vale) trechos.push({ ...base, de: vale, ate, estilo: "cheio", largura: forte });
  }
  return trechos;
}
