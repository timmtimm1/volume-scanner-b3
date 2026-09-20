// Indicadores na data do evento. Numeros reais da Unipar. `npm test`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  indicadoresNaData,
  proventosDeDozeMeses,
  trimestreNaData,
  umAnoAntes,
  valorDeMercado,
  variacaoAnual,
} from "./fundamentos.ts";

const perto = (a, b, tolerancia = 1e-6) =>
  assert.ok(Math.abs(a - b) < tolerancia, `${a} != ${b}`);

/** O 2T26 da Unipar, como a fase 3 grava (em reais). */
const DOIS_T26 = {
  dtFim: "2026-06-30",
  rotulo: "2T26",
  origem: "ITR",
  publicadoEm: "2026-08-06",
  layout: "geral",
  receitaTri: 1_495_676_000,
  ebitdaTri: 386_161_000,
  lucroTri: 125_074_000,
  receita12m: 5_233_765_000,
  ebitda12m: 925_154_000,
  lucro12m: 266_559_000,
  patrimonioLiquido: 1_998_822_000,
  ativoTotal: 7_759_771_000,
  dividaLiquida: 2_331_252_000,
  liquidezCorrente: 2.386,
  acoesEmCirculacao: 111_622_153,
  acoesOn: 38_985_383,
  acoesPn: 72_636_770,
};

const UM_T26 = {
  ...DOIS_T26,
  dtFim: "2026-03-31",
  rotulo: "1T26",
  publicadoEm: "2026-05-14",
  receitaTri: 1_238_235_000,
  lucroTri: 37_472_000,
  lucro12m: 374_713_000,
  patrimonioLiquido: 1_872_668_000,
};

const DOIS_T25 = {
  ...DOIS_T26,
  dtFim: "2025-06-30",
  rotulo: "2T25",
  publicadoEm: "2025-08-07",
  receitaTri: 1_273_920_000,
  lucroTri: 233_228_000,
};

const TRES_T25 = { ...DOIS_T25, dtFim: "2025-09-30", rotulo: "3T25", publicadoEm: "2025-11-13" };
const QUATRO_T25 = { ...DOIS_T25, dtFim: "2025-12-31", rotulo: "4T25", publicadoEm: "2026-03-19" };

const SERIE = [DOIS_T25, TRES_T25, QUATRO_T25, UM_T26, DOIS_T26];

const dados = (extra = {}) => ({
  empresa: "UNIPAR CARBOCLORO S.A.",
  setor: "Petroquímicos e Borracha",
  classe: "PNB",
  trimestres: SERIE,
  proventos: [
    { dataCom: "2025-08-12", tipo: "DIVIDENDO", valor: 3.55862869406 },
    { dataCom: "2025-12-05", tipo: "DIVIDENDO", valor: 6.03042284335 },
    { dataCom: "2025-12-05", tipo: "DIVIDENDO", valor: 0.44637931213 },
  ],
  precosPorClasse: {
    on: { "2026-09-15": 55.4, "2026-05-20": 50.0 },
    pn: { "2026-09-15": 57.48, "2026-05-20": 52.0 },
  },
  ...extra,
});

const barras = [
  { tradeDate: "2026-05-20", open: 52, high: 52, low: 52, close: 52.0, volumeFinancial: 1 },
  { tradeDate: "2026-09-15", open: 57, high: 58, low: 57, close: 57.48, volumeFinancial: 1 },
];

describe("trimestreNaData", () => {
  it("vale o que ja foi publicado, e nao o que se refere a data", () => {
    // Em 20/05/2026 o 2T26 (publicado em agosto) ainda nao existia.
    assert.equal(trimestreNaData(SERIE, "2026-05-20").rotulo, "1T26");
    assert.equal(trimestreNaData(SERIE, "2026-09-15").rotulo, "2T26");
  });

  it("no proprio dia da publicacao o trimestre ja vale", () => {
    assert.equal(trimestreNaData(SERIE, "2026-08-06").rotulo, "2T26");
    assert.equal(trimestreNaData(SERIE, "2026-08-05").rotulo, "1T26");
  });

  it("antes de qualquer publicacao nao ha trimestre", () => {
    assert.equal(trimestreNaData(SERIE, "2024-01-02"), null);
  });
});

describe("umAnoAntes", () => {
  it("volta um ano no calendario", () => {
    assert.equal(umAnoAntes("2026-09-15"), "2025-09-15");
  });

  it("29 de fevereiro cai em 28, que existe todo ano", () => {
    assert.equal(umAnoAntes("2024-02-29"), "2023-02-28");
  });
});

