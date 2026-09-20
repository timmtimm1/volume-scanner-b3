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
  /** Falso quando a contagem de acoes da CVM nao passou em alguma camada. */
  acoesConfiaveis: boolean;
  /** As seis conferencias e o que cada uma viu. */
  conferencias: Conferencia[];
  /** A CVM declarou as acoes em milhares e o numero foi corrigido. */
  escalaCorrigida: boolean;
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
  precoDoPapel: number | null = null,
): number | null {
  const candidatas = [
    { acoes: trimestre.acoesOn, preco: precos.on[data] },
    { acoes: trimestre.acoesPn, preco: precos.pn[data] },
  ].filter((p) => p.acoes !== null && p.acoes > 0);

  // Classe irrelevante nao bloqueia a conta. A Sabesp declara UMA acao
  // preferencial ao lado de 3,5 bilhoes de ordinarias: exigir o preco dela
  // deixaria a empresa inteira sem valor de mercado por R$ 50 de diferenca.
  // O corte e por materialidade -- abaixo de 0,1% do total, a classe nao muda
  // nenhum multiplo na segunda casa.
  const totalDeAcoes = candidatas.reduce((s, p) => s + (p.acoes as number), 0);
  const partes = candidatas.filter(
    (p) => (p.acoes as number) / totalDeAcoes >= FRACAO_MINIMA_DA_CLASSE,
  );

  // Empresa de classe unica sem preco classificado: vale o fechamento do papel
  // aberto. Se o balanco so tem ON, o papel que o usuario esta olhando SO pode
  // ser o ON -- nao ha outra coisa para negociar. A duvida de "qual classe e
  // esta" so existe quando ha duas, e ai a regra de cima continua valendo.
  //
  // Acontece porque 51 dos 447 tickers estao sem classe no banco: a B3 nao nos
  // deu o ISIN deles. Sem esta saida, EMBR3, JBSS3 e ELET3 ficariam sem valor
  // de mercado tendo preco e quantidade de acoes em maos.
  if (
    partes.length === 1 &&
    partes[0].preco === undefined &&
    precoDoPapel !== null
  ) {
    return (partes[0].acoes as number) * precoDoPapel;
  }

  let total = 0;
  for (const { acoes, preco } of partes) {
    if (preco === undefined) return null;
    total += (acoes as number) * preco;
  }
  return total === 0 ? null : total;
}

/**
 * As conferencias da contagem de acoes, em camadas independentes.
 *
 * O `composicao_capital` da CVM nao tem coluna de escala, e cerca de um terco
 * das empresas declara a quantidade em MILHARES. Pior: a mesma empresa troca de
 * escala entre trimestres. E ha lixo declarado -- 1 acao, 1.000 acoes, e uma
 * empresa com 54 trilhoes. Nada no arquivo separa o certo do errado.
 *
 * Por isso nenhuma conferencia sozinha manda. Sao seis, cada uma olhando para
 * um lado diferente do problema, e a contagem so vale passando em TODAS:
 *
 * | camada        | o que olha                  | pega o que as outras nao pegam |
 * |---------------|-----------------------------|--------------------------------|
 * | `existe`      | a propria contagem          | ausente ou negativa            |
 * | `piso`        | so a ordem de grandeza      | contagem pequena e iliquida    |
 * | `teto`        | so a ordem de grandeza      | contagem inflada, sem preco    |
 * | `serie`       | o historico da empresa      | a troca de escala no meio dela |
 * | `giro`        | o volume negociado          | impossibilidade, nao estimativa|
 * | `patrimonio`  | preco contra o balanco      | o iliquido que o giro nao ve   |
 *
 * Medido na base: 24 dos 153 papeis recusados caem por uma unica camada. Tirar
 * qualquer uma delas deixa dado errado passar.
 */
export type Conferencia = {
  nome: string;
  passou: boolean;
  /** So quando reprova: a frase que a ficha mostra. */
  porque: string | null;
};

/**
 * Menos que isto nao e companhia aberta na B3, e sim a escala errada. O menor
 * numero legitimo da base inteira e 153.464, entao o piso nao custa nenhum
 * papel bom e derruba 64 errados sozinho.
 */
const PISO_DE_ACOES = 100_000;

/** Acima disto e lixo declarado: a maior contagem real da base nao chega a 10^11. */
const TETO_DE_ACOES = 1e12;

/**
 * Quanto a contagem pode ser menor que o pico da propria empresa.
 *
 * Grupamento de verdade acontece: a Mobly fez 100:1 e a contagem caiu de
 * 3.788.605.704 para 37.886.057. O erro de escala e sempre mil vezes. 500 fica
 * no meio -- acima de qualquer grupamento plausivel, abaixo da assinatura do
 * erro.
 */
const QUEDA_MAXIMA_NA_SERIE = 500;

