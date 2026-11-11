/**
 * A pagina Backtest, do lado de quem desenha: tipos, rotulos, formatacao e a
 * leitura da selecao (`?setup=&saida=&grupo=`).
 *
 * Nao importa `pg`: vai para o navegador e para os testes. A leitura do banco
 * mora em `backtest.ts`.
 */

export type Nivel = "firme" | "fraco" | "falhou";
export type Saida = "alvo1" | "alvo2" | "alvo3" | "minimas" | "mme9";
export type Grupo = "todos" | "alta" | "contra";
export type Periodo = "1995-2015" | "2016-2026" | "tudo";
export type Motivo = "aberto" | "stop" | "movel" | "alvo" | "mme9" | "teto";

export type Rodada = {
  id: number;
  criadaEm: string;
  dadosDe: string;
  dadosAte: string;
  /** Custo por lado, em fracao (0,0008 = 0,08%). */
  custo: number;
  teto: number;
  trades: number;
  papeis: number;
};

export type Escolha = {
  setup: string;
  nivel: Nivel;
  saida: Saida | null;
  grupo: Grupo | null;
  combinacoes: number;
  nEscolha: number | null;
  nConferencia: number | null;
  expEscolha: number | null;
  difEscolha: number | null;
  expConferencia: number | null;
  icConfBaixo: number | null;
  icConfAlto: number | null;
  difConferencia: number | null;
};

export type Resultado = {
  setup: string;
  saida: Saida;
  grupo: Grupo;
  periodo: Periodo;
  n: number;
  acerto: number | null;
  ganhoMedio: number | null;
  perdaMedia: number | null;
  payoff: number | null;
  expectativa: number | null;
  icBaixo: number | null;
  icAlto: number | null;
  fatorLucro: number | null;
  diasMedio: number | null;
  rPorDia: number | null;
  controle: number | null;
  diferenca: number | null;
  difIcBaixo: number | null;
  difIcAlto: number | null;
  pctStop: number | null;
  pctMovel: number | null;
  pctAlvo: number | null;
  pctMme9: number | null;
  pctTeto: number | null;
};

export type Ano = {
  ano: number;
  n: number;
  expectativa: number | null;
  somaR: number | null;
  controle: number | null;
};

export type PontoDaCurva = {
  /** Primeiro dia do mes, AAAA-MM-DD. */
  mes: string;
  n: number;
  r: number | null;
  controle: number | null;
  acumulado: number | null;
  controleAcumulado: number | null;
  recuo: number | null;
};

export type TradeDoBacktest = {
  id: number;
  setup: string;
  saida: Saida;
  ticker: string;
  dataSinal: string;
  dataEntrada: string;
  dataSaida: string | null;
  entrada: number;
  stop: number;
  precoSaida: number | null;
  motivo: Motivo;
  dias: number | null;
  r: number | null;
  rControle: number | null;
  alta: boolean | null;
  rvol: number | null;
};

/** Ordem fixa de apresentacao: nunca por resultado. */
export const ORDEM_DOS_SETUPS: readonly string[] = [
  "9.1",
  "9.2",
  "9.3",
  "9.4",
  "123",
  "pfr",
  "123_suporte",
  "pfr_suporte",
  "mma20",
  "pullback",
  "contracao",
  "rompimento",
  "suporte",
  "media",
  "forca",
];

const COMPRA = "Compra 1 centavo acima da máxima no pregão seguinte; stop 1 centavo abaixo da mínima do padrão.";

