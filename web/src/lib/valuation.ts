/**
 * Valuation simples: tres contas classicas de "preco justo" sobre o balanco.
 *
 * Pedido do usuario em 16/11/2026: metodos basicos, nada complexo, que deem
 * para automatizar para todas as empresas. Escolhas dele: Graham, Bazin e um
 * fluxo de caixa descontado simples; resultado na ficha e numa lista geral;
 * semaforo por metodo; no DCF, premissa padrao automatica com ajuste na tela.
 *
 * O que isto E: aritmetica sobre o ultimo balanco publicado, com a formula a
 * vista. O que NAO e: recomendacao, previsao ou analise da empresa. Os tres
 * metodos discordam entre si com frequencia -- e isso e informacao, nao erro.
 *
 * So conta, sem banco e sem import de valor: os testes rodam este arquivo
 * direto no Node.
 */

import type { Provento, Trimestre } from "./types";

export type Metodo = "graham" | "bazin" | "dcf";

/** Onde o preco de hoje esta em relacao ao preco justo do metodo. */
export type Sinal = "abaixo" | "perto" | "acima";

export type Avaliacao = {
  metodo: Metodo;
  /** Null quando o metodo nao se aplica a empresa (ver `motivo`). */
  precoJusto: number | null;
  /** `preco / precoJusto - 1`: -0,18 = o preco esta 18% abaixo do justo. */
  diferenca: number | null;
  sinal: Sinal | null;
  /** Por que nao deu para calcular, em uma frase; null quando calculou. */
  motivo: string | null;
};

export const NOME_DO_METODO: Record<Metodo, string> = {
  graham: "Graham",
  bazin: "Bazin",
  dcf: "Fluxo de caixa",
};

/**
 * A faixa do "perto": preco a menos de 10% do justo, para cima ou para baixo.
 * Uma conta destas nao tem precisao para chamar 3% de desconto de barato.
 */
export const FAIXA_DO_PERTO = 0.1;

const positivo = (v: number | null | undefined): v is number =>
  typeof v === "number" && Number.isFinite(v) && v > 0;

export function sinalDoPreco(preco: number, precoJusto: number): Sinal {
  const diferenca = preco / precoJusto - 1;
  if (diferenca < -FAIXA_DO_PERTO) return "abaixo";
  if (diferenca > FAIXA_DO_PERTO) return "acima";
  return "perto";
}

function avaliacao(metodo: Metodo, preco: number, precoJusto: number): Avaliacao {
  return {
    metodo,
    precoJusto,
    diferenca: preco / precoJusto - 1,
    sinal: sinalDoPreco(preco, precoJusto),
    motivo: null,
  };
}

function semConta(metodo: Metodo, motivo: string): Avaliacao {
  return { metodo, precoJusto: null, diferenca: null, sinal: null, motivo };
}

/* ------------------------------------------------------------------ */
/* Graham                                                             */
/* ------------------------------------------------------------------ */

/** O teto de Graham: P/L de ate 15 vezes e P/VP de ate 1,5 -- 15 x 1,5. */
export const CONSTANTE_DE_GRAHAM = 22.5;

/**
 * Valor intrinseco de Benjamin Graham: raiz de 22,5 x lucro por acao x valor
 * patrimonial por acao. So existe para empresa com lucro e patrimonio
 * positivos: a raiz de um numero negativo nao e preco de nada.
 */
export function graham(lucroPorAcao: number | null, valorPatrimonialPorAcao: number | null): number | null {
  if (!positivo(lucroPorAcao) || !positivo(valorPatrimonialPorAcao)) return null;
  return Math.sqrt(CONSTANTE_DE_GRAHAM * lucroPorAcao * valorPatrimonialPorAcao);
}

/* ------------------------------------------------------------------ */
/* Bazin                                                              */
/* ------------------------------------------------------------------ */

/** O rendimento minimo que Decio Bazin exigia de uma acao: 6% ao ano. */
export const RENDIMENTO_DE_BAZIN = 0.06;
/** Quantos anos de proventos entram na media. */
export const ANOS_DE_PROVENTOS = 3;

function anosAntes(data: string, anos: number): string {
  const [a, m, d] = data.split("-");
  return `${Number(a) - anos}-${m}-${d}`;
}

/**
 * Media anual dos proventos por acao nos ultimos `anos` anos ate `data`.
 *
 * Janelas de 12 meses contadas pela data com, como o dividend yield da ficha.
 * Ano sem provento entra como zero: quem pagou em um ano de tres nao tem a
 * media de quem pagou nos tres. `null` so quando o papel nao tem provento
 * nenhum no banco -- "nao sei" e diferente de "nao pagou".
 */
