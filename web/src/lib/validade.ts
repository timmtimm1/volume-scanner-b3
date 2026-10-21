/**
 * Validade dos alertas de rompimento.
 *
 * O alerta criado pelo setup (aba Setups) so vale no pregao seguinte ao
 * candle: e ali que o setup confirma ou nao. Depois disso ele nao e mais
 * checado, e a tela tem de dizer "venceu", nao "vigiando". Alerta manual nao
 * tem validade (`expiraEm` nulo).
 *
 * Modulo sem banco nem DOM, para os testes rodarem no Node.
 */

// "en-CA" formata como AAAA-MM-DD, o mesmo formato das datas do banco.
const DIA_NA_B3 = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/Sao_Paulo",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** O dia em Sao Paulo, e nao o do servidor (UTC). */
export function hojeNaB3(agora: Date = new Date()): string {
  return DIA_NA_B3.format(agora);
}

/** Venceu: tinha validade e o ultimo pregao dela ja passou. */
export function alertaVencido(expiraEm: string | null, hoje: string): boolean {
  return expiraEm !== null && expiraEm < hoje;
}
