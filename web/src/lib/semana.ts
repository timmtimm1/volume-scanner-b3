/**
 * Logica pura da aba Semana: nada de React, nada de banco.
 *
 * Fica separada para ter teste (`semana.test.mjs`). Importa so TIPOS: o teste
 * roda sob `node --experimental-strip-types`, que nao resolve o alias `@/`.
 */

import type { AcaoDaSemana, BlocoComErro, EdicaoDaSemana, EventoDaAgenda } from "./types";

/** A sexta-feira da rota: AAAA-MM-DD e uma data que existe no calendario. */
export function sextaValida(texto: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(texto)) return false;
  const [a, m, d] = texto.split("-").map(Number);
  const dt = new Date(Date.UTC(a, m - 1, d));
  return dt.getUTCFullYear() === a && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

/** O bloco veio como `{ erro }`: a fonte caiu na montagem. */
export function ehErro<T extends object>(bloco: T | BlocoComErro): bloco is BlocoComErro {
  return typeof bloco === "object" && bloco !== null && "erro" in bloco;
}

const DIAS = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

/** Dia da semana abreviado de uma data ISO, sem passar pelo fuso do servidor. */
export function diaAbreviado(iso: string): string {
  const [a, m, d] = iso.split("-").map(Number);
  return DIAS[new Date(Date.UTC(a, m - 1, d)).getUTCDay()];
}