export function proventoMedioAnual(
  proventos: readonly Provento[],
  data: string,
  anos = ANOS_DE_PROVENTOS,
  /**
   * Fator que poe o provento na escala das acoes de `data` (desdobramento
   * entre a data com e o dia): `fatorAteODia`, de `fundamentos.ts`. Vem por
   * parametro porque este arquivo nao importa valor de outro modulo.
   */
  ajuste: (dataCom: string) => number = () => 1,
): number | null {
  if (proventos.length === 0) return null;
  const inicio = anosAntes(data, anos);
  const soma = proventos
    .filter((p) => p.dataCom > inicio && p.dataCom <= data)
    .reduce((total, p) => total + p.valor * ajuste(p.dataCom), 0);
  return soma / anos;
}

/**
 * Provento medio anual acima desta fracao do preco de hoje nao e usado.
 *
 * 30% ao ano, na media de tres anos, nao e dividendo recorrente: ou e um
 * pagamento extraordinario (venda de ativo, reducao de capital), ou o papel
 * desdobrou antes da janela de barras do banco e o provento antigo ficou na
 * escala velha. Nos dois casos, dividir por 6% daria um "preco teto" varias
 * vezes acima do preco, sem sentido como regua.
 */
export const RENDIMENTO_FORA_DE_ESCALA = 0.3;

/** Preco teto de Bazin: o preco em que o provento medio rende 6% ao ano. */
export function bazin(proventoMedio: number | null): number | null {
  if (!positivo(proventoMedio)) return null;
  return proventoMedio / RENDIMENTO_DE_BAZIN;
}

/* ------------------------------------------------------------------ */
/* Fluxo de caixa descontado simples                                  */
/* ------------------------------------------------------------------ */

export type Premissas = {
  /** Quanto o lucro cresce por ano nos primeiros anos, como fracao. */
  crescimento: number;
  /** A taxa que traz o lucro futuro a valor de hoje, como fracao. */
  desconto: number;
  /** Crescimento depois dos anos projetados, para sempre. */
  perpetuidade: number;
  /** Anos projetados com `crescimento` antes da perpetuidade. */
  anos: number;
};

export const ANOS_PROJETADOS = 5;
/** Crescimento nominal de longo prazo: a meta de inflacao (3%) mais 1 ponto de crescimento real. */
export const CRESCIMENTO_PERPETUO = 0.04;
/** Quanto a mais que o titulo publico longo se exige de uma acao. */
export const PREMIO_DE_RISCO = 0.05;
/** Sem o juro do banco (tabela vazia), vale este: perto da media de 10 anos do prefixado longo. */
export const JURO_DE_RESERVA = 0.12;
export const CRESCIMENTO_MINIMO = 0;
export const CRESCIMENTO_MAXIMO = 0.15;
/** Sem historico para medir o crescimento, vale o da perpetuidade. */
export const CRESCIMENTO_SEM_HISTORICO = CRESCIMENTO_PERPETUO;
/** O desconto tem de ficar acima da perpetuidade com folga, senao o valor explode. */
export const FOLGA_DO_DESCONTO = 0.03;

/**
 * Crescimento anual do lucro de 12 meses, medido na propria serie da empresa.
 *
 * Compara o lucro de 12 meses de hoje com o de `anos` anos atras (4 trimestres
 * por ano) e tira a taxa composta. `null` quando a serie e curta ou um dos
 * dois lucros nao e positivo: taxa composta saindo de prejuizo nao existe.
 */
export function crescimentoDoLucro(serie: readonly Trimestre[], anos = 2): number | null {
  const atual = serie[serie.length - 1];
  const antigo = serie[serie.length - 1 - anos * 4];
  if (!atual || !antigo) return null;
  if (!positivo(atual.lucro12m) || !positivo(antigo.lucro12m)) return null;
  return (atual.lucro12m / antigo.lucro12m) ** (1 / anos) - 1;
}

/**
 * As premissas com que o DCF sai calculado antes de o usuario mexer.
 *
 * Crescimento: o da propria empresa, entre 0% e 15% (lucro que dobrou em dois
 * anos nao vai dobrar para sempre, e lucro que caiu nao e projetado caindo).
 * Desconto: o juro do prefixado de 10 anos (ou a Selic, na falta dele) mais 5
 * pontos de premio por ser acao.
 */
export function premissasPadrao(
  crescimentoHistorico: number | null,
  juroAnual: number | null,
): Premissas {
  const crescimento =
    crescimentoHistorico === null || !Number.isFinite(crescimentoHistorico)
      ? CRESCIMENTO_SEM_HISTORICO
      : Math.min(CRESCIMENTO_MAXIMO, Math.max(CRESCIMENTO_MINIMO, crescimentoHistorico));
  const juro = positivo(juroAnual) ? juroAnual : JURO_DE_RESERVA;
  return {
    crescimento,
    desconto: juro + PREMIO_DE_RISCO,
    perpetuidade: CRESCIMENTO_PERPETUO,
    anos: ANOS_PROJETADOS,
  };
}

