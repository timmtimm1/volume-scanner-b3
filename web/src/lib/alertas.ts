/**
 * Alertas de rompimento, do lado do site.
 *
 * Diferente do resto de `db.ts`, estas consultas NAO rodam em tempo de build:
 * elas atendem as rotas de API, com o site ja no ar. Sao a unica parte do
 * sistema em que o navegador escreve no banco -- e por isso a unica que exige
 * sessao. Toda funcao daqui e chamada apenas depois de `ehDono()`.
 *
 * A validacao mora aqui e nao so na rota: quem escreve no banco valida o que
 * escreve, independentemente de quem chamou.
 */

import { conexaoDeAlertas } from "./db";

export type Direcao = "acima" | "abaixo";

export type Alerta = {
  id: number;
  ticker: string;
  tradeDate: string;
  preco: number;
  direcao: Direcao;
  criadoEm: string;
  disparadoEm: string | null;
  precoDisparo: number | null;
  fonteDisparo: string | null;
  ativo: boolean;
};

/**
 * Mesmo formato que o Python valida antes de mandar o ticker para a URL dos
 * fornecedores de cotacao. Repetido aqui de proposito: este e o ponto de
 * entrada do dado, e barrar na porta e mais barato do que confiar que a outra
 * ponta barra.
 */
const TICKER = /^[A-Z]{4}\d{1,2}[A-Z]?$/;

type Linha = {
  id: string | number;
  ticker: string;
  trade_date: Date | string;
  preco: string | number;
  direcao: string;
  criado_em: Date | string;
  disparado_em: Date | string | null;
  preco_disparo: string | number | null;
  fonte_disparo: string | null;
};

function dia(v: Date | string): string {
  if (v instanceof Date) {
    const m = `${v.getMonth() + 1}`.padStart(2, "0");
    const d = `${v.getDate()}`.padStart(2, "0");
    return `${v.getFullYear()}-${m}-${d}`;
  }
  return String(v).slice(0, 10);
}

function paraAlerta(r: Linha): Alerta {
  return {
    id: Number(r.id),
    ticker: r.ticker,
    tradeDate: dia(r.trade_date),
    preco: Number(r.preco),
    direcao: r.direcao === "acima" ? "acima" : "abaixo",
    criadoEm: new Date(r.criado_em).toISOString(),
    disparadoEm: r.disparado_em ? new Date(r.disparado_em).toISOString() : null,
    precoDisparo: r.preco_disparo === null ? null : Number(r.preco_disparo),
    fonteDisparo: r.fonte_disparo,
    ativo: r.disparado_em === null,
  };
}

const COLUNAS = `id, ticker, trade_date, preco, direcao, criado_em,
                 disparado_em, preco_disparo, fonte_disparo`;

export async function listarAlertas(ticker?: string): Promise<Alerta[]> {
  const filtro = ticker ? "WHERE ticker = $1" : "";
  const { rows } = await conexaoDeAlertas().query<Linha>(
    `SELECT ${COLUNAS} FROM volume_scanner.price_alerts ${filtro}
      ORDER BY (disparado_em IS NULL) DESC, criado_em DESC`,
    ticker ? [ticker.toUpperCase()] : [],
  );
  return rows.map(paraAlerta);
}

export class DadoInvalido extends Error {}

export async function criarAlerta(entrada: {
  ticker: unknown;
  preco: unknown;
  direcao: unknown;
  tradeDate: unknown;
}): Promise<Alerta> {
  const ticker = String(entrada.ticker ?? "").toUpperCase();
  if (!TICKER.test(ticker)) throw new DadoInvalido("ticker fora do formato da B3");

  const preco = Number(entrada.preco);
  if (!Number.isFinite(preco) || preco <= 0) {
    throw new DadoInvalido("preco tem de ser um numero positivo");
  }

  const direcao = String(entrada.direcao ?? "");
  if (direcao !== "acima" && direcao !== "abaixo") {
    throw new DadoInvalido("direcao aceita 'acima' ou 'abaixo'");
  }

  const tradeDate = String(entrada.tradeDate ?? "");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(tradeDate)) {
    throw new DadoInvalido("data do pregao fora do formato AAAA-MM-DD");
  }

  const { rows } = await conexaoDeAlertas().query<Linha>(
    `INSERT INTO volume_scanner.price_alerts (ticker, trade_date, preco, direcao)
     VALUES ($1, $2, $3, $4) RETURNING ${COLUNAS}`,
    [ticker, tradeDate, preco, direcao],
  );
  return paraAlerta(rows[0]);
}

export async function apagarAlerta(id: number): Promise<boolean> {
  const r = await conexaoDeAlertas().query(
    "DELETE FROM volume_scanner.price_alerts WHERE id = $1",
    [id],
  );
  return (r.rowCount ?? 0) > 0;
}

/** Religa um alerta ja disparado, limpando o registro do disparo. */
export async function reativarAlerta(id: number): Promise<Alerta | null> {
  const { rows } = await conexaoDeAlertas().query<Linha>(
    `UPDATE volume_scanner.price_alerts
        SET disparado_em = NULL, preco_disparo = NULL, fonte_disparo = NULL
      WHERE id = $1 RETURNING ${COLUNAS}`,
    [id],
  );
  return rows.length ? paraAlerta(rows[0]) : null;
}
