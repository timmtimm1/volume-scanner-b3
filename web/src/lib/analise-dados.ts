/**
 * A aba Analise, do lado do servidor: le as tabelas `analise_*` de cripto.
 * Nunca le `fechamentos` nem `volumes` de `analise_moedas` (uns 10 MB). As
 * contas moram em `analise.ts`. Sempre depois de `ehDono()`.
 */

import type { LinhaAnual, LinhaMensal, MoedaDaAnalise, PontoMovel } from "./analise";
import { conexaoDeAlertas } from "./db";
import { noMercado } from "./mercado-servidor";

const MERCADO = "cripto" as const;

type LinhaDeMoeda = {
  moeda: string;
  fonte: string;
  negociando: boolean;
  primeiro_dia: string;
  ultimo_dia: string;
  volume_12m: number | null;
  no_top: boolean;
};

type LinhaDeAnual = {
  moeda: string;
  ano: number;
  inicio: string;
  fim: string;
  parcial: boolean;
  retorno: number | null;
  retorno_btc: number | null;
  relativo: number | null;
  beta: number | null;
  correlacao: number | null;
  dias: number;
};

type LinhaDeMensal = {
  moeda: string;
  mes: string;
  inicio: string;
  fim: string;
  parcial: boolean;
  retorno: number | null;
  retorno_btc: number | null;
  relativo: number | null;
};

const paraMoeda = (r: LinhaDeMoeda): MoedaDaAnalise => ({
  moeda: r.moeda,
  fonte: r.fonte,
  negociando: r.negociando,
  primeiroDia: r.primeiro_dia,
  ultimoDia: r.ultimo_dia,
  volume12m: r.volume_12m,
  noTop: r.no_top,
});

const paraAnual = (r: LinhaDeAnual): LinhaAnual => ({
  moeda: r.moeda,
  ano: Number(r.ano),
  inicio: r.inicio,
  fim: r.fim,
  parcial: r.parcial,
  retorno: r.retorno,
  retornoBtc: r.retorno_btc,
  relativo: r.relativo,
  beta: r.beta,
  correlacao: r.correlacao,
  dias: Number(r.dias),
});

const paraMensal = (r: LinhaDeMensal): LinhaMensal => ({
  moeda: r.moeda,
  mes: r.mes,
  inicio: r.inicio,
  fim: r.fim,
  parcial: r.parcial,
  retorno: r.retorno,
  retornoBtc: r.retorno_btc,
  relativo: r.relativo,
});

const COLUNAS_DA_MOEDA = `m.moeda, m.fonte, m.negociando, m.primeiro_dia::text AS primeiro_dia,
       m.ultimo_dia::text AS ultimo_dia, m.volume_12m, COALESCE(t.no_top, false) AS no_top`;

// Com o prefixo `a.`: a visao geral junta `analise_moedas`, que tambem tem `moeda`.
const COLUNAS_ANUAIS = `a.moeda, a.ano::int AS ano, a.inicio::text AS inicio, a.fim::text AS fim,
       a.parcial, a.retorno, a.retorno_btc, a.relativo, a.beta, a.correlacao, a.dias::int AS dias`;

/** Todas as moedas da analise (as que ficaram de fora vao so em contagem). */
export async function lerVisaoGeral() {
  const { moedas, anuais, fora } = await noMercado(MERCADO, async () => {
    const pool = conexaoDeAlertas();
    const [{ rows: moedas }, { rows: anuais }, { rows: fora }] = await Promise.all([
      pool.query<LinhaDeMoeda>(
        `SELECT ${COLUNAS_DA_MOEDA}
           FROM volume_scanner.analise_moedas m
           LEFT JOIN volume_scanner.moedas t ON t.ticker = m.moeda
          WHERE m.fora_por IS NULL
          ORDER BY m.moeda`,
      ),
      pool.query<LinhaDeAnual>(
        `SELECT ${COLUNAS_ANUAIS}
           FROM volume_scanner.analise_anual a
           JOIN volume_scanner.analise_moedas m ON m.moeda = a.moeda
          WHERE m.fora_por IS NULL
          ORDER BY a.moeda, a.ano`,
      ),
      pool.query<{ motivo: string; n: number }>(
        `SELECT fora_por AS motivo, count(*)::int AS n
           FROM volume_scanner.analise_moedas
          WHERE fora_por IS NOT NULL
          GROUP BY fora_por
          ORDER BY n DESC`,
      ),
    ]);
    return { moedas, anuais, fora };
  });

  const lista = moedas.map(paraMoeda);
  const btc = lista.find((m) => m.moeda === "BTC");
  return {
    ate: btc?.ultimoDia ?? null,
    moedas: lista,
    anuais: anuais.map(paraAnual),
    fora: fora.map((f) => ({ motivo: f.motivo, n: Number(f.n) })),
  };
}

/** Uma moeda por inteiro, ou `null` se nao existe ou ficou de fora da analise. */
export async function lerMoeda(moeda: string) {
  const { cabeca, anuais, mensais, movel, btc } = await noMercado(MERCADO, async () => {
    const pool = conexaoDeAlertas();
    const [{ rows: cabeca }, { rows: anuais }, { rows: mensais }, { rows: movel }, { rows: btc }] =
      await Promise.all([
        pool.query<LinhaDeMoeda & { fora_por: string | null }>(
          `SELECT ${COLUNAS_DA_MOEDA}, m.fora_por
             FROM volume_scanner.analise_moedas m
             LEFT JOIN volume_scanner.moedas t ON t.ticker = m.moeda
            WHERE m.moeda = $1`,
          [moeda],
        ),
        pool.query<LinhaDeAnual>(
          `SELECT ${COLUNAS_ANUAIS}
             FROM volume_scanner.analise_anual a
            WHERE moeda = $1
            ORDER BY ano`,
          [moeda],
        ),
        pool.query<LinhaDeMensal>(
          `SELECT moeda, mes::text AS mes, inicio::text AS inicio, fim::text AS fim, parcial,
                  retorno, retorno_btc, relativo
             FROM volume_scanner.analise_mensal
            WHERE moeda = $1
            ORDER BY mes`,
          [moeda],
        ),
        pool.query<{ dia: string; beta: number | null; correlacao: number | null; dias: number }>(
          `SELECT dia::text AS dia, beta, correlacao, dias::int AS dias
             FROM volume_scanner.analise_movel
            WHERE moeda = $1
            ORDER BY dia`,
          [moeda],
        ),
        pool.query<{ ultimo_dia: string }>(
          `SELECT ultimo_dia::text AS ultimo_dia
             FROM volume_scanner.analise_moedas
            WHERE moeda = 'BTC'`,
        ),
      ]);
    return { cabeca, anuais, mensais, movel, btc };
  });

  if (cabeca.length === 0 || cabeca[0].fora_por !== null) return null;
  const pontos: PontoMovel[] = movel.map((p) => ({
    dia: p.dia,
    beta: p.beta,
    correlacao: p.correlacao,
    dias: Number(p.dias),
  }));
  return {
    moeda: paraMoeda(cabeca[0]),
    anuais: anuais.map(paraAnual),
    mensais: mensais.map(paraMensal),
    movel: pontos,
    ate: btc[0]?.ultimo_dia ?? null,
  };
}