export const SETUPS: Record<string, { nome: string; regra: string }> = {
  "9.1": {
    nome: "9.1",
    regra: `A média de 9 dias (MME 9) vinha caindo e virou para cima hoje, com a mínima num suporte de 3 ou mais toques e volume de 1,5× a mediana ou mais. ${COMPRA}`,
  },
  "9.2": {
    nome: "9.2",
    regra: `A MME 9 está subindo e o candle fechou abaixo da mínima do candle anterior. O candle precisa estar junto da média: mínima a no máximo 0,35 ATR acima da MME 9 (encostar ou furar vale). Só em tendência de alta: MME 80 subindo (acima de 20 pregões atrás) e topos e fundos ascendentes. ${COMPRA}`,
  },
  "9.3": {
    nome: "9.3",
    regra: `A MME 9 está subindo e houve dois fechamentos abaixo do fechamento de dois dias antes. O candle precisa estar junto da média: mínima a no máximo 0,35 ATR acima da MME 9 (encostar ou furar vale). Só em tendência de alta: MME 80 subindo (acima de 20 pregões atrás) e topos e fundos ascendentes. ${COMPRA}`,
  },
  "9.4": {
    nome: "9.4",
    regra:
      "A MME 9 subia, virou para baixo no dia anterior e voltou a subir hoje, sem perder a mínima de ontem. O candle precisa estar junto da média: mínima a no máximo 0,35 ATR acima da MME 9 (encostar ou furar vale). Só em tendência de alta: MME 80 subindo (acima de 20 pregões atrás) e topos e fundos ascendentes. Compra 1 centavo acima da máxima no pregão seguinte; stop 1 centavo abaixo da mínima de ontem.",
  },
  "123": {
    nome: "1-2-3",
    regra:
      "De três candles, o do meio tem a mínima mais baixa de todas. Compra 1 centavo acima da máxima no pregão seguinte; stop 1 centavo abaixo da mínima do candle do meio.",
  },
  pfr: {
    nome: "PFR",
    regra: `A mínima ficou abaixo das dos dois candles anteriores, mas o fechamento ficou acima do fechamento de ontem. ${COMPRA}`,
  },
  "123_suporte": {
    nome: "1-2-3 no suporte",
    regra:
      "O 1-2-3 com a mínima do candle do meio num suporte de 3 ou mais toques (o nível das linhas da ficha). Compra 1 centavo acima da máxima no pregão seguinte; stop 1 centavo abaixo da mínima do candle do meio.",
  },
  pfr_suporte: {
    nome: "PFR no suporte",
    regra: `O PFR com a mínima do dia num suporte de 3 ou mais toques (o nível das linhas da ficha). ${COMPRA}`,
  },
  mma20: {
    nome: "MMA 20",
    regra: `A média de 20 dias está subindo, o preço está acima da média de 200 dias e o candle encostou na média de 20 (até 1%) e fechou acima dela. ${COMPRA}`,
  },
  pullback: {
    nome: "Pullback",
    regra: `Uma resistência de 3 ou mais toques foi rompida no fechamento (vira suporte); o preço volta até ela em até 20 pregões e o fechamento segura o nível. ${COMPRA}`,
  },
  contracao: {
    nome: "Contração",
    regra:
      "Contração de volatilidade: três blocos seguidos de 10 pregões, cada um com amplitude (da maior máxima à menor mínima) menor que 70% da do bloco anterior, e o último a até 1 ATR da máxima de 60 pregões. Compra 1 centavo acima da máxima do último bloco (não a do dia); stop 1 centavo abaixo da mínima dele.",
  },
  rompimento: {
    nome: "Rompimento",
    regra: `Rompimento de resistência: o dia fecha acima de uma resistência de 3 ou mais toques (o nível das linhas da ficha), com volume de 1,5× ou mais. ${COMPRA}`,
  },
  suporte: {
    nome: "Suporte",
    regra: `Candle de reversão (martelo, engolfo e parecidos) num suporte de 3 ou mais toques, com volume alto, fora de queda e com espaço até a resistência. ${COMPRA}`,
  },
  media: {
    nome: "Na média",
    regra: `O mesmo candle de reversão, mas encostando na MME 9 ou na MMA 20 em tendência de alta. ${COMPRA}`,
  },
  forca: {
    nome: "Força",
    regra: `Candle verde largo saindo do suporte ou rompendo uma resistência, com os mesmos filtros do Suporte. ${COMPRA}`,
  },
};

export const SAIDAS: Record<Saida, string> = {
  alvo1: "Alvo de 1R",
  alvo2: "Alvo de 2R",
  alvo3: "Alvo de 3R",
  minimas: "Stop móvel nas mínimas",
  mme9: "Sai quando a MME 9 vira",
};

export const ORDEM_DAS_SAIDAS: readonly Saida[] = ["alvo1", "alvo2", "alvo3", "minimas", "mme9"];

export const GRUPOS: Record<Grupo, string> = {
  todos: "Todos",
  alta: "Em alta",
  contra: "Contra a tendência",
};

export const ORDEM_DOS_GRUPOS: readonly Grupo[] = ["todos", "alta", "contra"];

export const NIVEIS: Record<Nivel, { nome: string; explicacao: string }> = {
  firme: {
    nome: "Firme",
    explicacao: "Ganhou do controle em 2016–2026 e o intervalo de 95% ficou acima de zero.",
  },
  fraco: {
    nome: "Fraco",
    explicacao:
      "Positivo e acima do controle em 2016–2026, mas o intervalo cruza o zero: pode ter sido sorte.",
  },
  falhou: {
    nome: "Falhou",
    explicacao: "Em 2016–2026 ficou negativo ou abaixo do controle.",
  },
};

export const MOTIVOS: Record<Motivo, string> = {
  stop: "Stop",
  movel: "Stop móvel",
  alvo: "Alvo",
  mme9: "MME 9 virou",
  teto: "60 pregões",
  aberto: "Aberto",
};

