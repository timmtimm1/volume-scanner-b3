/**
 * Backtest, do lado do site: leitura do resultado que a suite local gravou no
 * banco (migration 0016). Roda em tempo de pedido, depois de `ehDono()`.
 *
 * O site mostra sempre a rodada mais recente. Os tipos e a formatacao moram em
 * `backtest-tela.ts`, que nao importa `pg`.
 */

import { conexaoDeAlertas } from "./db";
import type {
  Ano,
  Escolha,
  Grupo,
  Motivo,
  Nivel,
  Periodo,
  PontoDaCurva,
  Resultado,
  Rodada,
  Saida,
  TradeDoBacktest,
} from "./backtest-tela";

type Numero = number | string | null;

const num = (v: Numero | undefined): number | null => (v === null || v === undefined ? null : Number(v));

/** Date do `pg` (meia-noite local) ou texto, em AAAA-MM-DD. */
function dia(v: Date | string | null): string | null {
  if (v === null) return null;
  if (v instanceof Date) {
    const m = `${v.getMonth() + 1}`.padStart(2, "0");
    const d = `${v.getDate()}`.padStart(2, "0");
    return `${v.getFullYear()}-${m}-${d}`;
  }
  return String(v).slice(0, 10);
}

const TABELA_AUSENTE = "42P01";

export async function rodadaAtual(): Promise<Rodada | null> {
  try {
    const { rows } = await conexaoDeAlertas().query<{
      id: string | number;
      criada_em: Date;
      dados_de: Date | string;
      dados_ate: Date | string;
      custo: Numero;
      teto: number;
      trades: number;
      papeis: number;
    }>(
      `SELECT id, criada_em, dados_de, dados_ate, custo, teto, trades, papeis
         FROM volume_scanner.backtest_rodadas
        ORDER BY id DESC
        LIMIT 1`,
    );
    const r = rows[0];
    if (!r) return null;
    return {
      id: Number(r.id),
      criadaEm: new Date(r.criada_em).toISOString(),
      dadosDe: dia(r.dados_de) ?? "",
      dadosAte: dia(r.dados_ate) ?? "",
      custo: Number(r.custo),
      teto: Number(r.teto),
      trades: Number(r.trades),
      papeis: Number(r.papeis),
    };
  } catch (erro) {
    // Migration ainda nao aplicada: nao ha rodada, e a pagina explica.
    if ((erro as { code?: string }).code === TABELA_AUSENTE) return null;
    throw erro;
  }
}

export async function escolhasDa(rodadaId: number): Promise<Escolha[]> {
  const { rows } = await conexaoDeAlertas().query<{
    setup: string;
    nivel: string;
    saida: string | null;
    grupo: string | null;
    combinacoes: number;
    n_escolha: number | null;
    n_conferencia: number | null;
    exp_escolha: Numero;
    dif_escolha: Numero;
    exp_conferencia: Numero;
    ic_conf_baixo: Numero;
    ic_conf_alto: Numero;
    dif_conferencia: Numero;
  }>(
    `SELECT setup, nivel, saida, grupo, combinacoes, n_escolha, n_conferencia,
            exp_escolha, dif_escolha, exp_conferencia, ic_conf_baixo, ic_conf_alto,
            dif_conferencia
       FROM volume_scanner.backtest_escolhas
      WHERE rodada_id = $1`,
    [rodadaId],
  );
  return rows.map((r) => ({
    setup: r.setup,
    nivel: r.nivel as Nivel,
    saida: r.saida as Saida | null,
    grupo: r.grupo as Grupo | null,
    combinacoes: Number(r.combinacoes),
    nEscolha: num(r.n_escolha),
    nConferencia: num(r.n_conferencia),
    expEscolha: num(r.exp_escolha),
    difEscolha: num(r.dif_escolha),
    expConferencia: num(r.exp_conferencia),
    icConfBaixo: num(r.ic_conf_baixo),
    icConfAlto: num(r.ic_conf_alto),
    difConferencia: num(r.dif_conferencia),
  }));
}

