// As commodities da página Análise: o que é cada uma e de onde vem o preço.
//
// Cópia da lista de `scanner/cripto/commodities.py` (`A_VISTA` + `CONTRATOS`);
// um teste do Python trava as duas. O texto foi pesquisado em 24/11/2026 (sites
// da Paxos e da Tether, anúncios da Binance e o próprio dado da Binance).
// Sem import: o teste do site roda este arquivo direto no Node.

export type TipoDeCommodity = "token" | "contrato";

export interface Commodity {
  ticker: string;
  /** O nome na tela: "Ouro", "Petróleo WTI"... */
  nome: string;
  tipo: TipoDeCommodity;
  /** O par na Binance (à vista para os tokens, perpétuo para os contratos). */
  par: string;
  /** Quanto vale uma unidade do preço mostrado. */
  unidade: string;
  /** O que é, em frases curtas. */
  detalhes: string[];
}

const ONCA = "dólares por onça troy (31,1 g)";

const NEST =
  "Oferecido pela Nest Exchange, empresa da Binance supervisionada pelo regulador de Abu Dhabi (FSRA, no ADGM).";

export const COMMODITIES: Readonly<Record<string, Commodity>> = {
  PAXG: {
    ticker: "PAXG",
    nome: "Ouro (PAX Gold)",
    tipo: "token",
    par: "PAXGUSDT",
    unidade: "1 token = 1 onça troy (31,1 g) de ouro",
    detalhes: [
      "Emitido pela Paxos, empresa americana. Cada token corresponde a 1 onça troy de uma barra de ouro London Good Delivery guardada em cofre em Londres.",
      "Dá para trocar por barra física com conta na Paxos, a partir de uma barra inteira (cerca de 430 tokens). Abaixo disso, o resgate é em dólar.",
      "A Paxos publica atestados periódicos de que o ouro guardado cobre os tokens em circulação.",
      "É o ouro com o histórico mais longo na Binance à vista.",
    ],
  },
  XAUT: {
    ticker: "XAUT",
    nome: "Ouro (Tether Gold)",
    tipo: "token",
    par: "XAUTUSDT",
    unidade: "1 token = 1 onça troy (31,1 g) de ouro",
    detalhes: [
      "Emitido pela TG Commodities, do grupo Tether (o mesmo do USDT), registrada em El Salvador desde 2025. Cada token corresponde a 1 onça troy de ouro guardada em cofre na Suíça.",
      "Resgate em ouro físico a partir de 430 tokens, com conta verificada e entrega na Suíça.",
      "É o maior token de ouro em valor de mercado: mais da metade do ouro tokenizado em 2026.",
      "Na Binance à vista só desde março de 2026: histórico curto.",
    ],
  },
  XAU: {
    ticker: "XAU",
    nome: "Ouro",
    tipo: "contrato",
    par: "XAUUSDT",
    unidade: ONCA,
    detalhes: ["O ouro do XAUUSD, em contrato perpétuo.", NEST],
  },
  XAG: {
    ticker: "XAG",
    nome: "Prata",
    tipo: "contrato",
    par: "XAGUSDT",
    unidade: ONCA,
    detalhes: ["A prata do XAGUSD, em contrato perpétuo.", NEST],
  },
  XPT: {
    ticker: "XPT",
    nome: "Platina",
    tipo: "contrato",
    par: "XPTUSDT",
    unidade: ONCA,
    detalhes: ["A platina do XPTUSD, em contrato perpétuo. Volume bem menor que o do ouro e da prata."],
  },
  XPD: {
    ticker: "XPD",
    nome: "Paládio",
    tipo: "contrato",
    par: "XPDUSDT",
    unidade: ONCA,
    detalhes: ["O paládio do XPDUSD, em contrato perpétuo. É o de menor volume entre as commodities da Binance."],
  },
  COPPER: {
    ticker: "COPPER",
    nome: "Cobre",
    tipo: "contrato",
    par: "COPPERUSDT",
    unidade: "dólares por libra-peso (454 g), como na COMEX",
    detalhes: ["O cobre, em contrato perpétuo. Metal industrial: o preço costuma acompanhar a atividade econômica."],
  },
  CL: {
    ticker: "CL",
    nome: "Petróleo WTI",
    tipo: "contrato",
    par: "CLUSDT",
    unidade: "dólares por barril",
    detalhes: ["O petróleo americano (West Texas Intermediate), a referência da NYMEX, em contrato perpétuo."],
  },
  BZ: {
    ticker: "BZ",
    nome: "Petróleo Brent",
    tipo: "contrato",
    par: "BZUSDT",
    unidade: "dólares por barril",
    detalhes: ["O petróleo do Mar do Norte (Brent), a referência internacional negociada na ICE, em contrato perpétuo."],
  },
  NATGAS: {
    ticker: "NATGAS",
    nome: "Gás natural",
    tipo: "contrato",
    par: "NATGASUSDT",
    unidade: "dólares por milhão de BTU (MMBtu)",
    detalhes: ["O gás natural americano (Henry Hub), em contrato perpétuo."],
  },
};

/** Vale para os dois tokens de ouro. */
export const SOBRE_OS_TOKENS: readonly string[] = [
  "Token à vista com lastro: quem compra fica com o direito sobre o ouro guardado pelo emissor. O risco é o do emissor e o do cofre, não só o do preço.",
  "Negocia todo dia, como qualquer cripto. No fim de semana o mercado de ouro de verdade está fechado, então o preço de sábado e domingo é só o da Binance.",
];

/** Vale para os oito contratos. */
export const SOBRE_OS_CONTRATOS: readonly string[] = [
  "Contrato perpétuo da Binance Futures, liquidado em USDT: segue o preço da commodity, mas quem compra não fica dono de nada. Não tem vencimento.",
  "Uma taxa de financiamento, paga entre comprados e vendidos, mantém o preço do contrato perto do preço da commodity.",
  "Negocia também no sábado e no domingo, com volume menor, enquanto a bolsa da commodity está fechada.",
  "Histórico curto: o mais antigo, o do ouro, começa em dezembro de 2025. Sem 3 anos, ainda não há sazonalidade.",
  "O dia chega com um dia de atraso: o candle vem do arquivo público da Binance, que sai na manhã seguinte.",
];

export function eCommodity(ticker: string): boolean {
  return Object.prototype.hasOwnProperty.call(COMMODITIES, ticker);
}

export function commodityDe(ticker: string): Commodity | null {
  return eCommodity(ticker) ? COMMODITIES[ticker] : null;
}

/** O que a página Análise mostra: as criptos (padrão) ou as commodities. */
export type Grupo = "cripto" | "commodity";

/** `?grupo=commodity` abre as commodities; qualquer outra coisa é cripto. */
export function grupoDaUrl(v: string | string[] | undefined): Grupo {
  return v === "commodity" ? "commodity" : "cripto";
}

/** O endereço de uma aba da Análise, mantendo o grupo. */
export function hrefDaAnalise(aba: "ano" | "sazonalidade" | "rankings", grupo: Grupo): string {
  const partes: string[] = [];
  if (aba !== "ano") partes.push(`aba=${aba}`);
  if (grupo === "commodity") partes.push("grupo=commodity");
  return partes.length === 0 ? "/analise" : `/analise?${partes.join("&")}`;
}