/**
 * Valor por acao pelo fluxo descontado, usando o lucro por acao como o caixa
 * que pertence ao acionista.
 *
 * Soma dos lucros dos proximos `anos` anos, cada um trazido a valor de hoje,
 * mais o valor de tudo que vem depois (perpetuidade), tambem trazido a hoje.
 * E a versao mais simples que existe: nao separa investimento, capital de giro
 * nem divida. Serve para comparar empresas com a mesma regua, nao para dizer
 * quanto uma vale.
 *
 * `null` com prejuizo (nao ha o que projetar) ou quando o desconto nao fica
 * acima da perpetuidade com folga.
 */
export function dcf(lucroPorAcao: number | null, p: Premissas): number | null {
  if (!positivo(lucroPorAcao)) return null;
  if (!(p.desconto >= p.perpetuidade + FOLGA_DO_DESCONTO) || p.anos < 1) return null;
  let total = 0;
  let lucro = lucroPorAcao;
  for (let ano = 1; ano <= p.anos; ano++) {
    lucro *= 1 + p.crescimento;
    total += lucro / (1 + p.desconto) ** ano;
  }
  const depois = (lucro * (1 + p.perpetuidade)) / (p.desconto - p.perpetuidade);
  return total + depois / (1 + p.desconto) ** p.anos;
}

/* ------------------------------------------------------------------ */
/* Os tres juntos                                                     */
/* ------------------------------------------------------------------ */

export type DadosDoPapel = {
  preco: number;
  lucroPorAcao: number | null;
  valorPatrimonialPorAcao: number | null;
  /** Null quando o papel nao tem provento no banco. */
  proventoMedio: number | null;
  /** Falso quando a contagem de acoes da CVM nao e confiavel: nada por acao vale. */
  acoesConfiaveis: boolean;
};

const SEM_ACOES = "a contagem de ações da CVM não é confiável para esta empresa";

export function avaliar(d: DadosDoPapel, premissas: Premissas): Avaliacao[] {
  const { preco } = d;
  const porAcao = d.acoesConfiaveis;

  const vGraham = porAcao ? graham(d.lucroPorAcao, d.valorPatrimonialPorAcao) : null;
  const foraDeEscala =
    positivo(d.proventoMedio) && d.proventoMedio / preco > RENDIMENTO_FORA_DE_ESCALA;
  const vBazin = foraDeEscala ? null : bazin(d.proventoMedio);
  const vDcf = porAcao ? dcf(d.lucroPorAcao, premissas) : null;

  const semLucro = !positivo(d.lucroPorAcao);
  return [
    vGraham !== null
      ? avaliacao("graham", preco, vGraham)
      : semConta(
          "graham",
          !porAcao
            ? SEM_ACOES
            : semLucro
              ? "a empresa teve prejuízo nos últimos 12 meses"
              : "o patrimônio líquido está negativo",
        ),
    vBazin !== null
      ? avaliacao("bazin", preco, vBazin)
      : semConta(
          "bazin",
          d.proventoMedio === null
            ? "não há proventos deste papel no banco"
            : foraDeEscala
              ? "os proventos dos últimos 3 anos estão fora de escala para o preço de hoje (pagamento extraordinário ou desdobramento antigo)"
              : "o papel não pagou proventos nos últimos 3 anos",
        ),
    vDcf !== null
      ? avaliacao("dcf", preco, vDcf)
      : semConta(
          "dcf",
          !porAcao
            ? SEM_ACOES
            : semLucro
              ? "a empresa teve prejuízo nos últimos 12 meses"
              : "a taxa de desconto precisa ficar pelo menos 3 pontos acima do crescimento perpétuo",
        ),
  ];
}

export type Resumo = {
  /** Metodos que deram numero. */
  calculados: number;
  abaixo: number;
  acima: number;
  /** "2 de 3 métodos: abaixo do preço justo" */
  texto: string;
};

/** A linha de baixo do bloco: quantos metodos concordam, sem tirar media entre eles. */
export function resumir(avaliacoes: readonly Avaliacao[]): Resumo {
  const comConta = avaliacoes.filter((a) => a.sinal !== null);
  const abaixo = comConta.filter((a) => a.sinal === "abaixo").length;
  const acima = comConta.filter((a) => a.sinal === "acima").length;
  const n = comConta.length;
  let texto: string;
  if (n === 0) texto = "Nenhum método se aplica a esta empresa";
  else if (abaixo > 0 && abaixo >= acima)
    texto = `${abaixo} de ${n} ${n === 1 ? "método" : "métodos"}: abaixo do preço justo`;
  else if (acima > 0)
    texto = `${acima} de ${n} ${n === 1 ? "método" : "métodos"}: acima do preço justo`;
  else texto = `${n === 1 ? "O método calculado ficou" : `Os ${n} métodos ficaram`} perto do preço justo`;
  return { calculados: n, abaixo, acima, texto };
}

/** "18% abaixo", "15% acima", "no preço": a diferenca em palavras. */
export function textoDaDiferenca(diferenca: number | null): string {
  if (diferenca === null || !Number.isFinite(diferenca)) return "—";
  const pct = Math.round(Math.abs(diferenca) * 100);
  if (pct === 0) return "no preço";
  return `${pct}% ${diferenca < 0 ? "abaixo" : "acima"}`;
}
