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

/**
 * Segmento de suporte ou resistencia que a ficha desenha (tabela `niveis`).
 * Antes de `valeDesde` (o 3o toque) a linha e pontilhada; `virou` e o nivel que
 * trocou de papel (resistencia rompida que virou suporte, ou o contrario).
 */
export type NivelDoGrafico = {
  lado: "suporte" | "resistencia";
  preco: number;
  de: string;
  ate: string;
  valeDesde: string | null;
  rompidoEm: string | null;
  virou: boolean;
  ativo: boolean;
};

/** Seta de setup no candle (so logado): o dia, as letras dos padroes e o destaque. */
export type MarcaDeSetup = { data: string; letras: string; destaque: boolean; forca: boolean };

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

/* ------------------------------------------------------------------ */
/* Resumo da semana: o payload v1 gravado em `resumos_semanais`.       */
/* ------------------------------------------------------------------ */

/** Bloco (ou sub-bloco) cuja fonte falhou na montagem. O texto e tecnico. */
export type BlocoComErro = { erro: string };

/** Uma edicao da lista: a sexta-feira nominal e o intervalo da semana. */
export type EdicaoDaSemana = { sexta: string; inicio: string; fim: string };

export type AtivoDaAbertura = {
  data: string;
  valor: number;
  /** Variacoes em fracao (0,0157 = +1,57%). */
  semana: number | null;
  mes: number | null;
  ano: number | null;
};

export type Abertura = {
  ibovespa: AtivoDaAbertura | BlocoComErro;
  dolar: AtivoDaAbertura | BlocoComErro;
  brent: AtivoDaAbertura | BlocoComErro;
  ouro: AtivoDaAbertura | BlocoComErro;
};

export type AcaoDaSemana = {
  ticker: string;
  /** Variacao ajustada por proventos e desdobramentos, em fracao. */
  variacao: number;
  variacao_bruta: number;
  preco_inicio: number;
  preco_fim: number;
  data_inicio: string;
  data_fim: string;
  ajustado: boolean;
  /** Fator de desdobramento/grupamento/bonificacao; 1 = nenhum. */
  multiplicador: number;
  proventos_por_acao: number;
  /** Falso quando a B3 nao respondeu: "sem evento" e "nao deu para saber" diferem. */
  conferido: boolean;
  /** Preenchido so no `fora_do_ranking`: por que o papel nao tem variacao ajustada. */
  eventos_sem_ajuste: string | null;
};

export type AcoesDaSemana = {
  altas: AcaoDaSemana[];
  quedas: AcaoDaSemana[];
  fora_do_ranking: AcaoDaSemana[];
  avaliados: number;
  conferidos: number;
  falhas_b3: string[];
};

export type NoticiaOutraFonte = { fonte: string; link: string };

export type HistoriaDaSemana = {
  titulo: string;
  fonte: string;
  link: string;
  veiculos: number;
  publicada_em: string;
  outras_fontes: NoticiaOutraFonte[];
};

export type NoticiasDaSemana = {
  historias: HistoriaDaSemana[];
  contagem: {
    recebidas: number;
    distintas: number;
    na_semana: number;
    na_imprensa: number;
    descartes: Record<string, number>;
  };
  avisos: string[];
  buscas: string[];
  janela: { de: string; ate: string };
};

export type MoedaCripto = {
  id: string;
  simbolo: string;
  nome: string;
  rank: number;
  preco: number;
  market_cap: number;
  variacao_7d: number | null;
};

export type CriptoDaSemana = {
  btc: MoedaCripto | null;
  eth: MoedaCripto | null;
  altas: MoedaCripto[];
  quedas: MoedaCripto[];
  moedas: MoedaCripto[];
  coletado_em: string;
};

export type VerticeDaCurva = {
  du: number;
  anos: number;
  /** % a.a. */
  taxa: number;
  taxa_anterior: number | null;
  variacao_bp: number | null;
};

/**
 * A curva da semana (prefixada ou, em `curva_real`, IPCA+). Edicao antiga nao
 * tem `fonte` -- era a ANBIMA --, e a anterior ao Tesouro Direto nao tem
 * `curva_real`. `data_anterior` e null quando a semana anterior nao teve dado.
 */
