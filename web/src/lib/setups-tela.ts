/**
 * A aba Setups, sem banco: o tipo do setup, as secoes da tela e o resumo do
 * historico. Sem `pg` e sem React, para ir para o navegador e para os testes.
 *
 * Regra que a tela respeita: setup e leitura, nao promessa. Nenhum texto daqui
 * fala em chance de subir; o historico mostra o que aconteceu, contra o
 * mercado, e separa o que foi visto na hora (ao vivo) do que entrou na carga
 * retroativa da estreia.
 */

// So tipos: os testes rodam este arquivo no Node, que nao resolve import de
// valor sem extensao.
import type { CategoriaDoSetup, SaidaDoSetup } from "./config";
import type { LinhaDeSetup } from "./types";

export type { CategoriaDoSetup, SaidaDoSetup };

/** Volume "alto": o mesmo corte de `VOLUME_ALTO` em `backtest-tela.ts`. */
const VOLUME_ALTO = 1.5;

export type EstadoDoSetup =
  | "armado"
  | "confirmado"
  | "nao_confirmou"
  | "stop"
  | "prazo"
  | "alvo"
  | "movel"
  | "mme9";
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
  /**
   * reversao: no suporte horizontal; media: na media movel em alta; forca: a
   * parte; as demais sao os setups classicos (9.1 a 9.4, 123, pfr, mma20, pullback).
   */
  categoria: CategoriaDoSetup;
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
  /** `nivel` (suporte horizontal) ou as medias tocadas: `mme9`, `mma20`, `mme9,mma20`. */
  suporteTipo: string;
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
  /** Etiqueta de tendencia (acima da MMA 200 subindo); null nas linhas antigas. */
  alta: boolean | null;
  /** A saida que o setup segue depois de confirmado; null = a regra antiga. */
  saidaRegra: SaidaDoSetup | null;
  /**
   * Resultado em R feito pelo pipeline, na escala ajustada e liquido do custo do
   * backtest (encerrado: o final; em andamento: ate o ultimo fechamento). Os
   * precos da linha ficam cada um na escala do proprio dia, e um grupamento no
   * meio do trade (ENJU3, 09/10/2026) estragaria a conta feita aqui.
   */
  resultadoR: number | null;
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