/** A empresa inteira nao vale menos de 2% nem mais de 100x o proprio patrimonio. */
const PISO_DO_VALOR_SOBRE_PATRIMONIO = 0.02;
const TETO_DO_VALOR_SOBRE_PATRIMONIO = 100;

/**
 * Quanto uma classe precisa representar para o preco dela ser exigido.
 *
 * Abaixo disto ela nao move nenhum multiplo na segunda casa, e exigir o preco
 * so faria a empresa inteira ficar sem valor de mercado.
 */
const FRACAO_MINIMA_DA_CLASSE = 0.001;

/** Quantos trimestres a serie precisa ter para servir de referencia. */
const MINIMO_PARA_COMPARAR_A_SERIE = 3;

/**
 * Passa a contagem de acoes pelas seis conferencias.
 *
 * Devolve todas, e nao so as que reprovaram, para a ficha poder dizer qual
 * falhou em vez de um "nao da para calcular" sem explicacao.
 */
export function conferirAcoes(
  trimestre: Trimestre,
  serie: Trimestre[],
  mercado: number | null,
  picoDeVolumeEmAcoes: number | null,
): Conferencia[] {
  const acoes = trimestre.acoesEmCirculacao;
  const ok = (nome: string): Conferencia => ({ nome, passou: true, porque: null });
  const nao = (nome: string, porque: string): Conferencia => ({
    nome,
    passou: false,
    porque,
  });

  if (acoes === null || acoes <= 0) {
    return [nao("existe", "a CVM não informou a quantidade de ações")];
  }

  const camadas: Conferencia[] = [ok("existe")];

  camadas.push(
    acoes < PISO_DE_ACOES
      ? nao("piso", "a quantidade de ações é pequena demais para ser real")
      : ok("piso"),
  );

  camadas.push(
    acoes > TETO_DE_ACOES
      ? nao("teto", "a quantidade de ações é grande demais para ser real")
      : ok("teto"),
  );

  // A serie da propria empresa: uma queda dessas nao e grupamento, e escala.
  //
  // A referencia so aceita trimestres que passariam no piso e no teto. Sem esse
  // filtro a propria serie envenena a conferencia: a Gol declarou 9,17 trilhoes
  // de acoes em tres trimestres de 2025, e comparar contra esse pico reprovaria
  // os trimestres em que ela declarou os 3,2 bilhoes corretos.
  const contagens = serie
    .map((t) => t.acoesEmCirculacao)
    .filter(
      (v): v is number =>
        v !== null && v >= PISO_DE_ACOES && v <= TETO_DE_ACOES,
    );
  if (contagens.length >= MINIMO_PARA_COMPARAR_A_SERIE) {
    const pico = Math.max(...contagens);
    camadas.push(
      pico / acoes >= QUEDA_MAXIMA_NA_SERIE
        ? nao("serie", "a quantidade destoa do histórico da própria empresa")
        : ok("serie"),
    );
  }

  // A prova: ninguem negocia num pregao mais acoes do que tem em circulacao.
  if (picoDeVolumeEmAcoes !== null) {
    camadas.push(
      picoDeVolumeEmAcoes > acoes
        ? nao("giro", "o papel já negociou num pregão mais ações do que existiriam")
        : ok("giro"),
    );
  }

  // Patrimonio negativo nao serve de regua; as camadas acima e que decidem.
  const patrimonio = trimestre.patrimonioLiquido;
  if (mercado !== null && patrimonio !== null && patrimonio > 0) {
    const sobrePatrimonio = mercado / patrimonio;
    camadas.push(
      sobrePatrimonio < PISO_DO_VALOR_SOBRE_PATRIMONIO ||
        sobrePatrimonio > TETO_DO_VALOR_SOBRE_PATRIMONIO
        ? nao("patrimonio", "o valor de mercado não é compatível com o patrimônio")
        : ok("patrimonio"),
    );
  }

  return camadas;
}

/** A contagem so vale passando em todas as conferencias. */
export function acoesConfiaveis(camadas: Conferencia[]): boolean {
  return camadas.every((c) => c.passou);
}

/**
 * O erro de escala da CVM e sempre este: a empresa declarou em milhares.
 *
 * Nao e um fator ajustavel. Quem declara errado declara em milhares, e por isso
 * a correcao e uma hipotese unica -- ou ela explica o numero, ou nao explica.
 */
const FATOR_DA_ESCALA = 1000;

/**
 * O mesmo trimestre com a contagem de acoes multiplicada.
 *
 * So a quantidade muda. O balanco em reais esta certo: a CVM erra a escala das
 * ACOES, no `composicao_capital`, e nao a dos valores, que tem `ESCALA_MOEDA`.
 */
function comEscala(t: Trimestre, fator: number): Trimestre {
  const vezes = (v: number | null) => (v === null ? null : v * fator);
  return {
    ...t,
    acoesEmCirculacao: vezes(t.acoesEmCirculacao),
    acoesOn: vezes(t.acoesOn),
    acoesPn: vezes(t.acoesPn),
  };
}

