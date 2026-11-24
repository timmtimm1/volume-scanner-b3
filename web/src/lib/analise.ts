/**
 * A aba Analise: cada cripto contra o Bitcoin, ano a ano e mes a mes.
 *
 * So funcoes puras e tipos, sem banco nem React: a leitura mora em
 * `analise-dados.ts` e as telas so desenham o que sai daqui.
 *
 * "Contra o BTC" (relativo) = (1 + retorno) / (1 + retorno do BTC) - 1: se voce
 * tivesse trocado 1 BTC pela moeda no comeco do periodo, quanto a mais (ou a
 * menos) de BTC teria no fim. Positivo = mais forte que o Bitcoin.
 *
 * Nota: nao importa `./formato`. O teste roda no Node puro (strip-types), que
 * nao resolve import sem extensao; o unico formato que precisamos e o do
 * percentual curto, entao ele vive aqui, com o mesmo estilo do `percentual`.
 */

export const BTC = "BTC";

export type Fonte = "binance" | "kraken" | "binance+kraken" | string;

export type MoedaDaAnalise = {
  moeda: string;
  fonte: Fonte;
  negociando: boolean;
  primeiroDia: string;
  ultimoDia: string;
  volume12m: number | null;
  noTop: boolean;
};

export type LinhaAnual = {
  moeda: string;
  /** 0 = o periodo todo (o trecho continuo mais recente da moeda). */
  ano: number;
  inicio: string;
  fim: string;
  parcial: boolean;
  retorno: number | null;
  retornoBtc: number | null;
  relativo: number | null;
  beta: number | null;
  correlacao: number | null;
  dias: number;
};

export type LinhaMensal = {
  moeda: string;
  /** Primeiro dia do mes, AAAA-MM-DD. */
  mes: string;
  inicio: string;
  fim: string;
  parcial: boolean;
  retorno: number | null;
  retornoBtc: number | null;
  relativo: number | null;
};

export type PontoMovel = {
  dia: string;
  beta: number | null;
  correlacao: number | null;
  dias: number;
};

/** O que a tabela precisa de um ano (ou do periodo todo) de uma moeda. */
export type CelulaAnual = {
  relativo: number | null;
  retorno: number | null;
  retornoBtc: number | null;
  parcial: boolean;
  inicio: string;
  fim: string;
  /** So no periodo todo. */
  beta?: number | null;
  correlacao?: number | null;
};

export type LinhaDaTabela = {
  moeda: string;
  negociando: boolean;
  noTop: boolean;
  volume12m: number | null;
  porAno: Record<number, CelulaAnual>;
  total: CelulaAnual | null;
};

export type Grupo = "todas" | "negociando" | "top50";
export type Sentido = "asc" | "desc";
export type ChaveDeOrdem = "volume" | "total" | "beta" | "correlacao" | number;

/** 4 algarismos significativos bastam e encolhem o que vai para o navegador. */
const enxuto = (v: number | null): number | null =>
  v === null || !Number.isFinite(v) ? null : Number(v.toPrecision(4));

function celula(l: LinhaAnual, comRisco: boolean): CelulaAnual {
  const c: CelulaAnual = {
    relativo: enxuto(l.relativo),
    retorno: enxuto(l.retorno),
    retornoBtc: enxuto(l.retornoBtc),
    parcial: l.parcial,
    inicio: l.inicio,
    fim: l.fim,
  };
  if (comRisco) {
    c.beta = enxuto(l.beta);
    c.correlacao = enxuto(l.correlacao);
  }
  return c;
}

/**
 * Junta as linhas anuais de cada moeda numa linha de tabela. `anos` vem do mais
 * novo para o mais antigo e nao inclui o 0 (periodo todo, que vira `total`).
 */
export function montarTabela(
  moedas: MoedaDaAnalise[],
  anuais: LinhaAnual[],
): { anos: number[]; linhas: LinhaDaTabela[] } {
  const porMoeda = new Map<string, LinhaDaTabela>();
  const anos = new Set<number>();
  const linhas: LinhaDaTabela[] = moedas.map((m) => {
    const linha: LinhaDaTabela = {
      moeda: m.moeda,
      negociando: m.negociando,
      noTop: m.noTop,
      volume12m: enxuto(m.volume12m),
      porAno: {},
      total: null,
    };
    porMoeda.set(m.moeda, linha);
    return linha;
  });
  for (const a of anuais) {
    const linha = porMoeda.get(a.moeda);
    if (!linha) continue;
    if (a.ano === 0) {
      linha.total = celula(a, true);
    } else {
      linha.porAno[a.ano] = celula(a, false);
      anos.add(a.ano);
    }
  }
  return { anos: [...anos].sort((x, y) => y - x), linhas };
}

