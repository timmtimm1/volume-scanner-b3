/**
 * A aba Analise, do lado do servidor: le as tabelas `analise_*` de cripto.
 * Nunca le `fechamentos` nem `volumes` de `analise_moedas` (uns 10 MB). As
 * contas moram em `analise.ts`. Sempre depois de `ehDono()`.
 */

import type {
  AnoDaJanela,
  CandidatoAoRanking,
  JanelaDoEstudo,
  LadoDoEstudo,
  LinhaAnual,
  LinhaMensal,
  MesDaCesta,
  MesSazonal,
  MoedaDaAnalise,
  PeriodoDoAno,
  PontoMovel,
  VereditoDoEstudo,
} from "./analise";
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

type LinhaDeSazonal = {
  moeda?: string;
  mes: number;
  retorno: number | null;
  relativo: number | null;
  subiu: number;
  ganhou: number;
  anos: number;
};

const paraSazonal = (r: LinhaDeSazonal): MesSazonal => ({
  moeda: r.moeda ?? "",
  mes: Number(r.mes),
  retorno: r.retorno,
  relativo: r.relativo,
  subiu: Number(r.subiu),
  ganhou: Number(r.ganhou),
  anos: Number(r.anos),
});

/**
 * A aba Sazonalidade: a mediana de cada mes do calendario, por moeda e para o
 * mercado. So entra mes completo. `mercado` e a moeda tipica: para cada mes de
 * cada ano, a mediana entre as moedas (sem o BTC); depois, a mediana dos anos.
 */
export async function lerSazonalidade() {
  const { moedas, meses, mercado } = await noMercado(MERCADO, async () => {
    const pool = conexaoDeAlertas();
    const [{ rows: moedas }, { rows: meses }, { rows: mercado }] = await Promise.all([
      pool.query<LinhaDeMoeda>(
        `SELECT ${COLUNAS_DA_MOEDA}
           FROM volume_scanner.analise_moedas m
           LEFT JOIN volume_scanner.moedas t ON t.ticker = m.moeda
          WHERE m.fora_por IS NULL
          ORDER BY m.moeda`,
      ),
      pool.query<LinhaDeSazonal>(
        `SELECT x.moeda, extract(month FROM x.mes)::int AS mes,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY x.retorno) AS retorno,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY x.relativo) AS relativo,
                count(*) FILTER (WHERE x.retorno > 0)::int AS subiu,
                count(*) FILTER (WHERE x.relativo > 0)::int AS ganhou,
                count(*)::int AS anos
           FROM volume_scanner.analise_mensal x
           JOIN volume_scanner.analise_moedas m ON m.moeda = x.moeda
          WHERE NOT x.parcial AND m.fora_por IS NULL
          GROUP BY 1, 2`,
      ),
      pool.query<LinhaDeSazonal>(
        `WITH tipica AS (
           SELECT x.mes,
                  percentile_cont(0.5) WITHIN GROUP (ORDER BY x.retorno) AS retorno,
                  percentile_cont(0.5) WITHIN GROUP (ORDER BY x.relativo) AS relativo
             FROM volume_scanner.analise_mensal x
             JOIN volume_scanner.analise_moedas m ON m.moeda = x.moeda
            WHERE NOT x.parcial AND m.fora_por IS NULL AND x.moeda <> 'BTC'
            GROUP BY x.mes
         )
         SELECT extract(month FROM mes)::int AS mes,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY retorno) AS retorno,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY relativo) AS relativo,
                count(*) FILTER (WHERE retorno > 0)::int AS subiu,
                count(*) FILTER (WHERE relativo > 0)::int AS ganhou,
                count(*)::int AS anos
           FROM tipica GROUP BY 1`,
      ),
    ]);
    return { moedas, meses, mercado };
  });

  const lista = moedas.map(paraMoeda);
  const btc = lista.find((m) => m.moeda === "BTC");
  return {
    ate: btc?.ultimoDia ?? null,
    moedas: lista,
    meses: meses.map(paraSazonal),
    mercado: mercado.map(paraSazonal),
  };
}

