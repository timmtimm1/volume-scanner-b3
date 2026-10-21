/**
 * A aba Setups, sem banco: o tipo do setup, as secoes da tela e o resumo do
 * historico. Sem `pg` e sem React, para ir para o navegador e para os testes.
 *
 * Regra que a tela respeita: setup e leitura, nao promessa. Nenhum texto daqui
 * fala em chance de subir; o historico mostra o que aconteceu, contra o
 * mercado, e separa o que foi visto na hora (ao vivo) do que entrou na carga
 * retroativa da estreia.
 */

export type EstadoDoSetup = "armado" | "confirmado" | "nao_confirmou" | "stop" | "prazo";
export type Horizonte = 5 | 10 | 20;
export const HORIZONTES: readonly Horizonte[] = [5, 10, 20];

export type AlertaDoSetup = {
  preco: number;
  disparadoEm: string | null;
  precoDisparo: number | null;
  expiraEm: string | null;
};

export type Setup = {
  id: number;
  ticker: string;
  tradeDate: string;
  categoria: "reversao" | "forca";
  padroes: string[];
  toques: number;
  virou: boolean;
  furou: boolean;
  rvol: number;
  destaque: boolean;
  contexto: string[];
  fechamento: number;
  maxima: number;
  minima: number;
  suporte: number;
  resistencia: number | null;
  espacoR: number | null;
  riscoPct: number;
  aoVivo: boolean;
  estado: EstadoDoSetup;
  confirmadoEm: string | null;
  entrada: number | null;
  encerradoEm: string | null;
  saida: number | null;
  /** Retorno do fechamento do candle ate h pregoes depois. */
  r: Record<Horizonte, number | null>;
  /** Media do universo liquido na mesma janela. */
  m: Record<Horizonte, number | null>;
  /** Retorno da entrada confirmada ate h pregoes depois da confirmacao. */
  rc: Record<Horizonte, number | null>;
  alerta: AlertaDoSetup | null;
  ultimoFechamento: number | null;
  ultimoPregao: string | null;
  /** Pregoes do papel depois da confirmacao (o "dia N de 20"). */
  pregoesDesde: number | null;
};

export const NOME_DO_PADRAO: Record<string, string> = {
  martelo: "Martelo",
  libelula: "Doji libélula",
  engolfo: "Engolfo de alta",
  piercing: "Piercing",
  estrela: "Estrela da manhã",
  forca: "Candle de força",
};

export const NOME_DO_CONTEXTO: Record<string, string> = {
  lateral: "lateralização",
  correcao: "correção em alta",
};

/** Letras do marcador no grafico da ficha, uma por padrao. */
export const LETRA_DO_PADRAO: Record<string, string> = {
  martelo: "M",
  libelula: "L",
  engolfo: "E",
  piercing: "P",
  estrela: "★",
  forca: "F",
};

/**
 * Link da ficha centrado no candle do setup.
 *
 * `?foco=` e nao `?data=`: a ficha le `data` como o EVENTO de volume a abrir, e
 * o dia do setup quase nunca e evento -- ai ela caia no evento mais recente do
 * papel e o grafico pulava para meses atras (incidente de 21/10/2026).
 */
export function linkDaFicha(s: Pick<Setup, "ticker" | "tradeDate">): string {
  return `/papel/${s.ticker}?foco=${s.tradeDate}`;
}

export function nomeDosPadroes(s: Pick<Setup, "padroes">): string {
  return s.padroes.map((p) => NOME_DO_PADRAO[p] ?? p).join(" + ");
}

/** Quanto o papel andou alem do mercado em h pregoes (r - m), ou null. */
export function contraOMercado(s: Setup, h: Horizonte): number | null {
  const r = s.r[h];
  const m = s.m[h];
  return r === null || m === null ? null : r - m;
}

