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
import { TICKER } from "./ticker";
import { alertaVencido, hojeNaB3 } from "./validade";

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
  /** Ultimo pregao em que vale (alerta do setup); null = sem validade. */
  expiraEm: string | null;
  /** O setup que criou o alerta; null nos manuais. */
  setupId: number | null;
  /** Tinha validade e ela passou sem disparar. */
  vencido: boolean;
  /** Ainda vigiando: nao disparou e nao venceu. */
  ativo: boolean;
};

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
  // Opcionais: o banco ganha estas colunas na migration 0014. Ate ela rodar,
  // o `SELECT *` simplesmente nao as traz, e o alerta vale como manual.
  expira_em?: Date | string | null;
  setup_id?: string | number | null;
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
  const expiraEm = r.expira_em ? dia(r.expira_em) : null;
  const vencido = r.disparado_em === null && alertaVencido(expiraEm, hojeNaB3());
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
    expiraEm,
    setupId: r.setup_id === null || r.setup_id === undefined ? null : Number(r.setup_id),
    vencido,
    ativo: r.disparado_em === null && !vencido,
  };
}

// `*` e nao uma lista: assim o site funciona antes e depois da migration 0014,
// que acrescenta `expira_em` e `setup_id` (o deploy do site nao espera o banco).
const COLUNAS = "*";

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

function precoValido(bruto: unknown): number {
  const preco = Number(bruto);
  if (!Number.isFinite(preco) || preco <= 0) {
    throw new DadoInvalido("preco tem de ser um numero positivo");
  }
  return preco;
}

function direcaoValida(bruta: unknown): Direcao {
  const direcao = String(bruta ?? "");
  if (direcao !== "acima" && direcao !== "abaixo") {
    throw new DadoInvalido("direcao aceita 'acima' ou 'abaixo'");
  }
  return direcao;
}

export async function criarAlerta(entrada: {
  ticker: unknown;
  preco: unknown;
  direcao: unknown;
  tradeDate: unknown;
}): Promise<Alerta> {
  const ticker = String(entrada.ticker ?? "").toUpperCase();
  // Validado aqui, e nao so na rota: este e o ponto de entrada do dado, e o
  // ticker salvo vai depois para a URL dos fornecedores de cotacao.
  if (!TICKER.test(ticker)) throw new DadoInvalido("ticker fora do formato da B3");

  const preco = precoValido(entrada.preco);
  const direcao = direcaoValida(entrada.direcao);

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

/**
 * Muda o nivel (e a direcao) de um alerta que ainda esta vigiando.
 *
 * So o ativo muda: o disparado guarda a que preco e quando disparou, e trocar o
 * nivel dele apagaria o porque do disparo. Null quando o alerta nao existe ou
 * ja disparou -- inclusive se disparou entre o arrasto na tela e este UPDATE.
 *
 * O `trade_date` fica: e o pregao em que o alerta foi criado, e nao muda porque
 * a linha andou.
 */
export async function moverAlerta(
  id: number,
  entrada: { preco: unknown; direcao: unknown },
): Promise<Alerta | null> {
  const preco = precoValido(entrada.preco);
  const direcao = direcaoValida(entrada.direcao);
  const { rows } = await conexaoDeAlertas().query<Linha>(
    `UPDATE volume_scanner.price_alerts
        SET preco = $2, direcao = $3
      WHERE id = $1 AND disparado_em IS NULL
      RETURNING ${COLUNAS}`,
    [id, preco, direcao],
  );
  return rows.length ? paraAlerta(rows[0]) : null;
}

/**
 * Religa um alerta ja disparado (ou vencido), limpando o registro do disparo.
 * Tira tambem a validade: o alerta vencido de um setup volta como manual.
 */
export async function reativarAlerta(id: number): Promise<Alerta | null> {
  const { rows } = await conexaoDeAlertas().query<Linha>(
    `UPDATE volume_scanner.price_alerts
        SET disparado_em = NULL, preco_disparo = NULL, fonte_disparo = NULL,
            expira_em = NULL
      WHERE id = $1 RETURNING ${COLUNAS}`,
    [id],
  );
  return rows.length ? paraAlerta(rows[0]) : null;
}