/** "MME 9", "MMA 20", "MME 9 e MMA 20"; null no suporte horizontal. */
export function nomeDaMedia(tipo: string): string | null {
  if (tipo === "nivel") return null;
  return tipo
    .split(",")
    .filter(Boolean)
    .map((t) => `${t.slice(0, 3).toUpperCase()} ${t.slice(3)}`)
    .join(" e ");
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

/**
 * `saidaRegra` so muda duas palavras: nos setups com saida escolhida, `stop` e
 * o stop de R$ 0,01 abaixo da minima (nao "fechou abaixo") e `prazo` e o teto
 * de pregoes da suite (60), nao os 20 da regra antiga.
 */
export function rotuloDoEstado(
  estado: EstadoDoSetup,
  saidaRegra: SaidaDoSetup | null = null,
): string {
  if (saidaRegra !== null && estado === "stop") return "Stop";
  if (saidaRegra !== null && estado === "prazo") return "Teto de 60 pregões";
  switch (estado) {
    case "alvo":
      return "Alvo";
    case "movel":
      return "Stop móvel";
    case "mme9":
      return "MME 9 virou";
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
  /** Na media movel em alta: armados e em andamento juntos, secao propria. */
  media: Setup[];
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
    media: setups
      .filter((s) => s.categoria === "media" && ABERTO.has(s.estado))
      .sort((a, b) => (a.estado === b.estado ? b.rvol - a.rvol : a.estado === "armado" ? -1 : 1)),
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

/**
 * Os numeros da conferencia de uma categoria (padrao: a regra principal). As
 * categorias nao se misturam: cada uma passou -- ou nao -- por um criterio.
 */
export function resumoDoHistorico(
  lista: Setup[],
  categoria: Setup["categoria"] = "reversao",
): ResumoDoHistorico {
  const reversao = lista.filter((s) => s.categoria === categoria);
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

/** Um centavo: o gatilho fica acima da maxima e o stop abaixo da minima. */
const CENTAVO = 0.01;

const arredondar = (v: number): number => Math.round(v * 100) / 100;

/** Compra um centavo acima da maxima do candle. */
export function gatilho(s: Pick<Setup, "maxima">): number {
  return arredondar(s.maxima + CENTAVO);
}

/** Stop um centavo abaixo da minima do padrao. */
export function stopDoSetup(s: Pick<Setup, "minima">): number {
  return arredondar(s.minima - CENTAVO);
}

/** Quantos R o alvo da saida pede (alvo1/2/3), ou null nas outras saidas. */
export function multiploDoAlvo(saida: SaidaDoSetup | null): number | null {
  if (saida === "alvo1") return 1;
  if (saida === "alvo2") return 2;
  if (saida === "alvo3") return 3;
  return null;
}

/**
 * O alvo: entrada + K x (entrada - stop). Sem entrada ainda, vale o gatilho.
 * Null quando a saida do setup nao e de alvo.
 */
export function alvoDoSetup(
  s: Pick<Setup, "saidaRegra" | "entrada" | "maxima" | "minima">,
): number | null {
  const k = multiploDoAlvo(s.saidaRegra);
  if (k === null) return null;
  const entrada = s.entrada ?? gatilho(s);
  return arredondar(entrada + k * (entrada - stopDoSetup(s)));
}

/**
 * O resultado em R de quem tem saida escolhida: (saida - entrada) / (entrada -
 * stop). Em andamento, a saida e o ultimo fechamento. Null para linha antiga
 * (sem `saidaRegra`), armado que nao entrou, ou dado faltando.
 */
export function resultadoEmR(
  s: Pick<
    Setup,
    "saidaRegra" | "estado" | "entrada" | "saida" | "ultimoFechamento" | "minima" | "resultadoR"
  >,
): number | null {
  if (s.saidaRegra === null) return null;
  if (s.estado === "armado" || s.estado === "nao_confirmou") return null;
  // o do pipeline vale sempre que existe (escala ajustada); a conta abaixo e a
  // reserva para linha gravada antes de o pipeline preencher
  if (s.resultadoR !== null && s.resultadoR !== undefined) return s.resultadoR;
  if (s.entrada === null) return null;
  const risco = s.entrada - stopDoSetup(s);
  if (!(risco > 0)) return null;
  const preco = s.estado === "confirmado" ? s.ultimoFechamento : s.saida;
  if (preco === null) return null;
  return (preco - s.entrada) / risco;
}

/** Nome curto de cada setup, o mesmo do menu do Backtest. */
export const NOME_DO_SETUP: Record<CategoriaDoSetup, string> = {
  reversao: "Suporte",
  media: "Na média",
  forca: "Força",
  "9.1": "9.1",
  "9.2": "9.2",
  "9.3": "9.3",
  "9.4": "9.4",
  "123": "1-2-3",
  pfr: "PFR",
  mma20: "MMA 20",
  pullback: "Pullback",
};

/** Ordem fixa de apresentacao: a do Backtest, nunca por resultado. */
export const ORDEM_DAS_CATEGORIAS: readonly CategoriaDoSetup[] = [
  "9.1",
  "9.2",
  "9.3",
  "9.4",
  "123",
  "pfr",
  "mma20",
  "pullback",
  "reversao",
  "media",
  "forca",
];

/** Os setups classicos: tudo que nao e reversao, media ou forca. */
export function ehClassico(categoria: CategoriaDoSetup): boolean {
  return categoria !== "reversao" && categoria !== "media" && categoria !== "forca";
}

/** Reversao e "suporte" no Backtest; as demais chaves sao as mesmas. */
export function chaveDoBacktest(categoria: CategoriaDoSetup): string {
  return categoria === "reversao" ? "suporte" : categoria;
}

/** A categoria que cada chave do Backtest representa (o inverso de `chaveDoBacktest`). */
export function categoriaDaChave(chave: string): CategoriaDoSetup | null {
  const categoria = chave === "suporte" ? "reversao" : chave;
  return (ORDEM_DAS_CATEGORIAS as readonly string[]).includes(categoria)
    ? (categoria as CategoriaDoSetup)
    : null;
}

export type Preferencia = { alerta: boolean; saida: SaidaDoSetup };
export type Preferencias = Record<CategoriaDoSetup, Preferencia>;

/** O que cada saida diz, em palavras, no cartao. */
export const SAIDA_EM_TEXTO: Record<SaidaDoSetup, string> = {
  alvo1: "alvo de 1R",
  alvo2: "alvo de 2R",
  alvo3: "alvo de 3R",
  minimas: "stop móvel nas mínimas",
  mme9: "sai quando a MME 9 vira",
};

export type Etiqueta = { texto: string; tipo: "tendencia" | "volume" };

/**
 * As etiquetas do cartao: tendencia (so quando `alta` e conhecida) e volume
 * (so de 1,5x para cima; a estrela vai junto quando o setup esta marcado).
 */
export function etiquetasDoSetup(
  s: Pick<Setup, "alta" | "rvol" | "destaque">,
): Etiqueta[] {
  const lista: Etiqueta[] = [];
  if (s.alta !== null) {
    lista.push({ texto: s.alta ? "em alta" : "contra a tendência", tipo: "tendencia" });
  }
  if (s.rvol >= VOLUME_ALTO) {
    const v = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(s.rvol);
    lista.push({ texto: `${s.destaque ? "★ " : ""}vol ${v}×`, tipo: "volume" });
  } else if (s.destaque) {
    lista.push({ texto: "★", tipo: "volume" });
  }
  return lista;
}

export type Bloco = {
  categoria: CategoriaDoSetup;
  armados: Setup[];
  emAndamento: Setup[];
  /** Os ultimos encerrados, do mais recente para o mais antigo. */
  encerrados: Setup[];
  alerta: boolean;
  saida: SaidaDoSetup;
};

/** Quantos encerrados cada bloco mostra. */
export const MAXIMO_DE_ENCERRADOS = 10;

/**
 * Um bloco por setup, separado em "alerta ligado" e "outros" pelas preferencias.
 * A ordem dos blocos e fixa (`ORDEM_DAS_CATEGORIAS`); dentro do bloco os armados
 * vao por volume e os em andamento pelo dia da confirmacao -- nada por resultado.
 */
export function agruparPorCategoria(
  setups: Setup[],
  prefs: Preferencias,
): { ligados: Bloco[]; outros: Bloco[] } {
  const ligados: Bloco[] = [];
  const outros: Bloco[] = [];
  for (const categoria of ORDEM_DAS_CATEGORIAS) {
    const doSetup = setups.filter((s) => s.categoria === categoria);
    const bloco: Bloco = {
      categoria,
      armados: doSetup.filter((s) => s.estado === "armado").sort((a, b) => b.rvol - a.rvol),
      emAndamento: doSetup
        .filter((s) => s.estado === "confirmado")
        .sort((a, b) => (b.confirmadoEm ?? "").localeCompare(a.confirmadoEm ?? "")),
      encerrados: doSetup
        .filter((s) => !ABERTO.has(s.estado))
        .sort(
          (a, b) =>
            (b.encerradoEm ?? b.tradeDate).localeCompare(a.encerradoEm ?? a.tradeDate) ||
            b.tradeDate.localeCompare(a.tradeDate),
        )
        .slice(0, MAXIMO_DE_ENCERRADOS),
      alerta: prefs[categoria].alerta,
      saida: prefs[categoria].saida,
    };
    (bloco.alerta ? ligados : outros).push(bloco);
  }
  return { ligados, outros };
}

/**
 * As linhas de preco do grafico: do setup do papel que esta armado ou em
 * andamento (o mais recente) entre os de alerta ligado. Entrada (ou gatilho,
 * enquanto nao entrou), stop e, se a saida for de alvo, o alvo.
 */
export function linhasDoSetup(setups: Setup[], prefs: Preferencias): LinhaDeSetup[] {
  const aberto = setups
    .filter((s) => ABERTO.has(s.estado) && prefs[s.categoria].alerta)
    .sort((a, b) => b.tradeDate.localeCompare(a.tradeDate) || b.id - a.id)[0];
  if (!aberto) return [];
  const linhas: LinhaDeSetup[] = [
    { preco: aberto.entrada ?? gatilho(aberto), titulo: "entrada", tipo: "entrada" },
    { preco: stopDoSetup(aberto), titulo: "stop", tipo: "stop" },
  ];
  const alvo = alvoDoSetup(aberto);
  const k = multiploDoAlvo(aberto.saidaRegra);
  if (alvo !== null && k !== null) linhas.push({ preco: alvo, titulo: `alvo ${k}R`, tipo: "alvo" });
  return linhas;
}


/** Setups ao vivo ja encerrados de uma categoria, com a saida escolhida (desde a estreia). */
export type AoVivo = { n: number; mediaR: number | null; acerto: number | null };

/**
 * A conferencia de um setup: o que ele fez ao vivo contra o que o backtest
 * mediu em 2016-2026 (decisao de 21/10/2026: o historico ao vivo e a
 * conferencia da regra). As saidas podem ser diferentes: ao vivo vale a que o
 * usuario escolheu; no backtest, a escolhida em 1995-2015.
 */
export type Conferencia = {
  aoVivo: AoVivo | null;
  backtest: { r: number | null; saida: SaidaDoSetup | null } | null;
};

const r2 = (v: number) =>
  `${v > 0 ? "+" : v < 0 ? "\u2212" : ""}${Math.abs(v).toFixed(2).replace(".", ",")} R`;

/** "Ao vivo: 12 encerrados · média +0,08 R · acertou 42%", ou que ainda nao ha. */
export function textoAoVivo(a: AoVivo | null): string {
  if (!a || a.n === 0) return "Ao vivo: nenhum encerrado ainda com a saída escolhida.";
  const media = a.mediaR === null ? "" : ` · média ${r2(a.mediaR)}`;
  const acerto = a.acerto === null ? "" : ` · acertou ${Math.round(a.acerto * 100)}%`;
  return `Ao vivo: ${a.n} encerrado${a.n === 1 ? "" : "s"}${media}${acerto}`;
}