describe("proventosDeDozeMeses", () => {
  it("soma pela data com, nao pela de pagamento", () => {
    perto(proventosDeDozeMeses(dados().proventos, "2026-09-15"), 6.47680215548);
  });

  it("provento mais velho que a janela fica de fora", () => {
    // Em 01/09/2026 o de 12/08/2025 ja saiu dos 12 meses.
    perto(proventosDeDozeMeses(dados().proventos, "2026-08-13"), 6.47680215548);
    perto(proventosDeDozeMeses(dados().proventos, "2026-08-11"), 10.03543084954);
  });

  it("papel sem provento nenhum e desconhecido, e nao zero", () => {
    assert.equal(proventosDeDozeMeses([], "2026-09-15"), null);
  });

  it("papel com proventos, mas nenhum na janela, pagou zero mesmo", () => {
    perto(proventosDeDozeMeses(dados().proventos, "2027-06-01"), 0);
  });
});

describe("valorDeMercado", () => {
  it("soma cada classe pelo proprio preco", () => {
    const esperado = 38_985_383 * 55.4 + 72_636_770 * 57.48;
    perto(valorDeMercado(DOIS_T26, dados().precosPorClasse, "2026-09-15"), esperado, 1);
  });

  it("sem o preco de uma das classes, prefere nao responder", () => {
    const precos = { on: {}, pn: { "2026-09-15": 57.48 } };
    assert.equal(valorDeMercado(DOIS_T26, precos, "2026-09-15"), null);
  });

  it("empresa de classe unica nao precisa da outra", () => {
    const soOn = { ...DOIS_T26, acoesPn: null };
    const precos = { on: { "2026-09-15": 55.4 }, pn: {} };
    perto(valorDeMercado(soOn, precos, "2026-09-15"), 38_985_383 * 55.4, 1);
  });
});

describe("indicadoresNaData", () => {
  it("usa o balanco conhecido na data e o fechamento daquele pregao", () => {
    const i = indicadoresNaData(dados(), barras, "2026-09-15");

    assert.equal(i.trimestre.rotulo, "2T26");
    assert.equal(i.preco, 57.48);
    // P/L: 57,48 / (266.559.000 / 111.622.153) = 24,07
    perto(i.precoLucro, 57.48 / (266_559_000 / 111_622_153), 1e-4);
    // P/VP: 57,48 / (1.998.822.000 / 111.622.153) = 3,21
    perto(i.precoValorPatrimonial, 57.48 / (1_998_822_000 / 111_622_153), 1e-4);
    perto(i.retornoSobrePatrimonio, 266_559_000 / 1_998_822_000, 1e-6);
    perto(i.margemLiquida, 266_559_000 / 5_233_765_000, 1e-6);
    perto(i.dividaLiquidaPatrimonio, 2_331_252_000 / 1_998_822_000, 1e-6);
    perto(i.dividendYield, 6.47680215548 / 57.48, 1e-6);
  });

  it("o EV/EBITDA soma a divida liquida ao valor de mercado", () => {
    const i = indicadoresNaData(dados(), barras, "2026-09-15");
    const mercado = 38_985_383 * 55.4 + 72_636_770 * 57.48;

    perto(i.evEbitda, (mercado + 2_331_252_000) / 925_154_000, 1e-4);
  });

  it("no evento de maio vale o 1T26, com o preco de maio", () => {
    const i = indicadoresNaData(dados(), barras, "2026-05-20");

    assert.equal(i.trimestre.rotulo, "1T26");
    assert.equal(i.preco, 52.0);
    perto(i.precoLucro, 52.0 / (374_713_000 / 111_622_153), 1e-4);
  });

  it("sem pregao naquele dia nao ha o que calcular", () => {
    assert.equal(indicadoresNaData(dados(), barras, "2026-07-01"), null);
  });

  it("banco fica sem EBITDA, divida e margem", () => {
    const banco = { ...DOIS_T26, layout: "financeiro" };
    const i = indicadoresNaData(
      dados({ trimestres: [banco], proventos: [] }),
      barras,
      "2026-09-15",
    );

    assert.equal(i.ehBanco, true);
    assert.equal(i.evEbitda, null);
    assert.equal(i.margemLiquida, null);
    assert.equal(i.dividaLiquidaPatrimonio, null);
    // O que existe num banco continua valendo.
    assert.ok(i.precoLucro > 0);
  });

  it("acha o mesmo trimestre do ano anterior para a comparacao", () => {
    const i = indicadoresNaData(dados(), barras, "2026-09-15");
    assert.equal(i.anoAnterior.rotulo, "2T25");
  });

  it("serie termina no trimestre da data, e nao no mais recente que existe", () => {
    const i = indicadoresNaData(dados(), barras, "2026-05-20");
    assert.deepEqual(
      i.serie.map((t) => t.rotulo),
      ["2T25", "3T25", "4T25", "1T26"],
    );
  });
});

describe("variacaoAnual", () => {
  it("compara com o mesmo trimestre do ano anterior", () => {
    perto(variacaoAnual(1_495_676_000, 1_273_920_000), 1_495_676_000 / 1_273_920_000 - 1);
  });

  it("base negativa nao tem variacao que signifique alguma coisa", () => {
    assert.equal(variacaoAnual(5, -10), null);
  });

  it("sem o ano anterior nao ha comparacao", () => {
    assert.equal(variacaoAnual(10, null), null);
  });
});