type LinhaDeCesta = { mes: string; retorno: number; retorno_btc: number | null; moedas: number };

type LinhaDeJanela = {
  lado: string;
  inicio_mes: number;
  meses: number;
  posicao: number | null;
  veredito: string;
  escolha_media: number | null;
  escolha_mediana: number | null;
  escolha_positivos: number;
  escolha_anos: number;
  escolha_controle: number | null;
  conferencia_media: number | null;
  conferencia_mediana: number | null;
  conferencia_positivos: number;
  conferencia_anos: number;
  conferencia_controle: number | null;
  todos_media: number | null;
  todos_mediana: number | null;
  todos_positivos: number;
  todos_anos: number;
};

type LinhaDeAnoDaJanela = {
  lado: string;
  inicio_mes: number;
  meses: number;
  ano: number;
  periodo: string;
  resultado: number;
};

const paraJanela = (r: LinhaDeJanela): JanelaDoEstudo => ({
  lado: r.lado as LadoDoEstudo,
  inicioMes: Number(r.inicio_mes),
  meses: Number(r.meses),
  posicao: r.posicao === null ? null : Number(r.posicao),
  veredito: r.veredito as VereditoDoEstudo,
  escolhaMedia: r.escolha_media,
  escolhaMediana: r.escolha_mediana,
  escolhaPositivos: Number(r.escolha_positivos),
  escolhaAnos: Number(r.escolha_anos),
  escolhaControle: r.escolha_controle,
  conferenciaMedia: r.conferencia_media,
  conferenciaMediana: r.conferencia_mediana,
  conferenciaPositivos: Number(r.conferencia_positivos),
  conferenciaAnos: Number(r.conferencia_anos),
  conferenciaControle: r.conferencia_controle,
  todosMedia: r.todos_media,
  todosMediana: r.todos_mediana,
  todosPositivos: Number(r.todos_positivos),
  todosAnos: Number(r.todos_anos),
});

/**
 * O estudo "quando comprar e quando vender" (`scanner/cripto/sazonal.py`): a
 * cesta mes a mes, as 144 janelas e o resultado de cada janela em cada ano.
 * Se as tabelas ainda nao existem, o Postgres responde 42P01 (ver `semCripto`).
 */
export async function lerEstudoSazonal() {
  const { cesta, janelas, anos } = await noMercado(MERCADO, async () => {
    const pool = conexaoDeAlertas();
    const [{ rows: cesta }, { rows: janelas }, { rows: anos }] = await Promise.all([
      pool.query<LinhaDeCesta>(
        `SELECT mes::text AS mes, retorno, retorno_btc, moedas::int AS moedas
           FROM volume_scanner.analise_cesta
          ORDER BY mes`,
      ),
      pool.query<LinhaDeJanela>(
        `SELECT lado, inicio_mes::int AS inicio_mes, meses::int AS meses, posicao::int AS posicao,
                veredito,
                escolha_media, escolha_mediana, escolha_positivos::int AS escolha_positivos,
                escolha_anos::int AS escolha_anos, escolha_controle,
                conferencia_media, conferencia_mediana,
                conferencia_positivos::int AS conferencia_positivos,
                conferencia_anos::int AS conferencia_anos, conferencia_controle,
                todos_media, todos_mediana, todos_positivos::int AS todos_positivos,
                todos_anos::int AS todos_anos
           FROM volume_scanner.analise_janelas
          ORDER BY lado, posicao NULLS LAST, inicio_mes, meses`,
      ),
      pool.query<LinhaDeAnoDaJanela>(
        `SELECT lado, inicio_mes::int AS inicio_mes, meses::int AS meses, ano::int AS ano,
                periodo, resultado
           FROM volume_scanner.analise_janela_anos
          ORDER BY lado, inicio_mes, meses, ano`,
      ),
    ]);
    return { cesta, janelas, anos };
  });

  return {
    cesta: cesta.map(
      (r): MesDaCesta => ({
        mes: r.mes,
        retorno: r.retorno,
        retornoBtc: r.retorno_btc,
        moedas: Number(r.moedas),
      }),
    ),
    janelas: janelas.map(paraJanela),
    anos: anos.map(
      (r): AnoDaJanela => ({
        lado: r.lado as LadoDoEstudo,
        inicioMes: Number(r.inicio_mes),
        meses: Number(r.meses),
        ano: Number(r.ano),
        periodo: r.periodo as PeriodoDoAno,
        resultado: r.resultado,
      }),
    ),
  };
}

