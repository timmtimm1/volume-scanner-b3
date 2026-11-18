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

/**
 * O nivel de um alerta de preco no mercado: centavo na B3 (a mesma conta de
 * `nivelEmCentavos`, que a ficha das acoes sempre usou), as casas da moeda em
 * cripto -- um alerta em US$ 0,050411 nao pode virar US$ 0,05.
 */
export function nivelDoAlerta(mercado: Mercado, v: number): number {
  if (mercado === "b3") return Math.round(Number((v * 100).toPrecision(12))) / 100;
  return arredondarPreco(mercado, v);
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

/** "R$" ou "US$": o simbolo ao lado de um campo de preco. */
export function simboloDaMoeda(mercado: Mercado): string {
  return mercado === "b3" ? "R$" : "US$";
}

/** Um VALOR em dinheiro (perda, ganho, posicao): sempre com as casas pedidas. */
export function valor(mercado: Mercado, v: number | null | undefined, casas = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return VAZIO;
  return `${mercado === "b3" ? "R$" : "US$"} ${formatar(v, casas)}`;
}

export function valorComSinal(mercado: Mercado, v: number): string {
  return `${v >= 0 ? "+" : "−"}${valor(mercado, Math.abs(v))}`;
}

/** Uma DIFERENCA de preco com sinal: "+R$ 1,23", "−US$ 0,0012" (com as casas da moeda). */
export function precoComSinal(mercado: Mercado, v: number): string {
  return `${v >= 0 ? "+" : "−"}${preco(mercado, Math.abs(v))}`;
}

/** "150", "0,0153": so o numero da quantidade, para tabela. */
export function numeroDaQuantidade(mercado: Mercado, q: number): string {
  if (!Number.isFinite(q)) return VAZIO;
  if (mercado === "b3" || q === 0) return formatar(q, 0);
  // Quatro algarismos significativos, sem zero sobrando no fim: "0,0153".
  // De 100 a 1.000, ainda com casas: "666,67", e nao "667" de um lote de 666,6666.
  const casas = q >= 1000 ? 0 : q >= 1 ? 2 : Math.min(8, Math.max(2, 3 - Math.floor(Math.log10(q))));
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: casas }).format(q);
}

/** "150 ações", "1 ação", "0,0153 BTC": o tamanho da posicao. */
export function quantidade(mercado: Mercado, q: number, ticker: string): string {
  if (mercado === "b3") return `${formatar(q, 0)} ${q === 1 ? "ação" : "ações"}`;
  return `${numeroDaQuantidade(mercado, q)} ${ticker}`;
}

/**
 * A quantidade exata, com todas as casas da posicao: "0,0152847". E o numero
 * que tem de bater com o saldo da corretora.
 */
export function quantidadeExata(mercado: Mercado, q: number): string {
  return new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits: REGRAS_DO_DIARIO[mercado].casasDaPosicao,
  }).format(q);
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
  /** "papel" / "moeda": o ativo de um trade */
  ativo: string;
  /** "Ações" / "Qtd.": o titulo da coluna de quantidade */
  unidades: string;
  /** "Papel" / "Moeda": o rotulo do campo */
  rotuloDoAtivo: string;
  /** "PETR4" / "BTC": o exemplo do campo */
  exemploDoAtivo: string;
  /** O que dizer sob a data de uma operacao ("" na B3). */
  notaDaData: string;
  /** Por que nao ha lote, depois de "com 1% de risco sobre o seu capital, " */
  semLote: string;
  /** Quem entra na lista de tendencia, para o rodape do painel. */
  universoDaTendencia: string;
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
    ativo: "papel",
    unidades: "Ações",
    rotuloDoAtivo: "Papel",
    exemploDoAtivo: "PETR4",
    notaDaData: "",
    semLote: "não dá nem para 1 ação a esse preço e esse stop.",
    universoDaTendencia: "Só papéis com liquidez (mediana de R$ 500 mil por dia em 60 pregões).",
  },
  cripto: {
    naMoeda: "em dólares",
    dia: ["dia", "dias"],
    periodoDaNota: "2022-2026",
    periodoDaNotaTexto: "2022–2026",
    historico: "9 anos",
    sorteado: "uma moeda sorteada",
    proximo: "o próximo dia",
    ativo: "moeda",
    unidades: "Qtd.",
    rotuloDoAtivo: "Moeda",
    exemploDoAtivo: "BTC",
    notaDaData: "o dia do candle, em UTC: depois das 21h de Brasília já é o dia seguinte",
    semLote: "a posição ficaria abaixo de US$ 5, o mínimo da corretora.",
    universoDaTendencia:
      "As 50 maiores moedas por valor de mercado; “pouca liquidez” é a que negocia menos de US$ 5 milhões por dia na Binance.",
  },
};

export function textos(mercado: Mercado): Textos {
  return TEXTOS[mercado];
}

/** A ficha do ativo, com o foco no dia do candle (sem dia, a ficha como abre). */
export function linkDaFichaNoMercado(mercado: Mercado, ticker: string, dia?: string): string {
  const base = mercado === "b3" ? `/papel/${ticker}` : `/cripto/${ticker}`;
  return dia ? `${base}?foco=${dia}` : base;
}

// ---------------------------------------------------------------------------
// Diario de trades
// ---------------------------------------------------------------------------