export type CurvaPrefixada = {
  data: string;
  data_anterior: string | null;
  vertices: VerticeDaCurva[];
  fonte?: "tesouro_direto";
};

/** Uma linha de `juros_historico`: a taxa de uma serie numa semana (sexta nominal). */
export type LinhaDeJuros = {
  semana: string;
  serie: string;
  /** % a.a. */
  taxa: number;
};

/** Os ids das series do grafico de juros. */
export type IdDaSerie = "selic" | "pre_1a" | "pre_2a" | "pre_5a" | "pre_10a" | "ipca_5a" | "ipca_10a";

/**
 * O historico em forma compacta, para ir ao cliente: os vetores tem o tamanho de
 * `semanas` e estao alinhados com ela; `null` = a serie nao tem ponto na semana.
 */
export type HistoricoDeJuros = {
  semanas: string[];
  taxas: Record<IdDaSerie, (number | null)[]>;
};

export type IndicadoresBr = {
  /** % a.a. */
  selic_meta: number | null;
  /** FRACAO, acumulada no mes / no ano ate `cdi_data`. */
  cdi_mes: number | null;
  cdi_ano: number | null;
  cdi_data: string | null;
  /** % (4,58 = 4,58%), acumulado em 12 meses. */
  ipca_12m: number | null;
  /** Mes de referencia do IPCA, AAAA-MM. */
  ipca_referencia: string | null;
  /** Por que um numero ficou `null` (a fonte falhou); ausente quando veio tudo. */
  erros?: Partial<Record<"selic_meta" | "cdi_mes" | "cdi_ano" | "ipca_12m", string>>;
};

export type VencimentoTreasury = {
  /** "3 Mo", "2 Yr": como o Tesouro dos EUA escreve. */
  prazo: string;
  taxa: number;
  taxa_anterior: number | null;
  variacao_bp: number | null;
};

export type Treasuries = {
  data: string;
  data_anterior: string;
  vencimentos: VencimentoTreasury[];
};

export type DotPlot = {
  data_projecao: string;
  medianas: { periodo: string; taxa: number }[];
};

export type EventoDaAgenda = {
  data: string;
  /** HH:MM de Brasilia; null = sem horario. */
  hora: string | null;
  pais: string;
  fonte: string;
  evento: string;
  detalhe: string | null;
  consenso: { mediana: number; unidade: string; fonte: string; data: string } | null;
};

export type BalancoConfirmado = {
  data: string;
  empresa: string;
  cd_cvm: number;
  tickers: string[];
  horario: string | null;
  trimestre: string | null;
  fonte: string;
};

export type BalancoProvavel = {
  empresa: string;
  cd_cvm: number;
  tickers: string[];
  documento: string;
  entregue_em: string;
};

export type BalancosDaSemana = {
  confirmados: BalancoConfirmado[];
  provaveis: BalancoProvavel[];
  avisos: string[];
};

export type ProximaSemana = {
  inicio: string;
  fim: string;
  feriados_b3: string[];
  agenda: EventoDaAgenda[];
  agenda_avisos: string[];
  balancos: BalancosDaSemana | BlocoComErro;
};

/** O payload v1 inteiro. Os blocos opcionais podem vir como `{ erro }`. */
export type ResumoDaSemana = {
  versao: number;
  semana: { sexta: string; inicio: string; fim: string; pregoes: string[] };
  gerado_em: string;
  acoes: AcoesDaSemana;
  abertura: Abertura | BlocoComErro;
  cripto: CriptoDaSemana | BlocoComErro;
  juros_br: {
    curva: CurvaPrefixada | BlocoComErro;
    curva_real?: CurvaPrefixada | BlocoComErro;
    indicadores: IndicadoresBr | BlocoComErro;
  };
  eua: {
    treasuries: Treasuries | BlocoComErro;
    fed: DotPlot | BlocoComErro;
  };
  noticias: NoticiasDaSemana | BlocoComErro;
  proxima_semana: ProximaSemana;
};
