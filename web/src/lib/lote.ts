/**
 * Calculadora de lote e o perfil de risco (capital e risco por trade) -- o
 * calculo puro, sem banco. Secao 14 do plano, fase 4.
 *
 * Modulo puro de proposito: sem import de runtime, porque e testado com
 * `node --experimental-strip-types`, e vai tanto para o servidor (validar o
 * perfil) quanto para o navegador (mostrar o lote).
 *
 * Acoes inteiras (mercado fracionario): o lote e o menor entre o que o risco
 * permite e o que o capital compra. E uma conta de tamanho de posicao, nao uma
 * indicacao de quanto comprar: o usuario decide.
 */

import type { Mercado } from "./mercado";

export class PerfilInvalido extends Error {}

export type Perfil = {
  /** Em reais, > 0. */
  capital: number;
  /** Em pontos percentuais (1 = 1%), > 0 e ate 10. */
  riscoPct: number;
};

/** Risco por trade que vale quando o usuario so informa o capital. */
export const RISCO_PADRAO_PCT = 1;
export const RISCO_MAXIMO_PCT = 10;
/** Folga do `numeric(16, 2)` da coluna `capital`: bem abaixo de 10^14. */
export const CAPITAL_MAXIMO = 1_000_000_000_000;

export type EntradaDoLote = {
  capital: number | null | undefined;
  riscoPct: number | null | undefined;
  entrada: number | null | undefined;
  stop: number | null | undefined;
};

export type Lote = {
  /** Acoes inteiras; 0 quando nao ha lote (dado faltando, stop >= entrada, capital curto). */
  quantidade: number;
  /** `quantidade x (entrada - stop)`, em reais. */
  perdaMaxima: number;
  /** `quantidade x entrada`, em reais. */
  valorPosicao: number;
  /** `perdaMaxima / capital`, como fracao (0,0098 = 0,98%). */
  pctDoCapital: number;
  /** O limite foi o capital, nao o risco: o risco permitia mais acoes do que o capital compra. */
  limitadoPeloCapital: boolean;
};

const SEM_LOTE: Lote = {
  quantidade: 0,
  perdaMaxima: 0,
  valorPosicao: 0,
  pctDoCapital: 0,
  limitadoPeloCapital: false,
};

const r2 = (v: number): number => Math.round((v + Number.EPSILON) * 100) / 100;

const positivo = (v: number | null | undefined): v is number =>
  typeof v === "number" && Number.isFinite(v) && v > 0;

/**
 * `min(floor(capital x risco% / (entrada - stop)), floor(capital / entrada))`.
 *
 * O `+ 1e-9` antes do `floor` absorve a sujeira do ponto flutuante: 100 / 0,5
 * pode dar 199,99999999999997 e o lote cairia uma acao sem motivo.
 */
export function calcularLote(e: EntradaDoLote): Lote {
  const { capital, riscoPct, entrada, stop } = e;
  if (!positivo(capital) || !positivo(riscoPct) || !positivo(entrada) || !positivo(stop)) {
    return SEM_LOTE;
  }
  const porAcao = r2(entrada - stop);
  if (!(porAcao > 0)) return SEM_LOTE;

  const pelaRegraDoRisco = Math.floor((capital * riscoPct) / 100 / porAcao + 1e-9);
  const pelaRegraDoCapital = Math.floor(capital / entrada + 1e-9);
  const quantidade = Math.max(0, Math.min(pelaRegraDoRisco, pelaRegraDoCapital));
  const perdaMaxima = r2(quantidade * porAcao);
  return {
    quantidade,
    perdaMaxima,
    valorPosicao: r2(quantidade * entrada),
    pctDoCapital: perdaMaxima / capital,
    limitadoPeloCapital: pelaRegraDoCapital < pelaRegraDoRisco,
  };
}

/**
 * Le um numero digitado do jeito brasileiro: "10.000,50", "10000,5", "10000.5"
 * e "10.000" (ponto de milhar) valem. Null quando nao e um numero.
 *
 * "0.153" e 0,153, nao 153: milhar nunca comeca em zero. Em cripto isso e
 * quantidade comum (0,153 ETH).
 */
export function numeroDoTexto(texto: string): number | null {
  const t = texto.trim().replace(/\s/g, "");
  if (t === "") return null;
  let normal: string;
  if (t.includes(",")) normal = t.replace(/\./g, "").replace(",", ".");
  else if (/^[1-9]\d{0,2}(\.\d{3})+$/.test(t)) normal = t.replace(/\./g, "");
  else normal = t;
  if (!/^\d+(\.\d+)?$/.test(normal)) return null;
  const n = Number(normal);
  return Number.isFinite(n) ? n : null;
}

function duasCasas(v: number): boolean {
  return Math.abs(v - r2(v)) < 1e-9;
}

/**
 * Valida o perfil que chega do navegador: capital > 0 (ate o limite da
 * coluna), risco entre 0 (exclusive) e 10, os dois com no maximo 2 casas.
 * Lanca `PerfilInvalido` com mensagem em portugues.
 */
