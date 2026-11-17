/**
 * Tendencia de um ativo pelas medias que o usuario escolher (pedido de 17/11/2026).
 *
 * O pipeline grava, para o ultimo pregao, se cada media esta subindo (+1),
 * caindo (-1) ou sem historico (0) -- `scanner/tendencia.py`, tabela
 * `tendencias`. Aqui so a combinacao: alta = todas as escolhidas subindo,
 * baixa = todas caindo, lateral = discordam. Media sem historico deixa o
 * ativo fora das tres (null). E descricao do grafico, nao previsao.
 *
 * Modulo puro: sem import de runtime, testado com `node --experimental-strip-types`.
 */

export const PERIODOS = [9, 20, 50, 80, 200] as const;
export type Periodo = (typeof PERIODOS)[number];
export type TipoDeMedia = "MME" | "MMA";
export type Inclinacao = -1 | 0 | 1;
export type ColunaDeMedia = `${"mme" | "mma"}${Periodo}`;
export type Inclinacoes = Record<ColunaDeMedia, Inclinacao>;

export type EscolhaDeMedias = { tipo: TipoDeMedia; periodos: Periodo[] };
export type Estado = "alta" | "lateral" | "baixa";
export const ESTADOS: readonly Estado[] = ["alta", "lateral", "baixa"];

/**
 * O ponto de partida: MME 9 + MME 80. No estudo de 17/11/2026 sobre os trades
 * do backtest, a direcao da MME 9 foi a que mais separou o resultado dos
 * setups nos dois mercados, e a 80 junta a direcao do medio prazo.
 */
export const ESCOLHA_PADRAO: EscolhaDeMedias = { tipo: "MME", periodos: [9, 80] };

/** Com quantos pregoes atras cada media e comparada (o mesmo do Python). */
export const INCLINACAO: Record<Periodo, number> = { 9: 1, 20: 5, 50: 10, 80: 20, 200: 20 };

export function coluna(tipo: TipoDeMedia, periodo: Periodo): ColunaDeMedia {
  return `${tipo === "MME" ? "mme" : "mma"}${periodo}`;
}

/** Alta, lateral ou baixa pelas medias escolhidas; null sem historico em alguma delas. */
export function classificar(inc: Inclinacoes, escolha: EscolhaDeMedias): Estado | null {
  if (escolha.periodos.length === 0) return null;
  const v = escolha.periodos.map((p) => inc[coluna(escolha.tipo, p)]);
  if (v.some((x) => x === 0)) return null;
  if (v.every((x) => x === 1)) return "alta";
  if (v.every((x) => x === -1)) return "baixa";
  return "lateral";
}

/** Quantos ativos em cada estado (e sem historico) pela escolha. */
export function contar<T extends { inclinacoes: Inclinacoes }>(
  linhas: readonly T[],
  escolha: EscolhaDeMedias,
): Record<Estado | "sem", number> {
  const n = { alta: 0, lateral: 0, baixa: 0, sem: 0 };
  for (const l of linhas) n[classificar(l.inclinacoes, escolha) ?? "sem"]++;
  return n;
}

/** Liga ou desliga uma media; a ultima nao desliga (sem media nao ha tendencia). */
export function alternar(escolha: EscolhaDeMedias, periodo: Periodo): EscolhaDeMedias {
  const tem = escolha.periodos.includes(periodo);
  if (tem && escolha.periodos.length === 1) return escolha;
  const periodos = tem
    ? escolha.periodos.filter((p) => p !== periodo)
    : PERIODOS.filter((p) => p === periodo || escolha.periodos.includes(p));
  return { ...escolha, periodos: [...periodos] };
}

/** "MME 9 + 80" */
export function nomeDaEscolha(escolha: EscolhaDeMedias): string {
  return `${escolha.tipo} ${escolha.periodos.join(" + ")}`;
}

/**
 * Le a escolha guardada no navegador; qualquer coisa fora do formato volta ao
 * padrao (o texto vem do localStorage, que o usuario pode ter mexido).
 */
export function escolhaDoTexto(texto: string | null): { escolha: EscolhaDeMedias; estado: Estado } {
  const padrao = { escolha: ESCOLHA_PADRAO, estado: "alta" as Estado };
  if (!texto) return padrao;
  try {
    const d = JSON.parse(texto) as { tipo?: unknown; periodos?: unknown; estado?: unknown };
    const tipo = d.tipo === "MMA" ? "MMA" : d.tipo === "MME" ? "MME" : null;
    const periodos = Array.isArray(d.periodos)
      ? PERIODOS.filter((p) => (d.periodos as unknown[]).includes(p))
      : [];
    const estado = ESTADOS.includes(d.estado as Estado) ? (d.estado as Estado) : "alta";
    if (!tipo || periodos.length === 0) return { ...padrao, estado };
    return { escolha: { tipo, periodos: [...periodos] }, estado };
  } catch {
    return padrao;
  }
}
