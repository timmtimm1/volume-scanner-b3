/**
 * Formatacao em portugues do Brasil.
 *
 * Campo ausente vira travessao, nunca "NaN" nem zero: papel recem-listado nao
 * tem pos252, e mostrar zero ali seria mentira.
 */

const VAZIO = "—";

const nf = (casas: number) =>
  new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  });

export function numero(v: number | null | undefined, casas = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return VAZIO;
  return nf(casas).format(v);
}

export function percentual(v: number | null | undefined, casas = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return VAZIO;
  const sinal = v >= 0 ? "+" : "−";
  return `${sinal}${nf(casas).format(Math.abs(v) * 100)}%`;
}

/** Percentual sem sinal, para leituras que nao tem direcao (CLV, pos252). */
export function proporcao(v: number | null | undefined, casas = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return VAZIO;
  return `${nf(casas).format(v * 100)}%`;
}

/** Volume financeiro em escala legivel. */
export function dinheiro(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return VAZIO;
  if (Math.abs(v) >= 1e9) return `R$ ${nf(1).format(v / 1e9)} bi`;
  if (Math.abs(v) >= 1e6) return `R$ ${nf(1).format(v / 1e6)} mi`;
  if (Math.abs(v) >= 1e3) return `R$ ${nf(1).format(v / 1e3)} mil`;
  return `R$ ${nf(2).format(v)}`;
}

export function reais(v: number | null | undefined, casas = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return VAZIO;
  return `R$ ${nf(casas).format(v)}`;
}

export function multiplo(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return VAZIO;
  return `${nf(1).format(v)}×`;
}

/** AAAA-MM-DD para DD/MM/AAAA, sem passar por Date (que muda o fuso). */
export function data(iso: string): string {
  const [a, m, d] = iso.split("-");
  return `${d}/${m}/${a}`;
}

export function diaCurto(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

const SEMANA = ["domingo", "segunda", "terca", "quarta", "quinta", "sexta", "sabado"];

export function diaDaSemana(iso: string): string {
  const [a, m, d] = iso.split("-").map(Number);
  return SEMANA[new Date(a, m - 1, d).getDay()];
}

/** Onde o papel esta na faixa do ano, em palavras. */
export function leituraDaFaixa(pos: number | null): string | null {
  if (pos === null || !Number.isFinite(pos)) return null;
  if (pos <= 0.2) return "perto da minima";
  if (pos >= 0.8) return "perto da maxima";
  return null;
}

/**
 * Leitura do ticket medio: alto e bloco institucional, baixo com muitos
 * negocios e correria de varejo. E a informacao que so existe porque a fonte
 * e o COTAHIST, e o plano pede destaque para ela.
 */
export function leituraDoTicket(
  ticket: number | null,
  ticketZ: number | null,
  negocios: number | null,
): string | null {
  if (ticket === null || ticketZ === null) return null;
  if (ticketZ >= 2) return "bloco institucional";
  if (ticketZ <= -1 && (negocios ?? 0) > 5000) return "varejo em peso";
  if (ticketZ >= 1) return "ticket acima do normal";
  return null;
}