/** `qui 22/10`. */
export function diaComSemana(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${diaAbreviado(iso)} ${d}/${m}`;
}

/**
 * `13 a 16/10/2026`: do primeiro ao ultimo pregao da semana. Mesmo formato do
 * Telegram (`_periodo` em mensagem.py). Sem pregao na lista, cai no `fim`.
 */
export function periodoDaSemana(pregoes: string[], fim: string): string {
  const lista = pregoes.length > 0 ? pregoes : [fim];
  const primeiro = lista[0].split("-");
  const ultimo = lista[lista.length - 1].split("-");
  const completo = `${ultimo[2]}/${ultimo[1]}/${ultimo[0]}`;
  if (lista.length === 1 || lista[0] === lista[lista.length - 1]) return completo;
  if (primeiro[0] === ultimo[0] && primeiro[1] === ultimo[1]) {
    return `${Number(primeiro[2])} a ${completo}`;
  }
  if (primeiro[0] === ultimo[0]) return `${primeiro[2]}/${primeiro[1]} a ${completo}`;
  return `${primeiro[2]}/${primeiro[1]}/${primeiro[0]} a ${completo}`;
}

const FUSO = "America/Sao_Paulo";

function partesEmBrasilia(iso: string): Record<string, string> {
  const fmt = new Intl.DateTimeFormat("pt-BR", {
    timeZone: FUSO,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const partes: Record<string, string> = {};
  for (const p of fmt.formatToParts(new Date(iso))) partes[p.type] = p.value;
  return partes;
}

/** A data de calendario de um instante, em Brasilia: AAAA-MM-DD. */
export function diaEmBrasilia(iso: string): string {
  const p = partesEmBrasilia(iso);
  return `${p.year}-${p.month}-${p.day}`;
}

/** `sáb 17/10 às 08:31`, horario de Brasilia. */
export function instanteEmBrasilia(iso: string): string {
  const p = partesEmBrasilia(iso);
  return `${diaComSemana(`${p.year}-${p.month}-${p.day}`)} às ${p.hour}:${p.minute}`;
}

/** As edicoes vizinhas. A lista vem da mais recente para a mais antiga. */
export function vizinhas(
  edicoes: EdicaoDaSemana[],
  sexta: string,
): { anterior: string | null; seguinte: string | null } {
  const i = edicoes.findIndex((e) => e.sexta === sexta);
  if (i < 0) return { anterior: null, seguinte: null };
  return {
    anterior: edicoes[i + 1]?.sexta ?? null,
    seguinte: i > 0 ? edicoes[i - 1].sexta : null,
  };
}

/** A agenda agrupada por dia, em ordem; dentro do dia, por hora (sem hora por ultimo). */
export function agruparAgenda(
  agenda: EventoDaAgenda[],
): { data: string; eventos: EventoDaAgenda[] }[] {
  const ordenada = [...agenda].sort(
    (a, b) =>
      a.data.localeCompare(b.data) ||
      (a.hora ?? "99:99").localeCompare(b.hora ?? "99:99") ||
      a.pais.localeCompare(b.pais) ||
      a.evento.localeCompare(b.evento),
  );
  const grupos: { data: string; eventos: EventoDaAgenda[] }[] = [];
  for (const e of ordenada) {
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && ultimo.data === e.data) ultimo.eventos.push(e);
    else grupos.push({ data: e.data, eventos: [e] });
  }
  return grupos;
}

const nf = (casas: number) =>
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

/** Pontos-base com sinal: `+34,4 bp`, `−5,0 bp`. Zero arredondado vira `0,0 bp`. */
export function pontosBase(v: number | null | undefined, casas = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const r = Number(v.toFixed(casas));
  if (r === 0) return `${nf(casas).format(0)} bp`;
  return `${r > 0 ? "+" : "−"}${nf(casas).format(Math.abs(r))} bp`;
}

/** `3 Mo` -> `3 meses`, `10 Yr` -> `10 anos`. Texto desconhecido passa como veio. */
export function prazoDoTreasury(prazo: string): string {
  const m = /^(\d+)\s*(Mo|Yr)$/.exec(prazo.trim());
  if (!m) return prazo;
  const n = Number(m[1]);
  if (m[2] === "Mo") return n === 1 ? "1 mês" : `${n} meses`;
  return n === 1 ? "1 ano" : `${n} anos`;
}

/** `1 ano`, `10 anos`: o vertice da curva prefixada. */
export function prazoEmAnos(anos: number): string {
  return anos === 1 ? "1 ano" : `${nf(0).format(anos)} anos`;
}

/** `set/2026` a partir de `2026-09`. */
export function mesDeReferencia(ym: string): string {
  const [a, m] = ym.split("-");
  const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  return `${MESES[Number(m) - 1] ?? m}/${a}`;
}

/** Fator de acoes sem zeros a direita: 2 -> `2`, 1.03 -> `1,03`. */
function fator(v: number): string {
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 }).format(v);
}

/**
 * O que o ajuste fez no papel, em palavras: o preco andou X, houve provento
 * de R$ Y e/ou as acoes foram multiplicadas por Z. `null` quando nao ha ajuste.
 */
export function detalheDoAjuste(a: AcaoDaSemana): string | null {
  if (!a.ajustado) return null;
  const partes: string[] = [];
  const bruta = Number((a.variacao_bruta * 100).toFixed(1));
  partes.push(`variação de preço ${bruta < 0 ? "−" : bruta > 0 ? "+" : ""}${nf(1).format(Math.abs(bruta))}%`);
  if (a.proventos_por_acao > 0) {
    partes.push(`proventos de R$ ${new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(a.proventos_por_acao)}`);
  }
  if (a.multiplicador !== 1) partes.push(`ações ×${fator(a.multiplicador)}`);
  return partes.join("; ");
}

const MOTIVOS_DE_DESCARTE: Record<string, (n: number) => string> = {
  fora_da_imprensa: (n) => `${n} de sites fora da imprensa`,
  boletim_diario: (n) => (n === 1 ? "1 boletim diário" : `${n} boletins diários`),
  fora_da_semana: (n) => `${n} fora da semana`,
  nao_e_noticia: (n) => (n === 1 ? "1 não era notícia" : `${n} não eram notícia`),
};

/** Os descartes das noticias em linguagem de gente, do maior para o menor. */
export function descartesEmTexto(descartes: Record<string, number>): {
  total: number;
  partes: string[];
} {
  const itens = Object.entries(descartes)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  return {
    total: itens.reduce((soma, [, n]) => soma + n, 0),
    partes: itens.map(([motivo, n]) => (MOTIVOS_DE_DESCARTE[motivo] ?? ((x: number) => `${x} (${motivo})`))(n)),
  };
}

/**
 * Alta e so quem subiu; queda, so quem caiu. Ate 18/10/2026 a montagem
 * completava a lista de altas com quedas quando poucos subiam (a edicao de
 * 16/10 tem WBT e BCH caindo em "Maiores altas"). A tela filtra ao mostrar,
 * entao as edicoes ja gravadas tambem aparecem certas.
 */
export function soQuemSubiu<T>(itens: T[], variacao: (item: T) => number | null | undefined): T[] {
  return itens.filter((item) => (variacao(item) ?? 0) > 0);
}

export function soQuemCaiu<T>(itens: T[], variacao: (item: T) => number | null | undefined): T[] {
  return itens.filter((item) => (variacao(item) ?? 0) < 0);
}

/** Os tickers que a tela vai ligar a um nome de empresa. */
export function tickersDasAcoes(acoes: {
  altas: AcaoDaSemana[];
  quedas: AcaoDaSemana[];
  fora_do_ranking: AcaoDaSemana[];
}): string[] {
  return [
    ...new Set([...acoes.altas, ...acoes.quedas, ...acoes.fora_do_ranking].map((a) => a.ticker)),
  ];
}