/** Do preco de entrada ao ultimo fechamento, para o que esta em andamento. */
export function desdeAEntrada(s: Setup): number | null {
  if (s.entrada === null || s.ultimoFechamento === null) return null;
  return s.ultimoFechamento / s.entrada - 1;
}

/** Quanto falta ate a minima do padrao (o stop), a partir do ultimo fechamento. */
export function folgaAteOStop(s: Setup): number | null {
  if (s.ultimoFechamento === null) return null;
  return s.minima / s.ultimoFechamento - 1;
}

export function rotuloDoEstado(estado: EstadoDoSetup): string {
  switch (estado) {
    case "armado":
      return "armado";
    case "confirmado":
      return "em andamento";
    case "nao_confirmou":
      return "não confirmou";
    case "stop":
      return "fechou abaixo da mínima";
    case "prazo":
      return "completou 20 pregões";
  }
}

export type Secoes = {
  armados: Setup[];
  emAndamento: Setup[];
  forca: Setup[];
  historico: Setup[];
};

const ABERTO: ReadonlySet<EstadoDoSetup> = new Set(["armado", "confirmado"]);

/**
 * As secoes da aba. Armados e em andamento so com candle de reversao, que e a
 * regra conferida; o candle de forca vai a parte, com o aviso. O historico
 * tem os encerrados (os dois tipos), do candle mais novo para o mais antigo;
 * os retroativos so entram quando pedidos.
 */
export function separar(setups: Setup[], comRetroativos: boolean): Secoes {
  const porVolume = (a: Setup, b: Setup) => b.rvol - a.rvol;
  const reversao = setups.filter((s) => s.categoria === "reversao");
  return {
    armados: reversao.filter((s) => s.estado === "armado").sort(porVolume),
    emAndamento: reversao
      .filter((s) => s.estado === "confirmado")
      .sort((a, b) => (b.confirmadoEm ?? "").localeCompare(a.confirmadoEm ?? "")),
    forca: setups.filter((s) => s.categoria === "forca" && ABERTO.has(s.estado)).sort(porVolume),
    historico: setups
      .filter((s) => !ABERTO.has(s.estado) && (comRetroativos || s.aoVivo))
      .sort((a, b) => b.tradeDate.localeCompare(a.tradeDate) || b.rvol - a.rvol),
  };
}

export type ResumoDoHistorico = {
  setups: number;
  confirmaram: number;
  /** Media de (r20 - m20) entre os que ja tem 20 pregoes. */
  media20: number | null;
  comResultado: number;
};

/** Os numeros da conferencia: so candle de reversao, que e a regra da aba. */
export function resumoDoHistorico(lista: Setup[]): ResumoDoHistorico {
  const reversao = lista.filter((s) => s.categoria === "reversao");
  const resultados = reversao
    .map((s) => contraOMercado(s, 20))
    .filter((x): x is number => x !== null);
  return {
    setups: reversao.length,
    confirmaram: reversao.filter((s) => s.confirmadoEm !== null).length,
    media20: resultados.length ? resultados.reduce((a, b) => a + b, 0) / resultados.length : null,
    comResultado: resultados.length,
  };
}

const HORA_NA_B3 = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  hour: "2-digit",
  minute: "2-digit",
});

/** A situacao do alerta de confirmacao, em palavras, ou null sem alerta. */
export function situacaoDoAlerta(s: Setup, hoje: string): string | null {
  const a = s.alerta;
  if (!a) return null;
  if (a.disparadoEm) {
    const hora = HORA_NA_B3.format(new Date(a.disparadoEm));
    const preco = a.precoDisparo === null ? "" : ` a R$ ${a.precoDisparo.toFixed(2).replace(".", ",")}`;
    return `alerta rompeu às ${hora}${preco}`;
  }
  if (a.expiraEm !== null && a.expiraEm < hoje) return "alerta venceu sem romper";
  if (a.expiraEm === null) return "alerta vigiando";
  const [, m, d] = a.expiraEm.split("-");
  return `alerta vigiando até ${d}/${m}`;
}
