/**
 * Os dois setups do estudo de cripto de 17/11/2026, para a tela (so contas).
 *
 * A nota e a do proprio estudo (decisao do usuario): backtest no PyBacktestPro,
 * escolha em 2017-2021 e conferencia em 2022-2026. Os numeros sao os mesmos de
 * `scanner/cripto/estudo.py`. Os testes rodam este arquivo no Node.
 */

import type { Cor } from "./entradas";

export type SetupDoEstudo = {
  titulo: string;
  tf: "1d" | "4h";
  lado: "compra" | "venda";
  prazo: number;
  cor: Cor;
  conferencia: number;
  ic: [number, number];
  trades: number;
};

export const SETUPS_DO_ESTUDO: Record<string, SetupDoEstudo> = {
  rsi_reversao: {
    titulo: "Reversão no RSI",
    tf: "1d",
    lado: "compra",
    prazo: 20,
    cor: "amarelo",
    conferencia: 0.116,
    ic: [-0.1, 0.36],
    trades: 1622,
  },
  compressao_venda: {
    titulo: "Compressão na venda",
    tf: "4h",
    lado: "venda",
    prazo: 42,
    cor: "verde",
    conferencia: 0.155,
    ic: [0.005, 0.293],
    trades: 6432,
  },
};

const HORAS = { "1d": 24, "4h": 4 } as const;

/** Quando abriu o candle da entrada: o seguinte ao do sinal (ISO). */
export function aberturaDaEntrada(sinalEm: string, tf: "1d" | "4h"): string {
  return new Date(new Date(sinalEm).getTime() + HORAS[tf] * 3_600_000).toISOString();
}

/** Ate quando o trade pode ficar aberto: a abertura do candle depois do prazo (ISO). */
export function fimDoPrazo(sinalEm: string, tf: "1d" | "4h", prazo: number): string {
  return new Date(new Date(sinalEm).getTime() + (prazo + 2) * HORAS[tf] * 3_600_000).toISOString();
}

/** "+0,12 R por trade em 2022–2026 (intervalo de −0,10 a +0,36, 1.622 trades)". */
export function explicacaoDaNota(s: SetupDoEstudo): string {
  const r = (v: number) =>
    `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2).replace(".", ",")}`;
  return (
    `no estudo, ${r(s.conferencia)} R por trade em 2022–2026 ` +
    `(intervalo de ${r(s.ic[0])} a ${r(s.ic[1])}; ${s.trades.toLocaleString("pt-BR")} trades)`
  );
}