export const PERIODOS: readonly Periodo[] = ["1995-2015", "2016-2026", "tudo"];

export const ROTULO_DO_PERIODO: Record<Periodo, string> = {
  "1995-2015": "1995–2015",
  "2016-2026": "2016–2026",
  tudo: "Tudo",
};

const MENOS = "−";
const VAZIO = "—";

const casas2 = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function valido(v: number | null | undefined): v is number {
  return v !== null && v !== undefined && Number.isFinite(v);
}

/** "0,31" com sinal explicito: "+0,31", "−0,05"; o zero exato fica "0,00". */
function comSinal(v: number): string {
  if (v === 0) return "0,00";
  return `${v > 0 ? "+" : MENOS}${casas2.format(Math.abs(v))}`;
}

/** "+0,31 R", "−0,05 R", "0,00 R"; ausente vira travessao. */
export function fmtR(v: number | null | undefined): string {
  if (!valido(v)) return VAZIO;
  return `${comSinal(v)} R`;
}

/** "[+0,09; +0,54]"; sem um dos lados, travessao. */
export function fmtIntervalo(lo: number | null | undefined, hi: number | null | undefined): string {
  if (!valido(lo) || !valido(hi)) return VAZIO;
  return `[${comSinal(lo)}; ${comSinal(hi)}]`;
}

/** Fracao em percentual inteiro: 0,38 vira "38%". */
export function fmtPct(v: number | null | undefined): string {
  if (!valido(v)) return VAZIO;
  return `${Math.round(v * 100)}%`;
}

/** Numero com 2 casas, sem unidade (payoff, fator de lucro). */
export function fmtNumero(v: number | null | undefined, casas = 2): string {
  if (!valido(v)) return VAZIO;
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  }).format(v);
}

/** O custo por lado, em %: 0,0008 vira "0,08%". */
export function fmtCusto(v: number): string {
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 }).format(v * 100)}%`;
}

/** Volume do dia do sinal sobre a mediana dos 20 anteriores, a partir daqui "alto". */
export const VOLUME_ALTO = 1.5;

export const volumeAlto = (rvol: number | null | undefined): boolean =>
  valido(rvol) && rvol >= VOLUME_ALTO;

export function fmtVolume(rvol: number | null | undefined): string {
  if (!valido(rvol)) return VAZIO;
  return `vol ${new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(rvol)}×`;
}

export type Selecao = { setup: string; saida: Saida; grupo: Grupo };

type Params = Record<string, string | string[] | undefined>;

function um(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

const ehSaida = (v: string | undefined): v is Saida =>
  v !== undefined && (ORDEM_DAS_SAIDAS as readonly string[]).includes(v);

const ehGrupo = (v: string | undefined): v is Grupo =>
  v !== undefined && (ORDEM_DOS_GRUPOS as readonly string[]).includes(v);

/**
 * Setup, saida e grupo da URL, sempre validos.
 *
 * Setup invalido ou ausente: o primeiro da ordem fixa. Saida e grupo ausentes
 * ou invalidos: os da escolha daquele setup; sem escolha, mme9 e todos.
 */
export function lerSelecao(params: Params, escolhas: readonly Escolha[]): Selecao {
  const pedido = um(params.setup);
  const setup = pedido !== undefined && ORDEM_DOS_SETUPS.includes(pedido) ? pedido : ORDEM_DOS_SETUPS[0];
  const escolha = escolhas.find((e) => e.setup === setup);
  const s = um(params.saida);
  const g = um(params.grupo);
  return {
    setup,
    saida: ehSaida(s) ? s : (escolha?.saida ?? "mme9"),
    grupo: ehGrupo(g) ? g : (escolha?.grupo ?? "todos"),
  };
}

/** O link para uma selecao. */
export function linkDaSelecao(sel: Selecao): string {
  return `/setups/backtest?setup=${encodeURIComponent(sel.setup)}&saida=${sel.saida}&grupo=${sel.grupo}`;
}

/** Ficha do papel centrada no dia do sinal (o mesmo `?foco=` dos Setups). */
export function linkDoTrade(t: Pick<TradeDoBacktest, "ticker" | "dataSinal">): string {
  return `/papel/${t.ticker}?foco=${t.dataSinal}`;
}

/** "Como saiu", na ordem em que aparece na tabela. */
export function comoSaiu(r: Resultado): { rotulo: string; v: number | null }[] {
  return [
    { rotulo: "Stop", v: r.pctStop },
    { rotulo: "Stop móvel", v: r.pctMovel },
    { rotulo: "Alvo", v: r.pctAlvo },
    { rotulo: "MME 9 virou", v: r.pctMme9 },
    { rotulo: "60 pregões", v: r.pctTeto },
  ];
}