export function validarPerfil(entrada: { capital?: unknown; riscoPct?: unknown }): Perfil {
  const capital = typeof entrada.capital === "string" ? Number(entrada.capital) : entrada.capital;
  if (typeof capital !== "number" || !Number.isFinite(capital) || capital <= 0) {
    throw new PerfilInvalido("o capital tem de ser maior que zero");
  }
  if (capital > CAPITAL_MAXIMO) throw new PerfilInvalido("o capital está grande demais");
  if (!duasCasas(capital)) throw new PerfilInvalido("o capital aceita no máximo 2 casas decimais");

  const risco = typeof entrada.riscoPct === "string" ? Number(entrada.riscoPct) : entrada.riscoPct;
  if (typeof risco !== "number" || !Number.isFinite(risco) || risco <= 0 || risco > RISCO_MAXIMO_PCT) {
    throw new PerfilInvalido(`o risco por trade tem de ficar entre 0 e ${RISCO_MAXIMO_PCT}%`);
  }
  if (!duasCasas(risco)) throw new PerfilInvalido("o risco aceita no máximo 2 casas decimais");

  return { capital: r2(capital), riscoPct: r2(risco) };
}

/** Casas da quantidade de moeda: as corretoras aceitam ate 8. */
const CASAS_DA_MOEDA = 8;

/**
 * O lote em cripto: a mesma regra do risco, com quantidade FRACIONADA.
 *
 * Na B3 a conta arredonda para acoes inteiras e a distancia ate o stop para
 * centavos. Em cripto compra-se 0,0153 BTC e ha moeda de 0,000004 dolar:
 * nada disso pode ser arredondado para centavo, senao o risco some. A
 * quantidade e truncada (nunca arredondada para cima) na oitava casa.
 *
 * Abaixo de US$ 5 de posicao a corretora nem aceita a ordem: vira "nao cabe".
 */
export const POSICAO_MINIMA_EM_CRIPTO = 5;

export function calcularLoteFracionado(e: EntradaDoLote): Lote {
  const { capital, riscoPct, entrada, stop } = e;
  if (!positivo(capital) || !positivo(riscoPct) || !positivo(entrada) || !positivo(stop)) {
    return SEM_LOTE;
  }
  const porUnidade = entrada - stop;
  if (!(porUnidade > 0)) return SEM_LOTE;

  const pelaRegraDoRisco = (capital * riscoPct) / 100 / porUnidade;
  const pelaRegraDoCapital = capital / entrada;
  const fator = 10 ** CASAS_DA_MOEDA;
  const quantidade =
    Math.floor(Math.min(pelaRegraDoRisco, pelaRegraDoCapital) * fator + 1e-6) / fator;
  if (!(quantidade > 0) || quantidade * entrada < POSICAO_MINIMA_EM_CRIPTO) return SEM_LOTE;
  const perdaMaxima = r2(quantidade * porUnidade);
  return {
    quantidade,
    perdaMaxima,
    valorPosicao: r2(quantidade * entrada),
    pctDoCapital: perdaMaxima / capital,
    limitadoPeloCapital: pelaRegraDoCapital < pelaRegraDoRisco,
  };
}

/**
 * O lote de uma VENDA em cripto (futuros ou margem): o stop fica acima da entrada.
 *
 * A mesma regra do risco, com a distancia `stop - entrada`. Sem alavancagem: a
 * posicao vendida nunca passa do capital, mesmo que o risco permitisse mais.
 */
export function calcularLoteFracionadoVenda(e: EntradaDoLote): Lote {
  const { capital, riscoPct, entrada, stop } = e;
  if (!positivo(capital) || !positivo(riscoPct) || !positivo(entrada) || !positivo(stop)) {
    return SEM_LOTE;
  }
  const porUnidade = stop - entrada;
  if (!(porUnidade > 0)) return SEM_LOTE;

  const pelaRegraDoRisco = (capital * riscoPct) / 100 / porUnidade;
  const pelaRegraDoCapital = capital / entrada;
  const fator = 10 ** CASAS_DA_MOEDA;
  const quantidade =
    Math.floor(Math.min(pelaRegraDoRisco, pelaRegraDoCapital) * fator + 1e-6) / fator;
  if (!(quantidade > 0) || quantidade * entrada < POSICAO_MINIMA_EM_CRIPTO) return SEM_LOTE;
  const perdaMaxima = r2(quantidade * porUnidade);
  return {
    quantidade,
    perdaMaxima,
    valorPosicao: r2(quantidade * entrada),
    pctDoCapital: perdaMaxima / capital,
    limitadoPeloCapital: pelaRegraDoCapital < pelaRegraDoRisco,
  };
}

/** O lote de compra no mercado: acoes inteiras na B3, moeda fracionada em cripto. */
export function loteNoMercado(mercado: Mercado, e: EntradaDoLote): Lote {
  return mercado === "b3" ? calcularLote(e) : calcularLoteFracionado(e);
}
