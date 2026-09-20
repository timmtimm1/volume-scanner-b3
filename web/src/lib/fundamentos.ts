/**
 * Os indicadores que dependem do preco, na data que a ficha esta mostrando.
 *
 * O que a empresa publicou -- receita, lucro, patrimonio, divida -- ja vem
 * calculado do banco. O que muda com a cotacao fica aqui, porque depende do
 * dia que o usuario esta olhando: abrindo a ficha por um evento de marco, o
 * P/L tem de ser o de marco, com o balanco que ja era conhecido naquele dia e
 * o fechamento daquele pregao.
 *
 * Duas regras que isso obriga:
 *
 * - **Vale o trimestre ja PUBLICADO ate a data**, e nao o que se refere a ela.
 *   O balanco do 2T26 so passou a existir para o mercado em 06/08/2026; antes
 *   disso, quem olhava o papel via o 1T26.
 * - **O valor de mercado soma cada classe pelo proprio preco.** Em 15/09/2026
 *   a UNIP3 fechou a R$ 55,40 e a UNIP6 a R$ 57,48; multiplicar todas as acoes
 *   por um preco so erraria a conta -- e o EV/EBITDA junto.
 *
 * Numero que nao da para calcular fica `null`, e a ficha mostra travessao.
 * Nada aqui inventa zero.
 */

import type { Barra, Fundamentos, Provento, Trimestre } from "./types";

/** Quantos trimestres o minigrafico mostra. */
export const TRIMESTRES_NO_GRAFICO = 8;

export type Indicadores = {
  /** O trimestre que valia na data, ja publicado. */
  trimestre: Trimestre;
  /** Fechamento usado nas contas de preco. */
  preco: number;
  /** Pregao a que esses numeros se referem. */
  data: string;
  ehBanco: boolean;
  precoLucro: number | null;
  precoValorPatrimonial: number | null;
  evEbitda: number | null;
  dividendYield: number | null;
  valorDeMercado: number | null;
  retornoSobrePatrimonio: number | null;
  margemLiquida: number | null;
  dividaLiquidaPatrimonio: number | null;
  liquidezCorrente: number | null;
  dividaLiquida: number | null;
  /** O mesmo trimestre do ano anterior, quando existe na serie. */
  anoAnterior: Trimestre | null;
  /** Os ultimos trimestres ate o da data, do mais antigo para o mais novo. */
  serie: Trimestre[];
};

/**
 * O ultimo trimestre que ja tinha sido publicado ate `data`.
 *
 * `publicadoEm` e a data da PRIMEIRA entrega do documento: uma reapresentacao
 * corrige os numeros, mas nao muda o dia em que o mercado soube.
 */
export function trimestreNaData(
  trimestres: Trimestre[],
  data: string,
): Trimestre | null {
  const publicados = trimestres.filter(
    (t) => t.publicadoEm !== null && t.publicadoEm <= data,
  );
  return publicados.length === 0 ? null : publicados[publicados.length - 1];
}

/** AAAA-MM-DD de um ano antes, em texto: `Date` mudaria o fuso no caminho. */
export function umAnoAntes(data: string): string {
  const [ano, mes, dia] = data.split("-");
  const anoAnterior = Number(ano) - 1;
  // 29 de fevereiro nao existe no ano anterior; a janela comeca em 28.
  if (mes === "02" && dia === "29") return `${anoAnterior}-02-28`;
  return `${anoAnterior}-${mes}-${dia}`;
}

/**
 * Quanto o papel pagou por acao nos 12 meses ate `data`.
 *
 * Conta pela DATA COM, e nao pela de pagamento: e ela que decide quem tinha o
 * papel e recebeu. Papel sem provento nenhum no banco devolve `null` -- "nao
 * sei" e diferente de "nao pagou nada".
 */
export function proventosDeDozeMeses(
  proventos: Provento[],
  data: string,
): number | null {
  if (proventos.length === 0) return null;
  const inicio = umAnoAntes(data);
  const janela = proventos.filter(
    (p) => p.dataCom > inicio && p.dataCom <= data,
  );
  return janela.reduce((soma, p) => soma + p.valor, 0);
}

/** Divide protegendo contra zero, nulo e denominador negativo sem sentido. */
function razao(
  a: number | null,
  b: number | null,
  { positivo = false } = {},
): number | null {
  if (a === null || b === null || !Number.isFinite(a) || !Number.isFinite(b))
    return null;
  if (b === 0 || (positivo && b <= 0)) return null;
  return a / b;
}

/**
 * O valor de mercado da empresa na data: cada classe pelo proprio fechamento.
 *
 * `null` quando falta o preco de alguma classe que existe -- somar so parte
 * das acoes daria um valor menor que o real, e o EV/EBITDA sairia barato
 * demais sem ninguem perceber.
 */