export type Contagem = {
  /** O trimestre a usar, ja com a escala corrigida quando foi o caso. */
  trimestre: Trimestre;
  mercado: number | null;
  conferencias: Conferencia[];
  confiaveis: boolean;
  escalaCorrigida: boolean;
};

/**
 * Resolve a contagem de acoes: a da CVM, ou a corrigida, ou nenhuma.
 *
 * Reprovada a contagem publicada, a unica hipotese testada e "veio em
 * milhares". E ela nao e aceita por ser plausivel: e submetida as MESMAS seis
 * camadas, e so vale passando em todas. Nao passando, o numero continua
 * recusado -- corrigir as cegas seria trocar um erro conhecido por um chute.
 *
 * A serie inteira e multiplicada junto com o trimestre, senao a camada `serie`
 * compararia o corrigido contra um historico cru e reprovaria por construcao.
 * Multiplicar tudo preserva as razoes, entao aquela camada decide o mesmo antes
 * e depois -- quem muda de opiniao sao piso, teto, giro e patrimonio, que e
 * exatamente o que se quer testar.
 */
export function resolverContagem(
  trimestre: Trimestre,
  serie: Trimestre[],
  mercadoDe: (t: Trimestre) => number | null,
  picoDeVolumeEmAcoes: number | null,
): Contagem {
  const tentar = (fator: number): Contagem => {
    const alvo = fator === 1 ? trimestre : comEscala(trimestre, fator);
    const historico =
      fator === 1 ? serie : serie.map((x) => comEscala(x, fator));
    const mercado = mercadoDe(alvo);
    const conferencias = conferirAcoes(
      alvo,
      historico,
      mercado,
      picoDeVolumeEmAcoes,
    );
    return {
      trimestre: alvo,
      mercado,
      conferencias,
      confiaveis: acoesConfiaveis(conferencias),
      escalaCorrigida: fator !== 1,
    };
  };

  const publicada = tentar(1);
  if (publicada.confiaveis) return publicada;

  const corrigida = tentar(FATOR_DA_ESCALA);
  return corrigida.confiaveis ? corrigida : publicada;
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
  const ehBanco = trimestre.layout === "financeiro";

  // Tudo que divide por acao passa por aqui primeiro. Reprovada a contagem, os
  // quatro multiplos que dependem dela ficam em `null` -- e so eles: receita,
  // lucro, patrimonio, ROE, margem, liquidez e dividend yield nao dividem por
  // acao nenhuma e seguem valendo.
  const contagem = resolverContagem(
    trimestre,
    dados.trimestres,
    (t) => valorDeMercado(t, dados.precosPorClasse, data, preco),
    dados.picoDeVolumeEmAcoes,
  );
  const { conferencias, confiaveis, escalaCorrigida } = contagem;
  // Daqui para baixo vale o trimestre que a contagem resolveu: e o mesmo
  // balanco, com a quantidade de acoes corrigida se ela veio em milhares.
  const doTrimestre = contagem.trimestre;
  const acoes = confiaveis ? doTrimestre.acoesEmCirculacao : null;
  const mercado = confiaveis ? contagem.mercado : null;

  const lucroPorAcao = razao(doTrimestre.lucro12m, acoes, { positivo: true });
  const valorPatrimonialPorAcao = razao(doTrimestre.patrimonioLiquido, acoes, {
    positivo: true,
  });
  const empresa =
    mercado === null ? null : mercado + (doTrimestre.dividaLiquida ?? 0);

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
    trimestre: doTrimestre,
    preco,
    data,
    ehBanco,
    acoesConfiaveis: confiaveis,
    conferencias,
    escalaCorrigida,
    precoLucro: razao(preco, lucroPorAcao, { positivo: true }),
    precoValorPatrimonial: razao(preco, valorPatrimonialPorAcao, {
      positivo: true,
    }),
    evEbitda: ehBanco
      ? null
      : razao(empresa, doTrimestre.ebitda12m, { positivo: true }),
    dividendYield: razao(proventosDeDozeMeses(dados.proventos, data), preco),
    valorDeMercado: mercado,
    retornoSobrePatrimonio: razao(
      doTrimestre.lucro12m,
      doTrimestre.patrimonioLiquido,
      {
        positivo: true,
      },
    ),
    margemLiquida: ehBanco
      ? null
      : razao(doTrimestre.lucro12m, doTrimestre.receita12m, {
          positivo: true,
        }),
    dividaLiquidaPatrimonio: ehBanco
      ? null
      : razao(doTrimestre.dividaLiquida, doTrimestre.patrimonioLiquido, {
          positivo: true,
        }),
    liquidezCorrente: doTrimestre.liquidezCorrente,
    dividaLiquida: doTrimestre.dividaLiquida,
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
