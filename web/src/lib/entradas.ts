/**
 * "Entradas de hoje": as contas do cartao simples da aba Setups, sem banco e
 * sem React (vai para o navegador e para os testes).
 *
 * Pedido do usuario em 11/11/2026: a aba mostrava informacao demais. O cartao
 * agora responde so cinco perguntas -- o que e, onde entra, quanto perde se der
 * errado, quanto ganha se der certo, e o que o setup fez no passado -- e a
 * lista e uma so, com todos os setups juntos.
 *
 * O semaforo e a NOTA DO BACKTEST, nao uma probabilidade: verde = firme,
 * amarelo = fraco, vermelho = falhou, pelos mesmos tres niveis de
 * `scanner.backtest.metricas.nivel_da_conferencia`, medidos em 2016-2026 com a
 * saida do setup e a tendencia do papel. Os outros numeros do cartao (ganho
 * medio, duracao, pior fase) sao do historico inteiro.
 */

// So tipos: os testes rodam este arquivo no Node, que nao resolve import de
// valor sem extensao. Por isso gatilho, stop e lote chegam prontos de quem chama.
import type { Grupo, Nivel, Saida } from "./backtest-tela";
import type { Lote } from "./lote";
import type { Setup } from "./setups-tela";

/** Uma linha de `backtest_resultados`, so com o que o cartao usa. */
export type LinhaDoBacktest = {
  setup: string;
  saida: Saida;
  grupo: Grupo;
  periodo: "2016-2026" | "tudo";
  n: number;
  acerto: number | null;
  /** Ganho medio dos trades que terminaram no lucro, em R. */
  ganhoMedio: number | null;
  diasMedio: number | null;
  expectativa: number | null;
  icBaixo: number | null;
  /** Expectativa do setup menos a do controle sorteado. */
  diferenca: number | null;
  /** Null nas rodadas enviadas antes da migration 0020. */
  piorSequencia: number | null;
  piorRecuo: number | null;
};

export type Cor = "verde" | "amarelo" | "vermelho" | "cinza";

/** O que o semaforo diz em cada cor: a palavra e a explicacao de uma linha. */
export const TEXTO_DA_COR: Record<Cor, { nome: string; explicacao: string }> = {
  verde: {
    nome: "Histórico bom",
    explicacao: "deu lucro em 2016–2026 e ganhou de comprar um papel sorteado",
  },
  amarelo: {
    nome: "Histórico duvidoso",
    explicacao: "deu lucro em 2016–2026, mas por pouco: pode ter sido sorte",
  },
  vermelho: {
    nome: "Histórico ruim",
    explicacao: "em 2016–2026 perdeu dinheiro ou perdeu de um papel sorteado",
  },
  cinza: {
    nome: "Sem histórico",
    explicacao: "o backtest não tem trades suficientes desta combinação",
  },
};

const ORDEM_DAS_CORES: Record<Cor, number> = { verde: 0, amarelo: 1, vermelho: 2, cinza: 3 };

/** A tendencia do papel no dia do sinal, como o backtest agrupa. */
export function grupoDoPapel(alta: boolean | null): Grupo {
  if (alta === null) return "todos";
  return alta ? "alta" : "contra";
}

/**
 * Firme, fraco ou falhou a partir de uma linha de 2016-2026: a mesma regra de
 * `nivel_da_conferencia` no Python. Null sem trades ou sem numero.
 */
export function notaDaLinha(l: LinhaDoBacktest | undefined): Nivel | null {
  if (!l || l.n === 0 || l.expectativa === null || l.diferenca === null) return null;
  if (!(l.expectativa > 0 && l.diferenca > 0)) return "falhou";
  return l.icBaixo !== null && l.icBaixo > 0 ? "firme" : "fraco";
}

export function corDaNota(nota: Nivel | null): Cor {
  if (nota === "firme") return "verde";
  if (nota === "fraco") return "amarelo";
  if (nota === "falhou") return "vermelho";
  return "cinza";
}

/** O que quem chama ja calculou de cada setup armado. */
export type BaseDaEntrada = {
  setup: Setup;
  /** A chave do setup no backtest (`chaveDoBacktest`). */
  chave: string;
  /** Compra acima deste preco. */
  gatilho: number;
  stop: number;
  saida: Saida;
  /** Null quando o capital ainda nao foi informado. */
  lote: Lote | null;
};

export type Entrada = BaseDaEntrada & {
  /** (gatilho - stop) / gatilho: a perda no stop, como fracao do preco. */
  riscoPct: number;
  /** Quantos R o alvo pede; null nas saidas sem alvo fixo (minimas, MME 9). */
  multiplo: number | null;
  alvo: number | null;
  alvoPct: number | null;
  /** Ganho medio historico dos trades que deram lucro, como fracao do preco. */
  ganhoMedioPct: number | null;
  /** Em reais para o lote do usuario; null sem lote. */
  perdaEmReais: number | null;
  alvoEmReais: number | null;
  ganhoMedioEmReais: number | null;
  nota: Nivel | null;
  cor: Cor;
  /** Duracao media em pregoes. */
  dias: number | null;
  piorSequencia: number | null;
  /** O recuo da pior fase, em reais para o lote do usuario (negativo). */
  piorRecuoEmReais: number | null;
  /** False quando ha capital informado e nem 1 acao cabe no risco. */
  cabe: boolean;
};

const MULTIPLO: Partial<Record<Saida, number>> = { alvo1: 1, alvo2: 2, alvo3: 3 };

const centavos = (v: number): number => Math.round(v * 100) / 100;