export function valorDeMercado(
  trimestre: Trimestre,
  precos: Fundamentos["precosPorClasse"],
  data: string,
): number | null {
  const partes: { acoes: number | null; preco: number | undefined }[] = [
    { acoes: trimestre.acoesOn, preco: precos.on[data] },
    { acoes: trimestre.acoesPn, preco: precos.pn[data] },
  ];

  let total = 0;
  for (const { acoes, preco } of partes) {
    if (acoes === null || acoes === 0) continue;
    if (preco === undefined) return null;
    total += acoes * preco;
  }
  return total === 0 ? null : total;
}

/**
 * Tudo que a aba mostra para um pregao.
 *
 * `null` quando nao ha trimestre publicado ate a data ou nao ha fechamento
 * naquele pregao -- e o caso de um papel recem-listado.
 */
export function indicadoresNaData(
  dados: Fundamentos,
  barras: Barra[],
  data: string,
): Indicadores | null {
  const trimestre = trimestreNaData(dados.trimestres, data);
  const barra = barras.find((b) => b.tradeDate === data);
  if (trimestre === null || barra === undefined) return null;

  const preco = barra.close;
  const acoes = trimestre.acoesEmCirculacao;
  const ehBanco = trimestre.layout === "financeiro";

  const lucroPorAcao = razao(trimestre.lucro12m, acoes, { positivo: true });
  const valorPatrimonialPorAcao = razao(trimestre.patrimonioLiquido, acoes, {
    positivo: true,
  });
  const mercado = valorDeMercado(trimestre, dados.precosPorClasse, data);
  const empresa =
    mercado === null ? null : mercado + (trimestre.dividaLiquida ?? 0);

  const posicao = dados.trimestres.indexOf(trimestre);
  const serie = dados.trimestres.slice(
    Math.max(0, posicao + 1 - TRIMESTRES_NO_GRAFICO),
    posicao + 1,
  );
  // O mesmo trimestre do ano anterior e quatro posicoes atras -- e so vale se a
  // serie for continua ate la, que e o que `rotulo` confirma.
  const candidato = dados.trimestres[posicao - 4];
  const anoAnterior =
    candidato !== undefined && mesmoTrimestre(candidato, trimestre)
      ? candidato
      : null;

  return {
    trimestre,
    preco,
    data,
    ehBanco,
    precoLucro: razao(preco, lucroPorAcao, { positivo: true }),
    precoValorPatrimonial: razao(preco, valorPatrimonialPorAcao, {
      positivo: true,
    }),
    evEbitda: ehBanco
      ? null
      : razao(empresa, trimestre.ebitda12m, { positivo: true }),
    dividendYield: razao(proventosDeDozeMeses(dados.proventos, data), preco),
    valorDeMercado: mercado,
    retornoSobrePatrimonio: razao(
      trimestre.lucro12m,
      trimestre.patrimonioLiquido,
      {
        positivo: true,
      },
    ),
    margemLiquida: ehBanco
      ? null
      : razao(trimestre.lucro12m, trimestre.receita12m, {
          positivo: true,
        }),
    dividaLiquidaPatrimonio: ehBanco
      ? null
      : razao(trimestre.dividaLiquida, trimestre.patrimonioLiquido, {
          positivo: true,
        }),
    liquidezCorrente: trimestre.liquidezCorrente,
    dividaLiquida: trimestre.dividaLiquida,
    anoAnterior,
    serie,
  };
}

/** "2T26" e "2T25" sao o mesmo trimestre de anos diferentes. */
function mesmoTrimestre(a: Trimestre, b: Trimestre): boolean {
  return a.rotulo.slice(0, 2) === b.rotulo.slice(0, 2);
}

/** Variacao contra o mesmo trimestre do ano anterior, como fracao. */
export function variacaoAnual(
  atual: number | null,
  anterior: number | null,
): number | null {
  if (
    atual === null ||
    anterior === null ||
    !Number.isFinite(atual) ||
    !Number.isFinite(anterior)
  ) {
    return null;
  }
  // Base negativa nao tem variacao percentual que signifique alguma coisa:
  // sair de -10 para 5 nao e "+150%".
  if (anterior <= 0) return null;
  return atual / anterior - 1;
}

/** Ha quantos dias o trimestre foi publicado, para a etiqueta da aba. */
export function diasDesdeAPublicacao(
  trimestre: Trimestre,
  data: string,
): number | null {
  if (trimestre.publicadoEm === null) return null;
  const de = Date.parse(`${trimestre.publicadoEm}T00:00:00Z`);
  const ate = Date.parse(`${data}T00:00:00Z`);
  if (!Number.isFinite(de) || !Number.isFinite(ate)) return null;
  return Math.round((ate - de) / (24 * 60 * 60 * 1000));
}
