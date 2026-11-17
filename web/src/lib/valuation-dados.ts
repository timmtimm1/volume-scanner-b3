/**
 * O valuation de todas as empresas de uma vez, para a pagina /valuation.
 *
 * A ficha de um papel le os fundamentos dele com cinco consultas. Repetir isso
 * para os ~440 papeis seriam 2 mil consultas por visita; aqui sao cinco no
 * total, e cada empresa e montada em memoria no mesmo formato da ficha
 * (`Fundamentos`), para passar pela MESMA conta: `indicadoresNaData`, com as
 * seis camadas de conferencia da contagem de acoes. Um numero da lista tem de
 * ser igual ao da ficha do mesmo papel.
 */

import { cache } from "react";
import { conexaoDeAlertas, desdobramentosDosSaltos, SALTOS_DE_ABERTURA } from "./db";
import { fatorAteODia, indicadoresNaData } from "./fundamentos";
import type { Fundamentos, Provento, Trimestre } from "./types";
import {
  type Avaliacao,
  avaliar,
  crescimentoDoLucro,
  type Premissas,
  premissasPadrao,
  proventoMedioAnual,
} from "./valuation";

const TABELA_AUSENTE = "42P01";

type Numero = string | number | null;

function num(v: Numero): number | null {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function dia(v: Date | string): string {
  if (v instanceof Date) {
    const m = `${v.getMonth() + 1}`.padStart(2, "0");
    const d = `${v.getDate()}`.padStart(2, "0");
    return `${v.getFullYear()}-${m}-${d}`;
  }
  return String(v).slice(0, 10);
}

/**
 * O juro anual que entra na taxa de desconto, como fracao (0,1287).
 *
 * O prefixado de 10 anos do Tesouro, que e o juro de prazo comparavel ao de
 * uma acao; na falta dele, a Selic. Vem da serie semanal do resumo da semana.
 * `null` sem a tabela ou sem dado: a conta usa o valor de reserva.
 */
export const juroLongo = cache(async (): Promise<number | null> => {
  try {
    const { rows } = await conexaoDeAlertas().query<{ serie: string; taxa: number }>(
      `SELECT DISTINCT ON (serie) serie, taxa::float8 AS taxa
         FROM volume_scanner.juros_historico
        WHERE serie IN ('pre_10a', 'selic')
        ORDER BY serie, semana DESC`,
    );
    const de = (serie: string) => rows.find((r) => r.serie === serie)?.taxa ?? null;
    const taxa = de("pre_10a") ?? de("selic");
    return taxa !== null && taxa > 0 ? taxa / 100 : null;
  } catch (erro) {
    if ((erro as { code?: string }).code === TABELA_AUSENTE) return null;
    throw erro;
  }
});

export type LinhaDeValuation = {
  ticker: string;
  empresa: string;
  setor: string | null;
  preco: number;
  /** Mediana do volume financeiro nos ultimos 60 pregoes do papel. */
  volume: number | null;
  /** Rotulo do balanco usado ("3T26") e quando foi publicado. */
  trimestre: string;
  publicadoEm: string | null;
  lucroPorAcao: number | null;
  valorPatrimonialPorAcao: number | null;
  proventoMedio: number | null;
  premissas: Premissas;
  /** Graham, Bazin e fluxo de caixa, nesta ordem. */
  avaliacoes: Avaliacao[];
};

export type ValuationDeTodos = {
  /** Pregao dos precos. */
  data: string | null;
  juro: number | null;
  linhas: LinhaDeValuation[];
};

const TRIMESTRES_POR_EMPRESA = 12;

export async function valuationDeTodos(): Promise<ValuationDeTodos> {
  const pool = conexaoDeAlertas();
  const ultimo = await pool.query<{ data: Date | string | null }>(
    `SELECT max(trade_date) AS data FROM volume_scanner.daily_bars`,
  );
  const bruto = ultimo.rows[0]?.data ?? null;
  if (bruto === null) return { data: null, juro: null, linhas: [] };
  const data = dia(bruto);

  const [papeis, trimestres, proventos, picos, juro] = await Promise.all([
    pool.query<{
      ticker: string;
      cd_cvm: number;
      classe: string | null;
      nome: string;
      setor_cvm: string | null;
      close: Numero;
      liquidez: Numero;
      mediana: Numero;
    }>(
      `WITH janela AS (
          SELECT DISTINCT trade_date FROM volume_scanner.daily_bars
           ORDER BY trade_date DESC LIMIT 60
       ),
       volume AS (
          SELECT b.ticker,
                 SUM(b.volume_financial) AS liquidez,
                 percentile_cont(0.5) WITHIN GROUP (ORDER BY b.volume_financial) AS mediana
            FROM volume_scanner.daily_bars b
           WHERE b.trade_date IN (SELECT trade_date FROM janela)
           GROUP BY b.ticker
       )
       SELECT t.ticker, t.cd_cvm, t.classe, e.setor_cvm,
              COALESCE(NULLIF(TRIM(e.nome_comercial), ''), e.nome) AS nome,
              b.close, v.liquidez, v.mediana
         FROM volume_scanner.empresa_tickers t
         JOIN volume_scanner.empresas e USING (cd_cvm)
         JOIN volume_scanner.daily_bars b ON b.ticker = t.ticker AND b.trade_date = $1
         LEFT JOIN volume v ON v.ticker = t.ticker`,
      [data],
    ),
    pool.query<Record<string, Numero | Date>>(
      `SELECT * FROM (
          SELECT f.cd_cvm, f.dt_fim, f.rotulo, f.origem, f.publicado_em, f.layout,
                 f.receita_tri, f.ebitda_tri, f.lucro_tri,
                 f.receita_12m, f.ebitda_12m, f.lucro_12m,
                 f.patrimonio_liquido, f.ativo_total, f.divida_liquida,
                 f.liquidez_corrente, f.acoes_em_circulacao,
                 b.acoes_on - COALESCE(b.tesouraria_on, 0) AS acoes_on,
                 b.acoes_pn - COALESCE(b.tesouraria_pn, 0) AS acoes_pn,
                 row_number() OVER (PARTITION BY f.cd_cvm ORDER BY f.dt_fim DESC) AS ordem
            FROM volume_scanner.fundamentos_trimestre f
            LEFT JOIN volume_scanner.cvm_balancos b
                   ON b.cd_cvm = f.cd_cvm AND b.dt_refer = f.dt_fim
       ) x
        WHERE ordem <= $1
        ORDER BY cd_cvm, dt_fim`,
      [TRIMESTRES_POR_EMPRESA],
    ),
    pool.query<{ ticker: string; data_com: Date | string; tipo: string; valor: Numero }>(
      `SELECT ticker, data_com, tipo, valor
         FROM volume_scanner.proventos
        WHERE data_com > CURRENT_DATE - INTERVAL '4 years'
        ORDER BY ticker, data_com`,
    ),
    pool.query<{ cd_cvm: number; pico: Numero }>(
      `SELECT t.cd_cvm, MAX(b.volume_shares) AS pico
         FROM volume_scanner.daily_bars b
         JOIN volume_scanner.empresa_tickers t USING (ticker)
        WHERE t.cd_cvm IS NOT NULL AND b.trade_date > CURRENT_DATE - INTERVAL '1 year'
        GROUP BY t.cd_cvm`,
    ),
    juroLongo(),
  ]);
  const desdobramentos = desdobramentosDosSaltos(
    (await pool.query(SALTOS_DE_ABERTURA, [papeis.rows.map((r) => r.ticker)])).rows,
  );

  const trimestresDe = new Map<number, Trimestre[]>();
  for (const r of trimestres.rows) {
    const lista = trimestresDe.get(Number(r.cd_cvm)) ?? [];
    lista.push({
      dtFim: dia(r.dt_fim as Date | string),
      rotulo: String(r.rotulo),
      origem: String(r.origem),
      publicadoEm: r.publicado_em === null ? null : dia(r.publicado_em as Date | string),
      layout: r.layout === null ? null : String(r.layout),
      receitaTri: num(r.receita_tri as Numero),
      ebitdaTri: num(r.ebitda_tri as Numero),
      lucroTri: num(r.lucro_tri as Numero),
      receita12m: num(r.receita_12m as Numero),
      ebitda12m: num(r.ebitda_12m as Numero),
      lucro12m: num(r.lucro_12m as Numero),
      patrimonioLiquido: num(r.patrimonio_liquido as Numero),
      ativoTotal: num(r.ativo_total as Numero),
      dividaLiquida: num(r.divida_liquida as Numero),
      liquidezCorrente: num(r.liquidez_corrente as Numero),
      acoesEmCirculacao: num(r.acoes_em_circulacao as Numero),
      acoesOn: num(r.acoes_on as Numero),
      acoesPn: num(r.acoes_pn as Numero),
    });
    trimestresDe.set(Number(r.cd_cvm), lista);
  }

  const proventosDe = new Map<string, Provento[]>();
  for (const r of proventos.rows) {
    const lista = proventosDe.get(r.ticker) ?? [];
    lista.push({ dataCom: dia(r.data_com), tipo: String(r.tipo), valor: num(r.valor) ?? 0 });
    proventosDe.set(r.ticker, lista);
  }
  const picoDe = new Map(picos.rows.map((r) => [Number(r.cd_cvm), num(r.pico)]));

  // O preco de cada classe da empresa no pregao: a ON, e a PN mais liquida
  // (a mesma escolha de `precosPorClasse` na ficha).
  const classesDe = new Map<number, { on: number | null; pn: number | null; liquidezPn: number }>();
  for (const r of papeis.rows) {
    const fechamento = num(r.close);
    if (fechamento === null || r.classe === null) continue;
    const atual = classesDe.get(r.cd_cvm) ?? { on: null, pn: null, liquidezPn: -1 };
    if (r.classe === "ON") atual.on = fechamento;
    else if (r.classe.startsWith("PN")) {
      const liquidez = num(r.liquidez) ?? 0;
      if (liquidez > atual.liquidezPn) {
        atual.pn = fechamento;
        atual.liquidezPn = liquidez;
      }
    }
    classesDe.set(r.cd_cvm, atual);
  }

  const linhas: LinhaDeValuation[] = [];
  for (const r of papeis.rows) {
    const preco = num(r.close);
    const serie = trimestresDe.get(r.cd_cvm);
    if (preco === null || !serie || serie.length === 0) continue;
    const classes = classesDe.get(r.cd_cvm);
    const dados: Fundamentos = {
      empresa: r.nome,
      setor: r.setor_cvm,
      classe: r.classe,
      trimestres: serie,
      proventos: proventosDe.get(r.ticker) ?? [],
      precosPorClasse: {
        on: classes?.on != null ? { [data]: classes.on } : {},
        pn: classes?.pn != null ? { [data]: classes.pn } : {},
      },
      picoDeVolumeEmAcoes: picoDe.get(r.cd_cvm) ?? null,
      desdobramentos: desdobramentos[r.ticker] ?? [],
    };
    const indicadores = indicadoresNaData(
      dados,
      [{ tradeDate: data, open: preco, high: preco, low: preco, close: preco, volumeFinancial: 0 }],
      data,
    );
    if (indicadores === null) continue;
    const ate = serie.slice(0, serie.findIndex((t) => t.dtFim === indicadores.trimestre.dtFim) + 1);
    const premissas = premissasPadrao(crescimentoDoLucro(ate), juro);
    const proventoMedio = proventoMedioAnual(dados.proventos, data, undefined, (dataCom) =>
      fatorAteODia(dataCom, data, dados.desdobramentos ?? []),
    );
    linhas.push({
      ticker: r.ticker,
      empresa: r.nome,
      setor: r.setor_cvm,
      preco,
      volume: num(r.mediana),
      trimestre: indicadores.trimestre.rotulo,
      publicadoEm: indicadores.trimestre.publicadoEm,
      lucroPorAcao: indicadores.lucroPorAcao,
      valorPatrimonialPorAcao: indicadores.valorPatrimonialPorAcao,
      proventoMedio,
      premissas,
      avaliacoes: avaliar(
        {
          preco,
          lucroPorAcao: indicadores.lucroPorAcao,
          valorPatrimonialPorAcao: indicadores.valorPatrimonialPorAcao,
          proventoMedio,
          acoesConfiaveis: indicadores.acoesConfiaveis,
        },
        premissas,
      ),
    });
  }
  linhas.sort((a, b) => a.ticker.localeCompare(b.ticker));
  return { data, juro, linhas };
}