/** Busca por pedaco do nome e grupo. O BTC e a regua: nunca sai da lista. */
export function filtrarLinhas<T extends { moeda: string; negociando: boolean; noTop: boolean }>(
  linhas: T[],
  { busca, grupo }: { busca: string; grupo: Grupo },
): T[] {
  const q = busca.trim().toLowerCase();
  return linhas.filter((l) => {
    if (l.moeda === BTC) return true;
    if (grupo === "negociando" && !l.negociando) return false;
    if (grupo === "top50" && !l.noTop) return false;
    return q === "" || l.moeda.toLowerCase().includes(q);
  });
}

function valorDeOrdem(l: LinhaDaTabela, chave: ChaveDeOrdem): number | null {
  const v =
    chave === "volume"
      ? l.volume12m
      : chave === "total"
        ? (l.total?.relativo ?? null)
        : chave === "beta"
          ? (l.total?.beta ?? null)
          : chave === "correlacao"
            ? (l.total?.correlacao ?? null)
            : (l.porAno[chave]?.relativo ?? null);
  return v === null || v === undefined || !Number.isFinite(v) ? null : v;
}

/**
 * Ordena sem mexer na lista original. Quem nao tem o valor fica por ultimo nos
 * dois sentidos, e o BTC fica sempre em primeiro.
 */
export function ordenarLinhas(
  linhas: LinhaDaTabela[],
  chave: ChaveDeOrdem,
  sentido: Sentido,
): LinhaDaTabela[] {
  const f = sentido === "desc" ? -1 : 1;
  return [...linhas].sort((a, b) => {
    if (a.moeda === BTC && b.moeda !== BTC) return -1;
    if (b.moeda === BTC && a.moeda !== BTC) return 1;
    const va = valorDeOrdem(a, chave);
    const vb = valorDeOrdem(b, chave);
    if (va === null && vb === null) return 0;
    if (va === null) return 1;
    if (vb === null) return -1;
    return (va - vb) * f;
  });
}

export type MesDoAno = { mes: number; mediana: number | null; positivos: number; meses: number };

function mediana(valores: number[]): number | null {
  if (valores.length === 0) return null;
  const s = [...valores].sort((a, b) => a - b);
  const meio = s.length >> 1;
  return s.length % 2 === 1 ? s[meio] : (s[meio - 1] + s[meio]) / 2;
}

/** Numero do mes (1..12) de um AAAA-MM-DD, sem passar por Date. */
export const numeroDoMes = (iso: string): number => Number(iso.slice(5, 7));
export const anoDoMes = (iso: string): number => Number(iso.slice(0, 4));

/**
 * Como a moeda costuma se sair em cada mes do calendario. Mediana, nao media:
 * um mes maluco nao puxa a conta. Mes incompleto fica de fora.
 */
export function sazonalidade(mensais: LinhaMensal[], campo: "relativo" | "retorno"): MesDoAno[] {
  const porMes: number[][] = Array.from({ length: 12 }, () => []);
  for (const m of mensais) {
    if (m.parcial) continue;
    const v = m[campo];
    if (v === null || v === undefined || !Number.isFinite(v)) continue;
    const n = numeroDoMes(m.mes);
    if (n >= 1 && n <= 12) porMes[n - 1].push(v);
  }
  return porMes.map((vs, i) => ({
    mes: i + 1,
    mediana: mediana(vs),
    positivos: vs.filter((v) => v > 0).length,
    meses: vs.length,
  }));
}

export type MapaMensal = {
  anos: number[];
  celula: (ano: number, mes: number) => LinhaMensal | undefined;
};

export function mapaMensal(mensais: LinhaMensal[]): MapaMensal {
  const por = new Map<string, LinhaMensal>();
  const anos = new Set<number>();
  for (const m of mensais) {
    const ano = anoDoMes(m.mes);
    por.set(`${ano}-${numeroDoMes(m.mes)}`, m);
    anos.add(ano);
  }
  return {
    anos: [...anos].sort((a, b) => b - a),
    celula: (ano, mes) => por.get(`${ano}-${mes}`),
  };
}

export type Escala = "ano" | "mes";

