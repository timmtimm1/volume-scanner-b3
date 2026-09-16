/**
 * O preco "de agora" de um trade e o rotulo que explica de onde ele veio.
 *
 * Mesma regra em tres telas (cartao da ficha, lista e detalhe de trade): o
 * candle de hoje quando ele e mesmo de hoje na B3 ("agora HH:MM · fonte"),
 * senao o fechamento do snapshot mais recente ("fech. dd/mm"). Um modulo so
 * para nao repetir essa decisao tres vezes com o risco de divergir.
 */

import { diaNaB3, horaNaB3, type CandleDeHoje } from "./candle-de-hoje";
import { diaCurto } from "./formato";

export type PrecoDeAgora = { preco: number; rotulo: string };

/** So os dois campos do snapshot que esta regra usa. */
export type SnapshotParaPreco = { data: string; fechamento: number };

export function precoDeAgora(
  candleHoje: CandleDeHoje | null,
  ultimoSnapshot: SnapshotParaPreco | null,
): PrecoDeAgora | null {
  if (candleHoje && candleHoje.dia === diaNaB3(new Date())) {
    return {
      preco: candleHoje.close,
      rotulo: `agora ${horaNaB3(candleHoje.hora)} · ${candleHoje.fonte}`,
    };
  }
  if (ultimoSnapshot) {
    return { preco: ultimoSnapshot.fechamento, rotulo: `fech. ${diaCurto(ultimoSnapshot.data)}` };
  }
  return null;
}