/**
 * As contas do diario de trades em cada mercado. `posicao.ts` e `diario.ts` sao
 * modulos puros e recebem isto por parametro.
 *
 * A taxa da Binance (0,1% por lado, decisao do usuario em 17/11/2026) entra do
 * jeito que a Binance cobra sem BNB: na COMPRA sai da moeda comprada (compra de
 * 0,0153 BTC deixa 0,0152847 na conta) e na VENDA sai dos dolares recebidos. Na
 * B3 o diario nao conta custo nenhum (decisao de 16/09/2026): taxa zero, e as
 * contas ficam exatamente as de antes.
 */
export type RegrasDoDiario = {
  /** Fracao por lado. */
  taxa: number;
  /** Casas da quantidade digitada: 0 = so inteiro (acoes); 8 em cripto, o maximo da Binance. */
  casasDaQuantidade: number;
  /** Casas da posicao depois da taxa (a coluna guarda 10). */
  casasDaPosicao: number;
  /** Casas do preco digitado e do stop. */
  casasDoPreco: number;
  /** Casas do preco medio guardado. */
  casasDoPrecoMedio: number;
  /** Todo dia tem negocio (cripto) ou so os pregoes da B3. */
  todoDia: boolean;
  /** Setups do estudo que podem virar trade (so o de compra). */
  categoriasDoEstudo: readonly string[];
  /**
   * Venda a descoberto: o trade que abre com uma VENDA e fecha com a recompra.
   * Null = o mercado nao deixa (B3, decisao do usuario de 18/11/2026). Em
   * cripto e a operacao dos futuros, e a taxa e a deles (0,05% por lado, a de
   * quem tira liquidez nos USDⓈ-M da Binance), cobrada em dolar sobre o valor
   * negociado; o funding fica de fora (escolha do usuario).
   */
  vendido: { taxa: number } | null;
};

const REGRAS_DO_DIARIO: Record<Mercado, RegrasDoDiario> = {
  b3: {
    taxa: 0,
    casasDaQuantidade: 0,
    casasDaPosicao: 0,
    casasDoPreco: 2,
    casasDoPrecoMedio: 6,
    todoDia: false,
    categoriasDoEstudo: [],
    vendido: null,
  },
  cripto: {
    taxa: 0.001,
    casasDaQuantidade: 8,
    casasDaPosicao: 10,
    casasDoPreco: 10,
    casasDoPrecoMedio: 10,
    todoDia: true,
    categoriasDoEstudo: ["rsi_estudo"],
    vendido: { taxa: 0.0005 },
  },
};

export function regrasDoDiario(mercado: Mercado): RegrasDoDiario {
  return REGRAS_DO_DIARIO[mercado];
}

const DIA_EM_SAO_PAULO = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/Sao_Paulo",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/**
 * O dia de negociacao em `instante`, AAAA-MM-DD. B3: o dia em Sao Paulo (a
 * mesma conta de `diaNaB3`). Cripto: o dia UTC, que e o do candle diario da
 * Binance -- as 22h de Brasilia ja e o candle de amanha.
 */
export function diaDoMercado(mercado: Mercado, instante: Date): string {
  return mercado === "b3" ? DIA_EM_SAO_PAULO.format(instante) : instante.toISOString().slice(0, 10);
}

/** Mesma regra de `TICKER` (`ticker.ts`); o teste trava a copia. */
const TICKER_DA_B3 = /^[A-Z][A-Z0-9]{3}\d{1,2}[A-Z]?$/;
const MOEDA = /^[A-Z0-9]{1,15}$/;

/** O ticker tem o formato do mercado? "PETR4" na B3; "BTC", "1INCH" em cripto. */
export function tickerValido(mercado: Mercado, ticker: string): boolean {
  return (mercado === "b3" ? TICKER_DA_B3 : MOEDA).test(ticker);
}

/**
 * A lista de tendencia so com os ativos liquidos? Na B3 sim: sao centenas de
 * papeis, e uma centena quase sem negocio. Em cripto o universo ja e o das 50
 * maiores por valor de mercado, e o piso do backtest (US$ 5 mi por dia, feito
 * para o stop ser realista) tirava 14 delas -- entre elas as poucas em alta em
 * 16/11/2026. Em cripto entram todas, com etiqueta nas pouco liquidas.
 */
export function tendenciaSoLiquidos(mercado: Mercado): boolean {
  return mercado === "b3";
}

/** `?mercado=cripto` para as rotas e paginas que servem os dois mercados; nada na B3. */
export function sufixoDoMercado(mercado: Mercado): string {
  return mercado === "b3" ? "" : "?mercado=cripto";
}

/** A pagina de um trade. Os ids repetem de um schema para o outro: o mercado vai junto. */
export function linkDoTrade(mercado: Mercado, id: number): string {
  return `/trades/${id}${sufixoDoMercado(mercado)}`;
}

/** Uma quantidade para o campo de texto do formulario: "0,0153", "100". */
export function quantidadeParaCampo(mercado: Mercado, q: number): string {
  const casas = REGRAS_DO_DIARIO[mercado].casasDaPosicao;
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: casas, useGrouping: false }).format(q);
}

/** Um preco para o campo de texto: "38,20" na B3, "0,52341" ou "65351" em cripto. */
export function precoParaCampo(mercado: Mercado, v: number): string {
  const casas = mercado === "b3" ? 2 : Math.max(casasDoPreco(v), 2);
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: mercado === "b3" ? 2 : 0,
    maximumFractionDigits: casas,
    useGrouping: false,
  }).format(v);
}