/** As 45 linhas do setup: 5 saidas x 3 grupos x 3 periodos. */
export async function resultadosDo(rodadaId: number, setup: string): Promise<Resultado[]> {
  const { rows } = await conexaoDeAlertas().query<Record<string, Numero | string>>(
    `SELECT setup, saida, grupo, periodo, n, acerto, ganho_medio, perda_media, payoff,
            expectativa, ic_baixo, ic_alto, fator_lucro, dias_medio, r_por_dia,
            controle, diferenca, dif_ic_baixo, dif_ic_alto,
            pct_stop, pct_movel, pct_alvo, pct_mme9, pct_teto
       FROM volume_scanner.backtest_resultados
      WHERE rodada_id = $1 AND setup = $2`,
    [rodadaId, setup],
  );
  return rows.map((r) => ({
    setup: String(r.setup),
    saida: r.saida as Saida,
    grupo: r.grupo as Grupo,
    periodo: r.periodo as Periodo,
    n: Number(r.n),
    acerto: num(r.acerto),
    ganhoMedio: num(r.ganho_medio),
    perdaMedia: num(r.perda_media),
    payoff: num(r.payoff),
    expectativa: num(r.expectativa),
    icBaixo: num(r.ic_baixo),
    icAlto: num(r.ic_alto),
    fatorLucro: num(r.fator_lucro),
    diasMedio: num(r.dias_medio),
    rPorDia: num(r.r_por_dia),
    controle: num(r.controle),
    diferenca: num(r.diferenca),
    difIcBaixo: num(r.dif_ic_baixo),
    difIcAlto: num(r.dif_ic_alto),
    pctStop: num(r.pct_stop),
    pctMovel: num(r.pct_movel),
    pctAlvo: num(r.pct_alvo),
    pctMme9: num(r.pct_mme9),
    pctTeto: num(r.pct_teto),
  }));
}

export async function anosDo(
  rodadaId: number,
  setup: string,
  saida: Saida,
  grupo: Grupo,
): Promise<Ano[]> {
  const { rows } = await conexaoDeAlertas().query<{
    ano: number;
    n: number;
    expectativa: Numero;
    soma_r: Numero;
    controle: Numero;
  }>(
    `SELECT ano, n, expectativa, soma_r, controle
       FROM volume_scanner.backtest_anos
      WHERE rodada_id = $1 AND setup = $2 AND saida = $3 AND grupo = $4
      ORDER BY ano`,
    [rodadaId, setup, saida, grupo],
  );
  return rows.map((r) => ({
    ano: Number(r.ano),
    n: Number(r.n),
    expectativa: num(r.expectativa),
    somaR: num(r.soma_r),
    controle: num(r.controle),
  }));
}

export async function curvaDo(
  rodadaId: number,
  setup: string,
  saida: Saida,
  grupo: Grupo,
): Promise<PontoDaCurva[]> {
  const { rows } = await conexaoDeAlertas().query<{
    mes: Date | string;
    n: number;
    r: Numero;
    controle: Numero;
    acumulado: Numero;
    controle_acumulado: Numero;
    recuo: Numero;
  }>(
    `SELECT mes, n, r, controle, acumulado, controle_acumulado, recuo
       FROM volume_scanner.backtest_curvas
      WHERE rodada_id = $1 AND setup = $2 AND saida = $3 AND grupo = $4
      ORDER BY mes`,
    [rodadaId, setup, saida, grupo],
  );
  return rows.map((r) => ({
    mes: dia(r.mes) ?? "",
    n: Number(r.n),
    r: num(r.r),
    controle: num(r.controle),
    acumulado: num(r.acumulado),
    controleAcumulado: num(r.controle_acumulado),
    recuo: num(r.recuo),
  }));
}

/** Os trades mais recentes do setup e da saida (a amostra que o banco guarda). */
export async function tradesDo(
  rodadaId: number,
  setup: string,
  saida: Saida,
  limite = 50,
): Promise<TradeDoBacktest[]> {
  const { rows } = await conexaoDeAlertas().query<{
    id: string | number;
    setup: string;
    saida: string;
    ticker: string;
    data_sinal: Date | string;
    data_entrada: Date | string;
    data_saida: Date | string | null;
    entrada: Numero;
    stop: Numero;
    preco_saida: Numero;
    motivo: string;
    dias: number | null;
    r: Numero;
    r_controle: Numero;
    alta: boolean | null;
    rvol: Numero;
  }>(
    `SELECT id, setup, saida, ticker, data_sinal, data_entrada, data_saida, entrada, stop,
            preco_saida, motivo, dias, r, r_controle, alta, rvol
       FROM volume_scanner.backtest_trades
      WHERE rodada_id = $1 AND setup = $2 AND saida = $3
      ORDER BY data_entrada DESC, id DESC
      LIMIT $4`,
    [rodadaId, setup, saida, limite],
  );
  return rows.map((r) => ({
    id: Number(r.id),
    setup: r.setup,
    saida: r.saida as Saida,
    ticker: r.ticker,
    dataSinal: dia(r.data_sinal) ?? "",
    dataEntrada: dia(r.data_entrada) ?? "",
    dataSaida: dia(r.data_saida),
    entrada: Number(r.entrada),
    stop: Number(r.stop),
    precoSaida: num(r.preco_saida),
    motivo: r.motivo as Motivo,
    dias: r.dias === null ? null : Number(r.dias),
    r: num(r.r),
    rControle: num(r.r_controle),
    alta: r.alta,
    rvol: num(r.rvol),
  }));
}
