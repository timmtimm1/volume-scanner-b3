/** Formas que a interface consome. Espelham as tabelas da secao 8 do plano. */

export type Evento = {
  ticker: string;
  /**
   * Nome comercial da empresa, para o ticker nao ficar sozinho na tela.
   * Nulo em papel sem empresa ligada: ETF, recibo, codigo que saiu da bolsa.
   */
  empresa: string | null;
  tradeDate: string; // ISO, AAAA-MM-DD
  /** O maior z entre as janelas: o que decide o alerta. */
  zLog: number;
  /** A janela de onde veio o `zLog`. */
  zJanela: number;
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

/** O que a tabela do historico mostra. So isso vai para o navegador. */
export type LinhaDoHistorico = Pick<
  Evento,
  | "ticker"
  | "empresa"
  | "tradeDate"
  | "zLog"
  | "rvol"
  | "retDay"
  | "zExcess"
  | "avgTicket"
  | "volumeFinancial"
>;

export type Barra = {
  tradeDate: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volumeFinancial: number;
};

/** Papeis do pregao cujo maior z caiu em [faixa, faixa+1); a faixa 6 junta 6 ou mais. */
export type FaixaDeDesvio = { faixa: number; papeis: number };

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

/** Um trimestre ja calculado, como a fase 3 grava. Valores em reais. */
export type Trimestre = {
  /** Fim do periodo, AAAA-MM-DD. */
  dtFim: string;
  /** "2T26", como o mercado chama. */
  rotulo: string;
  /** ITR, DFP ou `derivado` -- o 4T, que a CVM nao publica. */
  origem: string;
  /** Data da PRIMEIRA entrega do documento: quando o mercado soube. */
  publicadoEm: string | null;
  /** `financeiro` em banco: la nao existe EBITDA nem divida liquida. */
  layout: string | null;
  receitaTri: number | null;
  ebitdaTri: number | null;
  lucroTri: number | null;
  receita12m: number | null;
  ebitda12m: number | null;
  lucro12m: number | null;
  /** Dos controladores, que e sobre o que ROE e P/VP fazem sentido. */
  patrimonioLiquido: number | null;
  ativoTotal: number | null;
  dividaLiquida: number | null;
  liquidezCorrente: number | null;
  acoesEmCirculacao: number | null;
  /** Por classe, para o valor de mercado somar cada uma pelo seu preco. */
  acoesOn: number | null;
  acoesPn: number | null;
};

/** Um provento em dinheiro do papel. `valor` e por acao. */
export type Provento = {
  dataCom: string;
  tipo: string;
  valor: number;
};

/** Tudo que a aba Fundamentos da ficha precisa. */
export type Fundamentos = {
  empresa: string;
  setor: string | null;
  /** Classe do papel aberto (ON, PN, PNA, UNT...), quando conhecida. */
  classe: string | null;
  trimestres: Trimestre[];
  proventos: Provento[];
  /**
   * Fechamento das outras classes da mesma empresa, por pregao. O valor de
   * mercado soma cada classe pelo proprio preco: em 15/09/2026 a UNIP3 valia
   * R$ 55,40 e a UNIP6, R$ 57,48.
   */
  precosPorClasse: { on: Record<string, number>; pn: Record<string, number> };
  /**
   * O maior volume em ACOES que um papel da empresa negociou num pregao da
   * janela. Serve de prova contra a contagem de acoes: a empresa nao pode ter
   * menos acoes em circulacao do que negociou num dia so.
   */
  picoDeVolumeEmAcoes: number | null;
};
