// Testes da montagem do candle de hoje. Rodam com o executor do proprio Node,
// sem dependencia nova: `npm test`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  candleParcial,
  diaNaB3,
  horaNaB3,
  maisRecente,
  montarCandle,
} from "./candle-de-hoje.ts";

const HORA = new Date("2026-09-14T16:14:30Z"); // 13:14 em Brasilia

const campos = (extra = {}) => ({
  preco: 13.04,
  abertura: 13.16,
  maxima: 13.21,
  minima: 12.86,
  volume: 431100,
  hora: HORA,
  ...extra,
});

const barra = (tradeDate) => ({
  tradeDate,
  open: 10,
  high: 10,
  low: 10,
  close: 10,
  volumeFinancial: 1,
});

describe("montarCandle", () => {
  it("monta o candle com o dia e a hora da cotacao", () => {
    const c = montarCandle("ALPA4", "yahoo", campos());
    assert.deepEqual(c, {
      ticker: "ALPA4",
      dia: "2026-09-14",
      open: 13.16,
      high: 13.21,
      low: 12.86,
      close: 13.04,
      volumeAcoes: 431100,
      hora: "2026-09-14T16:14:30.000Z",
      fonte: "yahoo",
    });
  });

  it("sem preco ou sem hora nao ha candle", () => {
    assert.equal(montarCandle("ALPA4", "yahoo", campos({ preco: null })), null);
    assert.equal(montarCandle("ALPA4", "yahoo", campos({ preco: 0 })), null);
    assert.equal(montarCandle("ALPA4", "yahoo", campos({ hora: null })), null);
    assert.equal(montarCandle("ALPA4", "yahoo", campos({ hora: new Date("x") })), null);
  });

  it("maxima e minima contem abertura e fechamento", () => {
    // Fornecedor atrasado: preco novo acima da maxima que ele mesmo informou.
    const c = montarCandle("ALPA4", "brapi", campos({ preco: 13.5, minima: 13.2 }));
    assert.equal(c.high, 13.5);
    assert.equal(c.low, 13.16);
  });

  it("precos com duas casas, sem o ruido de float do Yahoo", () => {
    const c = montarCandle("ALPA4", "yahoo", campos({ abertura: 13.15999984741211 }));
    assert.equal(c.open, 13.16);
  });

  it("abertura ausente cai no preco, volume ausente vira null", () => {
    const c = montarCandle("ALPA4", "brapi", campos({ abertura: null, volume: null }));
    assert.equal(c.open, 13.04);
    assert.equal(c.volumeAcoes, null);
  });

  it("o dia e o de Sao Paulo, nao o de UTC", () => {
    // 22:30 de Brasilia ja e o dia seguinte em UTC.
    assert.equal(diaNaB3(new Date("2026-09-15T01:30:00Z")), "2026-09-14");
    assert.equal(horaNaB3("2026-09-14T16:14:30.000Z"), "13:14");
  });
});

describe("maisRecente", () => {
  const cedo = montarCandle("ALPA4", "brapi", campos({ hora: new Date("2026-09-14T15:45:00Z") }));
  const tarde = montarCandle("ALPA4", "yahoo", campos({ hora: new Date("2026-09-14T16:00:00Z") }));

  it("fica com a de hora mais nova, em qualquer ordem", () => {
    assert.equal(maisRecente(cedo, tarde), tarde);
    assert.equal(maisRecente(tarde, cedo), tarde);
  });

  it("empate fica com a primeira, e ausencia com a outra", () => {
    const outra = { ...cedo, fonte: "yahoo" };
    assert.equal(maisRecente(cedo, outra), cedo);
    assert.equal(maisRecente(null, tarde), tarde);
    assert.equal(maisRecente(cedo, null), cedo);
    assert.equal(maisRecente(null, null), null);
  });
});

describe("candleParcial", () => {
  const hoje = montarCandle("ALPA4", "yahoo", campos());

  it("aparece quando o COTAHIST ainda nao trouxe o pregao", () => {
    assert.equal(candleParcial([barra("2026-09-11")], hoje), hoje);
  });

  it("some quando o pregao ja esta no grafico oficial", () => {
    // Antes da abertura, fim de semana ou feriado: a ultima cotacao e de um
    // pregao que ja tem barra oficial.
    assert.equal(candleParcial([barra("2026-09-14")], hoje), null);
  });

  it("sem cotacao nao ha candle; sem barras, aparece", () => {
    assert.equal(candleParcial([barra("2026-09-11")], null), null);
    assert.equal(candleParcial([], hoje), hoje);
  });
});
