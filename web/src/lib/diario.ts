/**
 * O diario ligado ao setup: risco e resultado em R de cada trade, a estatistica
 * por setup e a validacao dos campos novos (setup e stop). Puro, sem banco.
 *
 * Modulo puro de proposito: sem import de runtime (so tipos), porque e testado
 * com `node --experimental-strip-types`. O que pediria import de valor --
 * `marcarAgora` de `posicao.ts`, a lista de categorias de `config.ts`, a ordem
 * de `setups-tela.ts` -- chega por parametro ou e repetido com um teste que
 * trava a copia.
 *
 * R = resultado total / risco em reais. O risco e o que o trade pedia para
 * perder: soma, sobre as COMPRAS, de `quantidade x (preco - stop)`. Sem stop,
 * ou com alguma compra a preco igual ou abaixo do stop, nao ha R.
 */

export class DiarioInvalido extends Error {}

type OperacaoParaR = { tipo: "compra" | "venda"; quantidade: number; preco: number };

/** O minimo de um trade para a conta de R (o `TradeResumo` serve). */
export type TradeParaR = {
  stop: number | null;
  /** Estado depois da ultima operacao. */
  quantidade: number;
  precoMedio: number;
  realizado: number;
  operacoes: OperacaoParaR[];
};

const r2 = (v: number): number => Math.round((v + Number.EPSILON) * 100) / 100;

/**
 * Quanto o trade arriscava, em reais. Null sem stop ou com alguma compra a
 * preco <= stop (o risco dessa compra nao existe, e o R perde o sentido).
 */
export function riscoEmReais(trade: Pick<TradeParaR, "stop" | "operacoes">): number | null {
  const { stop } = trade;
  if (stop === null || !(stop > 0)) return null;
  let risco = 0;
  let compras = 0;
  for (const op of trade.operacoes) {
    if (op.tipo !== "compra") continue;
    if (!(op.preco > stop)) return null;
    risco += op.quantidade * (op.preco - stop);
    compras++;
  }
  return compras === 0 ? null : r2(risco);
}

/**
 * O resultado do trade em R. `precoAgora` marca o que ainda esta em aberto;
 * null (trade encerrado, ou sem cotacao) vale so o realizado. A conta do
 * resultado e a de `marcarAgora` (posicao.ts): `realizado + quantidade x
 * (preco - precoMedio)`; o teste compara as duas.
 */
export function resultadoEmRDoTrade(trade: TradeParaR, precoAgora: number | null): number | null {
  const risco = riscoEmReais(trade);
  if (risco === null || !(risco > 0)) return null;
  const resultado =
    precoAgora === null
      ? r2(trade.realizado)
      : r2(trade.realizado + trade.quantidade * (precoAgora - trade.precoMedio));
  return resultado / risco;
}

export type TradeParaEstatistica = TradeParaR & {
  encerradoEm: string | null;
  /** Null = sem setup. */
  categoriaSetup: string | null;
};

export type LinhaDeEstatistica = {
  /** Null = "Sem setup". */
  categoria: string | null;
  /** Trades encerrados. */
  encerrados: number;
  /** Dos encerrados, quantos tem stop (e portanto R). */
  comR: number;
  /** Fracao dos que tem R com R > 0; null sem nenhum. */
  acerto: number | null;
  mediaR: number | null;
  somaR: number;
};

/**
 * "Seu resultado por setup": so trades encerrados, uma linha por setup que
 * tem algum, na ordem de `ordem` (fixa, nunca por resultado) e, por ultimo,
 * os sem setup. Trade encerrado sem stop conta nos encerrados mas fica fora
 * das contas de R.
 */
export function estatisticaPorSetup(
  trades: TradeParaEstatistica[],
  ordem: readonly string[],
): LinhaDeEstatistica[] {
  const chaves: (string | null)[] = [...ordem, null];
  const linhas: LinhaDeEstatistica[] = [];
  for (const categoria of chaves) {
    const doSetup = trades.filter((t) => t.encerradoEm !== null && t.categoriaSetup === categoria);
    if (doSetup.length === 0) continue;
    const rs = doSetup
      .map((t) => resultadoEmRDoTrade(t, null))
      .filter((r): r is number => r !== null);
    const soma = rs.reduce((a, r) => a + r, 0);
    linhas.push({
      categoria,
      encerrados: doSetup.length,
      comR: rs.length,
      acerto: rs.length === 0 ? null : rs.filter((r) => r > 0).length / rs.length,
      mediaR: rs.length === 0 ? null : soma / rs.length,
      somaR: soma,
    });
  }
  return linhas;
}

/** Folga do `numeric(12, 2)` da coluna `stop`. */
const STOP_MAXIMO = 1_000_000_000;

export type CamposDoDiario = {
  setupId: number | null;
  categoriaSetup: string | null;
  stop: number | null;
};

const vazio = (v: unknown): boolean => v === undefined || v === null || v === "";

/**
 * Valida os campos novos de um trade (setup, categoria, stop). Todos opcionais:
 * ausente, null ou "" valem "sem". Lanca `DiarioInvalido` com mensagem em
 * portugues. `categoriasValidas` e `CATEGORIAS_DE_SETUP` (parametro, para o
 * modulo seguir puro).
 */
export function validarCamposDoDiario(
  entrada: { setupId?: unknown; categoriaSetup?: unknown; stop?: unknown },
  categoriasValidas: readonly string[],
): CamposDoDiario {
  let setupId: number | null = null;
  if (!vazio(entrada.setupId)) {
    const n = Number(entrada.setupId);
    if (!Number.isInteger(n) || n <= 0) throw new DiarioInvalido("setup invalido");
    setupId = n;
  }

  let categoriaSetup: string | null = null;
  if (!vazio(entrada.categoriaSetup)) {
    const c = entrada.categoriaSetup;
    if (typeof c !== "string" || !categoriasValidas.includes(c)) {
      throw new DiarioInvalido("setup desconhecido");
    }
    categoriaSetup = c;
  }

  let stop: number | null = null;
  if (!vazio(entrada.stop)) {
    const n = Number(entrada.stop);
    if (!Number.isFinite(n) || n <= 0) throw new DiarioInvalido("o stop tem de ser um numero positivo");
    if (n > STOP_MAXIMO) throw new DiarioInvalido("o stop esta grande demais");
    if (Math.abs(n - r2(n)) >= 1e-9) throw new DiarioInvalido("o stop aceita no maximo 2 casas decimais");
    stop = r2(n);
  }

  return { setupId, categoriaSetup, stop };
}
