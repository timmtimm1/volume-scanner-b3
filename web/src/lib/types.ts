/** Formas que a interface consome. Espelham as tabelas da secao 8 do plano. */

export type Evento = {
  ticker: string;
  tradeDate: string; // ISO, AAAA-MM-DD
  zLog: number;
  zByWindow: Record<number, number>;
  zRobust: number | null;
  rvol: number | null;
  close: number;
  volumeFinancial: number;
  tradesCount: number | null;
  tradesCensored: boolean;
  /** Contexto da secao 3.2. Campo ausente vem null: papel novo nao tem pos252. */
  retDay: number | null;
  clv: number | null;
  gap: number | null;
  rangeNorm: number | null;
  pos252: number | null;
  retPrior20: number | null;
  avgTicket: number | null;
  ticketZ: number | null;
  mktVolZ: number | null;
  zExcess: number | null;
  /** true quando cruzou o limiar do config e virou alerta no Telegram. */
  notificado: boolean;
};

export type Barra = {
  tradeDate: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volumeFinancial: number;
};

export type Pregao = {
  tradeDate: string;
  mktVolZ: number | null;
  avaliados: number;
  notificados: number;
};

export type Papel = {
  ticker: string;
  barras: Barra[];
  /** Todos os eventos do papel no historico disponivel, para os marcadores. */
  eventos: Evento[];
};

export type PapelVigiado = {
  ticker: string;
  medianaVolume: number;
  pregoesNegociados: number;
  cobertura: number;
  /** Último fechamento na janela, para dar contexto de preço. */
  ultimoFechamento: number | null;
};

export type Universo = {
  papeis: PapelVigiado[];
  /** Pregões considerados na janela. */
  janela: number;
  pisoMediana: number;
  coberturaMinima: number;
  /** Quantos papéis negociaram na janela, antes dos cortes. */
  avaliados: number;
};