/** US$ 1 milhão por dia, em média, nos últimos 12 meses (o volume_12m soma o ano: 365 milhões). */
export const LIQUIDEZ_DO_RANKING = 365_000_000;

type LinhaDeRanking = {
  moeda: string;
  beta_90: number | null;
  correlacao_90: number | null;
  dias_90: number | null;
  beta_ano: number | null;
  correlacao_ano: number | null;
  dias_ano: number | null;
  beta_total: number | null;
  correlacao_total: number | null;
  dias_total: number | null;
  desde: string | null;
};

const comoNumero = (v: number | string | null): number | null => (v === null ? null : Number(v));

/** A aba Rankings: as moedas vivas e líquidas, com beta e correlação em 3 períodos. */
export async function lerRanking() {
  const { candidatos, btc, dia90 } = await noMercado(MERCADO, async () => {
    const pool = conexaoDeAlertas();
    const [{ rows: candidatos }, { rows: btc }, { rows: dia90 }] = await Promise.all([
      pool.query<LinhaDeRanking>(
        `SELECT m.moeda,
                v.beta AS beta_90, v.correlacao AS correlacao_90, v.dias::int AS dias_90,
                a.beta AS beta_ano, a.correlacao AS correlacao_ano, a.dias::int AS dias_ano,
                t.beta AS beta_total, t.correlacao AS correlacao_total, t.dias::int AS dias_total,
                t.inicio::text AS desde
           FROM volume_scanner.analise_moedas m
           LEFT JOIN volume_scanner.analise_movel v ON v.moeda = m.moeda
                 AND v.dia = (SELECT max(dia) FROM volume_scanner.analise_movel WHERE moeda = 'BTC')
           LEFT JOIN volume_scanner.analise_anual a ON a.moeda = m.moeda
                 AND a.ano = (SELECT extract(year FROM ultimo_dia)::int
                                FROM volume_scanner.analise_moedas WHERE moeda = 'BTC')
           LEFT JOIN volume_scanner.analise_anual t ON t.moeda = m.moeda AND t.ano = 0
          WHERE m.fora_por IS NULL AND m.negociando AND m.volume_12m >= $1 AND m.moeda <> 'BTC'
          ORDER BY m.moeda`,
        [LIQUIDEZ_DO_RANKING],
      ),
      pool.query<{ ultimo_dia: string; ano: number }>(
        `SELECT ultimo_dia::text AS ultimo_dia, extract(year FROM ultimo_dia)::int AS ano
           FROM volume_scanner.analise_moedas
          WHERE moeda = 'BTC'`,
      ),
      pool.query<{ dia: string | null }>(
        `SELECT max(dia)::text AS dia FROM volume_scanner.analise_movel WHERE moeda = 'BTC'`,
      ),
    ]);
    return { candidatos, btc, dia90 };
  });

  const lista: CandidatoAoRanking[] = candidatos.map((r) => ({
    moeda: r.moeda,
    beta90: r.beta_90,
    correlacao90: r.correlacao_90,
    dias90: comoNumero(r.dias_90),
    betaAno: r.beta_ano,
    correlacaoAno: r.correlacao_ano,
    diasAno: comoNumero(r.dias_ano),
    betaTotal: r.beta_total,
    correlacaoTotal: r.correlacao_total,
    diasTotal: comoNumero(r.dias_total),
    desde: r.desde,
  }));
  return {
    ate: btc[0]?.ultimo_dia ?? null,
    ano: btc[0] ? Number(btc[0].ano) : null,
    dia90: dia90[0]?.dia ?? null,
    candidatos: lista,
  };
}
