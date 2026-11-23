/**
 * A evolucao do patrimonio em cripto (pedido de 23/11/2026), em dolar:
 *
 *   patrimonio do dia = capital + resultado de todos os trades naquele dia
 *
 * O resultado de cada trade ja soma o realizado e o que esta em aberto. Trade
 * encerrado continua contando com o resultado final, senao o patrimonio cairia
 * no dia seguinte ao fechamento.
 *
 * So contas, sem rede e sem import de valor: os testes rodam este arquivo no Node.
 */

export type OperacaoDaCurva = {
  data: string;
  quantidadeApos: number;
  realizadoApos: number;
};

export type TradeDaCurva = {
  id: number;
  /** Em ordem crescente de (data, id). */
  operacoes: readonly OperacaoDaCurva[];
  /** Fechamento de cada dia marcado, em ordem crescente de data. */
  snapshots: readonly { data: string; resultado: number }[];
  /** Resultado marcado no preco de agora; so para trade aberto. */
  resultadoAgora?: number | null;
};

export type PontoDoPatrimonio = {
  dia: string;
  patrimonio: number;
  /** Lucro ou prejuizo ja fechado. */
  realizado: number;
  /** Resultado das posicoes ainda abertas. */
  aberto: number;
};

export type ResumoDoPatrimonio = {
  capital: number;
  atual: number;
  resultado: number;
  resultadoPct: number;
  realizado: number;
  aberto: number;
  /** A maior queda de um topo ate um fundo, em dolar (zero ou negativa). */
  maiorQueda: number;
  maiorQuedaPct: number;
};

const r2 = (v: number) => Math.round(v * 100) / 100;

function diaSeguinte(dia: string): string {
  const d = new Date(`${dia}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

function diaAnterior(dia: string): string {
  const d = new Date(`${dia}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

/** O ultimo item com `data <= dia`; a lista vem em ordem crescente. */
function ultimoAte<T extends { data: string }>(lista: readonly T[], dia: string): T | null {
  let achado: T | null = null;
  for (const item of lista) {
    if (item.data > dia) break;
    achado = item;
  }
  return achado;
}

/**
 * Realizado e resultado total de um trade no fim de `dia`.
 *
 * Vale o snapshot mais recente, a nao ser que exista operacao mais nova que ele:
 * a marcacao so roda a noite, e o trade fechado hoje ja tem de contar hoje.
 */
function noDia(t: TradeDaCurva, dia: string, ehHoje: boolean): { realizado: number; total: number } {
  const op = ultimoAte(t.operacoes, dia);
  if (op === null) return { realizado: 0, total: 0 };
  const realizado = op.realizadoApos;
  if (op.quantidadeApos === 0) return { realizado, total: realizado };
  if (ehHoje && t.resultadoAgora !== undefined && t.resultadoAgora !== null) {
    return { realizado, total: t.resultadoAgora };
  }
  const snap = ultimoAte(t.snapshots, dia);
  return { realizado, total: snap !== null && snap.data >= op.data ? snap.resultado : realizado };
}

/**
 * Um ponto por dia, do dia anterior ao primeiro trade (o capital, o ponto de
 * partida da linha) ate `hoje`. Sem nenhuma operacao, a curva e vazia.
 */
export function montarCurva(
  capital: number,
  trades: readonly TradeDaCurva[],
  hoje: string,
): PontoDoPatrimonio[] {
  const inicios = trades.flatMap((t) => (t.operacoes[0] ? [t.operacoes[0].data] : []));
  if (inicios.length === 0) return [];
  const primeiro = inicios.reduce((a, b) => (a < b ? a : b));
  const ultimo = primeiro > hoje ? primeiro : hoje;

  const curva: PontoDoPatrimonio[] = [
    { dia: diaAnterior(primeiro), patrimonio: r2(capital), realizado: 0, aberto: 0 },
  ];
  for (let dia = primeiro; dia <= ultimo; dia = diaSeguinte(dia)) {
    let realizado = 0;
    let total = 0;
    for (const t of trades) {
      const v = noDia(t, dia, dia === hoje);
      realizado += v.realizado;
      total += v.total;
    }
    curva.push({
      dia,
      patrimonio: r2(capital + total),
      realizado: r2(realizado),
      aberto: r2(total - realizado),
    });
  }
  return curva;
}

/** Os numeros do topo da aba. Sem curva, tudo no capital. */
export function resumirCurva(
  capital: number,
  curva: readonly PontoDoPatrimonio[],
): ResumoDoPatrimonio {
  const fim = curva.at(-1);
  const atual = fim?.patrimonio ?? r2(capital);
  let topo = capital;
  let maiorQueda = 0;
  let maiorQuedaPct = 0;
  for (const p of curva) {
    if (p.patrimonio > topo) topo = p.patrimonio;
    const queda = p.patrimonio - topo;
    if (queda < maiorQueda) {
      maiorQueda = queda;
      maiorQuedaPct = topo > 0 ? queda / topo : 0;
    }
  }
  return {
    capital,
    atual,
    resultado: r2(atual - capital),
    resultadoPct: capital > 0 ? (atual - capital) / capital : 0,
    realizado: fim?.realizado ?? 0,
    aberto: fim?.aberto ?? 0,
    maiorQueda: r2(maiorQueda),
    maiorQuedaPct,
  };
}