const LIMITES: Record<Escala, readonly number[]> = {
  ano: [0.05, 0.15, 0.35, 0.75],
  mes: [0.02, 0.05, 0.1, 0.2],
};

/** 0 (quase nada) a 4 (muito forte), pelo tamanho do numero, sem olhar o sinal. */
export function nivelDeCor(v: number | null | undefined, escala: Escala): number {
  if (v === null || v === undefined || !Number.isFinite(v)) return 0;
  const m = Math.abs(v);
  const limites = LIMITES[escala];
  let nivel = 0;
  for (const l of limites) if (m >= l) nivel += 1;
  return nivel;
}

const FORCA = [0, 14, 26, 40, 56];

/** O fundo da celula: verde para quem ganhou do BTC, vermelho para quem perdeu. */
export function corDaCelula(v: number | null | undefined, escala: Escala): string {
  const nivel = nivelDeCor(v, escala);
  if (nivel === 0 || v === null || v === undefined) return "transparent";
  const cor = v > 0 ? "var(--alta)" : "var(--baixa)";
  return `color-mix(in srgb, ${cor} ${FORCA[nivel]}%, transparent)`;
}

const nf = (casas: number) =>
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

/**
 * Percentual curto para caber na celula: 1 casa abaixo de 10%, nenhuma de 10%
 * para cima ("+4,2%", "−45%", "+10.750%"). Quem arredonda para zero fica sem
 * sinal ("0,0%"): "−0,0%" so confunde.
 */
export function pctCurto(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  // Perda de 99,5% a 99,99...%: com zero casas viraria "−100%", que e perder
  // tudo. So a perda total mostra 100; o resto ganha casas e para em 99,99.
  if (v > -1 && v <= -0.995) {
    return `−${nf(2).format(Math.min(Math.abs(v) * 100, 99.99))}%`;
  }
  const casas = Math.abs(v) < 0.1 ? 1 : 0;
  const texto = nf(casas).format(Math.abs(v) * 100);
  if (Number(texto.replace(/\./g, "").replace(",", ".")) === 0) return `${texto}%`;
  return `${v >= 0 ? "+" : "−"}${texto}%`;
}

// ---------------------------------------------------------------------------
// Sazonalidade: a mediana de cada mes do calendario, ao longo dos anos.
// ---------------------------------------------------------------------------

/** Menos anos completos que isso num mes e pouco para falar em "estacao". */
export const MINIMO_DE_ANOS = 3;

/** Um mes do calendario (jan..dez) de uma moeda, ou do mercado, ao longo dos anos. */
export type CelulaSazonal = {
  retorno: number | null;
  relativo: number | null;
  /** Em quantos anos o mes fechou em alta (retorno > 0). */
  subiu: number;
  /** Em quantos anos o mes ganhou do BTC (relativo > 0). */
  ganhou: number;
  /** Quantos anos completos entraram na conta. */
  anos: number;
};

export type LinhaSazonal = {
  moeda: string;
  negociando: boolean;
  noTop: boolean;
  volume12m: number | null;
  /** Meses de 1 a 12. */
  porMes: Record<number, CelulaSazonal>;
};

export type MesSazonal = {
  moeda: string;
  mes: number;
  retorno: number | null;
  relativo: number | null;
  subiu: number;
  ganhou: number;
  anos: number;
};

export type ModoSazonal = "retorno" | "relativo";

/** Uma celula do banco, com os numeros em 4 algarismos significativos. */
export function celulaSazonal(m: Omit<MesSazonal, "moeda" | "mes">): CelulaSazonal {
  return {
    retorno: enxuto(m.retorno),
    relativo: enxuto(m.relativo),
    subiu: Number(m.subiu),
    ganhou: Number(m.ganhou),
    anos: Number(m.anos),
  };
}

/** Junta as medianas mensais de cada moeda numa linha da tabela de sazonalidade. */
export function montarSazonalidade(moedas: MoedaDaAnalise[], meses: MesSazonal[]): LinhaSazonal[] {
  const porMoeda = new Map<string, LinhaSazonal>();
  const linhas = moedas.map((m) => {
    const linha: LinhaSazonal = {
      moeda: m.moeda,
      negociando: m.negociando,
      noTop: m.noTop,
      volume12m: enxuto(m.volume12m),
      porMes: {},
    };
    porMoeda.set(m.moeda, linha);
    return linha;
  });
  for (const x of meses) {
    const linha = porMoeda.get(x.moeda);
    if (!linha || x.mes < 1 || x.mes > 12) continue;
    linha.porMes[x.mes] = celulaSazonal(x);
  }
  return linhas;
}