function achar(
  linhas: readonly LinhaDoBacktest[],
  chave: string,
  saida: Saida,
  grupo: Grupo,
  periodo: LinhaDoBacktest["periodo"],
): LinhaDoBacktest | undefined {
  return linhas.find(
    (l) => l.setup === chave && l.saida === saida && l.grupo === grupo && l.periodo === periodo,
  );
}

/** Junta o setup armado com os numeros do backtest da combinacao dele. */
export function montarEntrada(b: BaseDaEntrada, linhas: readonly LinhaDoBacktest[]): Entrada {
  const grupo = grupoDoPapel(b.setup.alta);
  const conferencia = achar(linhas, b.chave, b.saida, grupo, "2016-2026");
  const tudo = achar(linhas, b.chave, b.saida, grupo, "tudo");
  const porAcao = b.gatilho - b.stop;
  const riscoPct = b.gatilho > 0 ? porAcao / b.gatilho : 0;
  const multiplo = MULTIPLO[b.saida] ?? null;
  const ganhoMedio = tudo?.ganhoMedio ?? null;
  const nota = notaDaLinha(conferencia);
  const perda = b.lote && b.lote.quantidade > 0 ? b.lote.perdaMaxima : null;
  return {
    ...b,
    riscoPct,
    multiplo,
    alvo: multiplo === null ? null : centavos(b.gatilho + multiplo * porAcao),
    alvoPct: multiplo === null ? null : multiplo * riscoPct,
    ganhoMedioPct: ganhoMedio === null ? null : ganhoMedio * riscoPct,
    perdaEmReais: perda,
    alvoEmReais: perda === null || multiplo === null ? null : centavos(multiplo * perda),
    ganhoMedioEmReais: perda === null || ganhoMedio === null ? null : centavos(ganhoMedio * perda),
    nota,
    cor: corDaNota(nota),
    dias: tudo?.diasMedio ?? null,
    piorSequencia: tudo?.piorSequencia ?? null,
    piorRecuoEmReais:
      perda === null || tudo?.piorRecuo == null ? null : centavos(tudo.piorRecuo * perda),
    cabe: b.lote === null || b.lote.quantidade > 0,
  };
}

/** Verdes primeiro, depois amarelas, vermelhas e sem historico; dentro da cor, mais volume primeiro. */
export function ordenarEntradas(entradas: readonly Entrada[]): Entrada[] {
  return [...entradas].sort(
    (a, b) =>
      ORDEM_DAS_CORES[a.cor] - ORDEM_DAS_CORES[b.cor] ||
      b.setup.rvol - a.setup.rvol ||
      a.setup.ticker.localeCompare(b.setup.ticker),
  );
}

/** As que cabem no risco do usuario e as que nao cabem (escondidas, com aviso). */
export function separarPeloBolso(entradas: readonly Entrada[]): {
  cabem: Entrada[];
  naoCabem: Entrada[];
} {
  return {
    cabem: entradas.filter((e) => e.cabe),
    naoCabem: entradas.filter((e) => !e.cabe),
  };
}

/** Quantas entradas de cada cor, na ordem do semaforo; cor sem entrada fica de fora. */
export function contarPorCor(entradas: readonly Entrada[]): { cor: Cor; n: number }[] {
  return (Object.keys(ORDEM_DAS_CORES) as Cor[])
    .map((cor) => ({ cor, n: entradas.filter((e) => e.cor === cor).length }))
    .filter((c) => c.n > 0);
}

/** "dura ~6 pregões", com o singular certo; null sem numero. */
export function textoDaDuracao(dias: number | null): string | null {
  if (dias === null || !Number.isFinite(dias)) return null;
  const n = Math.max(1, Math.round(dias));
  return `dura ~${n} ${n === 1 ? "pregão" : "pregões"}`;
}

/** Um candle do mini grafico. */
export type Candle = { dia: string; abre: number; maxima: number; minima: number; fecha: number };

export type CandleDesenhado = {
  x: number;
  largura: number;
  /** Topo e base do pavio e do corpo, em pixels a partir do topo. */
  pavioDe: number;
  pavioAte: number;
  corpoDe: number;
  corpoAte: number;
  subiu: boolean;
};

/**
 * A geometria do mini grafico: os candles e a altura (y) de cada preco marcado
 * (entrada, stop, alvo). A escala inclui os precos marcados: a linha do alvo
 * nao pode cair fora do desenho.
 */
export function desenharCandles(
  candles: readonly Candle[],
  marcas: readonly number[],
  largura: number,
  altura: number,
): { candles: CandleDesenhado[]; y: (preco: number) => number } {
  const precos = [...candles.flatMap((c) => [c.maxima, c.minima]), ...marcas].filter(
    Number.isFinite,
  );
  const topo = precos.length ? Math.max(...precos) : 1;
  const base = precos.length ? Math.min(...precos) : 0;
  const faixa = topo - base || 1;
  const y = (preco: number) => ((topo - preco) / faixa) * altura;
  const passo = candles.length ? largura / candles.length : largura;
  const corpo = Math.max(1, passo * 0.6);
  return {
    y,
    candles: candles.map((c, i) => {
      const de = y(Math.max(c.abre, c.fecha));
      const ate = y(Math.min(c.abre, c.fecha));
      return {
        x: i * passo + (passo - corpo) / 2,
        largura: corpo,
        pavioDe: y(c.maxima),
        pavioAte: y(c.minima),
        corpoDe: de,
        // corpo de pelo menos 1px: o doji nao pode sumir
        corpoAte: Math.max(ate, de + 1),
        subiu: c.fecha >= c.abre,
      };
    }),
  };
}
