/**
 * O que muda na tela de um mercado para o outro: B3 ou cripto.
 *
 * As criptos rodam no mesmo motor das acoes, num schema separado do banco
 * (`scanner/mercado.py`). Na tela, o cartao, a ficha e o backtest tambem sao
 * os mesmos; este arquivo guarda as diferencas, para os componentes nao
 * espalharem `if cripto`: a moeda, o menor passo de preco, como se escreve um
 * preco de 0,000004 e as palavras ("pregao" vira "dia", "acao" vira a propria
 * moeda).
 *
 * So conta e texto, sem banco: pode ser importado por componente de cliente.
 */

export type Mercado = "b3" | "cripto";

export function mercadoDe(valor: string | null | undefined): Mercado {
  return valor === "cripto" ? "cripto" : "b3";
}

const VAZIO = "—";

/** Casas decimais para um preco de cripto: pelo menos 5 algarismos significativos. */
export function casasDoPreco(v: number): number {
  const modulo = Math.abs(v);
  if (!(modulo > 0)) return 2;
  if (modulo >= 1000) return 0;
  if (modulo >= 100) return 2;
  // 0,52 -> 5 casas; 0,000004 -> 10 casas (o limite da coluna do banco)
  return Math.min(10, Math.max(2, 4 - Math.floor(Math.log10(modulo))));
}

/**
 * O menor passo de preco. B3: 1 centavo. Cripto: a quinta casa significativa
 * (1 para o BTC a 65.000; 0,00001 para uma moeda a 0,52) -- a mesma conta de
 * `scanner.mercado.tick_do_preco`, que e a que o backtest e o pipeline usam.
 */
export function passoDoPreco(mercado: Mercado, preco: number): number {
  if (mercado === "b3") return 0.01;
  if (!(preco > 0) || !Number.isFinite(preco)) return Number.NaN;
  return 10 ** (Math.floor(Math.log10(preco)) - 4);
}

/** Arredonda um preco para as casas que o mercado mostra (tira o ruido de ponto flutuante). */
export function arredondarPreco(mercado: Mercado, v: number): number {
  if (!Number.isFinite(v)) return v;
  const casas = mercado === "b3" ? 2 : Math.max(casasDoPreco(v), 2);
  const fator = 10 ** casas;
  return Math.round((v + Number.EPSILON) * fator) / fator;
}

/** Compra um passo acima da maxima do candle. */
export function gatilhoNoMercado(mercado: Mercado, maxima: number): number {
  return arredondarPreco(mercado, maxima + passoDoPreco(mercado, maxima));
}

/** Stop um passo abaixo da minima do padrao. */
export function stopNoMercado(mercado: Mercado, minima: number): number {
  return arredondarPreco(mercado, minima - passoDoPreco(mercado, minima));
}

function formatar(v: number, casas: number): string {
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  }).format(v);
}

/** Um PRECO de ativo: "R$ 34,50", "US$ 65.351", "US$ 0,0000042". */
export function preco(mercado: Mercado, v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return VAZIO;
  if (mercado === "b3") return `R$ ${formatar(v, 2)}`;
  return `US$ ${formatar(v, casasDoPreco(v))}`;
}

/** Um VALOR em dinheiro (perda, ganho, posicao): sempre com as casas pedidas. */
export function valor(mercado: Mercado, v: number | null | undefined, casas = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return VAZIO;
  return `${mercado === "b3" ? "R$" : "US$"} ${formatar(v, casas)}`;
}

export function valorComSinal(mercado: Mercado, v: number): string {
  return `${v >= 0 ? "+" : "−"}${valor(mercado, Math.abs(v))}`;
}

/** "150 ações", "1 ação", "0,0153 BTC": o tamanho da posicao. */
export function quantidade(mercado: Mercado, q: number, ticker: string): string {
  if (mercado === "b3") return `${formatar(q, 0)} ${q === 1 ? "ação" : "ações"}`;
  // Quatro algarismos significativos, sem zero sobrando no fim: "0,0153 BTC".
  const casas = q >= 100 ? 0 : q >= 1 ? 2 : Math.min(8, Math.max(2, 3 - Math.floor(Math.log10(q))));
  const texto = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: casas }).format(q);
  return `${texto} ${ticker}`;
}

export type Textos = {
  /** "em reais" / "em dólares" */
  naMoeda: string;
  /** singular e plural da unidade de tempo do grafico diario */
  dia: [string, string];
  /** o periodo em que a nota do semaforo foi medida, como esta na grade do backtest */
  periodoDaNota: string;
  /** o mesmo, para ler: "2016–2026" */
  periodoDaNotaTexto: string;
  /** quanto historico o backtest cobre: "30 anos" */
  historico: string;
  /** contra o que o setup e comparado: "um papel sorteado" */
  sorteado: string;
  /** "o próximo pregão" / "o próximo dia" */
  proximo: string;
};

const TEXTOS: Record<Mercado, Textos> = {
  b3: {
    naMoeda: "em reais",
    dia: ["pregão", "pregões"],
    periodoDaNota: "2016-2026",
    periodoDaNotaTexto: "2016–2026",
    historico: "30 anos",
    sorteado: "um papel sorteado",
    proximo: "o próximo pregão",
  },
  cripto: {
    naMoeda: "em dólares",
    dia: ["dia", "dias"],
    periodoDaNota: "2022-2026",
    periodoDaNotaTexto: "2022–2026",
    historico: "9 anos",
    sorteado: "uma moeda sorteada",
    proximo: "o próximo dia",
  },
};

export function textos(mercado: Mercado): Textos {
  return TEXTOS[mercado];
}

/** A ficha do ativo, com o foco no dia do candle. */
export function linkDaFichaNoMercado(mercado: Mercado, ticker: string, dia: string): string {
  return mercado === "b3" ? `/papel/${ticker}?foco=${dia}` : `/cripto/${ticker}?foco=${dia}`;
}