export type ChaveSazonal = "volume" | number;

/** O valor de ordem de um mes, ou `null` se faltam anos ou dado. */
function valorSazonal(l: LinhaSazonal, mes: number, modo: ModoSazonal): number | null {
  const c = l.porMes[mes];
  if (!c || c.anos < MINIMO_DE_ANOS) return null;
  const v = c[modo];
  return v === null || v === undefined || !Number.isFinite(v) ? null : v;
}

/**
 * Ordena sem mexer na lista original. Por mes: pela mediana do modo escolhido;
 * quem tem menos de `MINIMO_DE_ANOS` anos (ou nao tem o valor) fica por ultimo
 * nos dois sentidos. O BTC fica sempre em primeiro.
 */
export function ordenarSazonalidade(
  linhas: LinhaSazonal[],
  chave: ChaveSazonal,
  modo: ModoSazonal,
  sentido: Sentido,
): LinhaSazonal[] {
  const f = sentido === "desc" ? -1 : 1;
  const valor = (l: LinhaSazonal): number | null => {
    if (chave === "volume") {
      const v = l.volume12m;
      return v === null || !Number.isFinite(v) ? null : v;
    }
    return valorSazonal(l, chave, modo);
  };
  return [...linhas].sort((a, b) => {
    if (a.moeda === BTC && b.moeda !== BTC) return -1;
    if (b.moeda === BTC && a.moeda !== BTC) return 1;
    const va = valor(a);
    const vb = valor(b);
    if (va === null && vb === null) return 0;
    if (va === null) return 1;
    if (vb === null) return -1;
    return (va - vb) * f;
  });
}

// ---------------------------------------------------------------------------
// Rankings: beta e correlacao contra o BTC em tres periodos.
// ---------------------------------------------------------------------------

export type Periodo = "90d" | "ano" | "total";
export type MetricaDoRanking = "beta" | "correlacao";

export type CandidatoAoRanking = {
  moeda: string;
  beta90: number | null;
  correlacao90: number | null;
  dias90: number | null;
  betaAno: number | null;
  correlacaoAno: number | null;
  diasAno: number | null;
  betaTotal: number | null;
  correlacaoTotal: number | null;
  diasTotal: number | null;
  /** Primeiro dia do trecho do periodo todo. */
  desde: string | null;
};

export type ItemDoRanking = {
  moeda: string;
  valor: number;
  /** A outra metrica do mesmo periodo (correlacao no ranking de beta e vice-versa). */
  outro: number | null;
  dias: number | null;
};

const finito = (v: number | null | undefined): v is number =>
  v !== null && v !== undefined && Number.isFinite(v);

function doPeriodo(c: CandidatoAoRanking, p: Periodo) {
  return p === "90d"
    ? { beta: c.beta90, correlacao: c.correlacao90, dias: c.dias90 }
    : p === "ano"
      ? { beta: c.betaAno, correlacao: c.correlacaoAno, dias: c.diasAno }
      : { beta: c.betaTotal, correlacao: c.correlacaoTotal, dias: c.diasTotal };
}

/**
 * As `n` primeiras do ranking. Beta: do maior para o menor. Correlacao: do
 * MENOR para o maior (a que anda mais sozinha primeiro; pode ser negativa).
 * Sem valor, e o BTC, ficam de fora; empate se resolve pelo nome.
 */
export function rankear(
  candidatos: CandidatoAoRanking[],
  periodo: Periodo,
  chave: MetricaDoRanking,
  n = 15,
): ItemDoRanking[] {
  const outraChave: MetricaDoRanking = chave === "beta" ? "correlacao" : "beta";
  const itens: ItemDoRanking[] = [];
  for (const c of candidatos) {
    if (c.moeda === BTC) continue;
    const p = doPeriodo(c, periodo);
    const valor = p[chave];
    if (!finito(valor)) continue;
    const outro = p[outraChave];
    itens.push({ moeda: c.moeda, valor, outro: finito(outro) ? outro : null, dias: p.dias ?? null });
  }
  const f = chave === "beta" ? -1 : 1;
  itens.sort((a, b) => (a.valor - b.valor) * f || a.moeda.localeCompare(b.moeda));
  return itens.slice(0, n);
}
