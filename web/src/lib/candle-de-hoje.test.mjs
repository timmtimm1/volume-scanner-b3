// Testes da montagem do candle de hoje. Rodam com o executor do proprio Node,
// sem dependencia nova: `npm test`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { candleParcial, diaNaB3, horaNaB3, montarCandle } from "./candle-de-hoje.ts";

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

const barra = (tradeDate, ohlc = {}) => ({
  tradeDate,
  open: 10,
  high: 10,
  low: 10,
  close: 10,
  volumeFinancial: 1,
  ...ohlc,
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

describe("candleParcial", () => {
  // 14/09/2026 e uma segunda-feira; 13:14 em Brasilia.
  const hoje = montarCandle("ALPA4", "yahoo", campos());

  it("aparece quando o COTAHIST ainda nao trouxe o pregao", () => {
    assert.equal(candleParcial([barra("2026-09-11")], hoje), hoje);
  });

  it("some quando o pregao ja esta no grafico oficial", () => {
    assert.equal(candleParcial([barra("2026-09-14")], hoje), null);
  });

  it("sem cotacao nao ha candle; sem barras, aparece", () => {
    assert.equal(candleParcial([barra("2026-09-11")], null), null);
    assert.equal(candleParcial([], hoje), hoje);
  });

  describe("copia da ultima barra fechada", () => {
    // O caso real de 23/09/2026: a brapi devolveu o pregao fechado de 22/09
    // inteiro carimbado como 23/09 as 10:19, e a ficha desenhou os dois
    // candles iguais, lado a lado.
    const viva3 = montarCandle("VIVA3", "brapi", {
      preco: 22.78,
      abertura: 23.76,
      maxima: 23.79,
      minima: 22.12,
      volume: 9265200,
      hora: new Date("2026-09-23T13:19:30Z"),
    });
    const fechado = barra("2026-09-22", { open: 23.76, high: 23.79, low: 22.12, close: 22.78 });

    it("nao desenha quando os quatro precos batem", () => {
      assert.equal(candleParcial([fechado], viva3), null);
    });

    it("desenha assim que qualquer um dos quatro anda", () => {
      // O parcial de verdade do mesmo papel na mesma manha, pelo Yahoo.
      const real = montarCandle("VIVA3", "yahoo", {
        preco: 22.62,
        abertura: 22.6,
        maxima: 22.75,
        minima: 22.59,
        volume: 9400,
        hora: new Date("2026-09-23T13:08:53Z"),
      });
      assert.notEqual(candleParcial([fechado], real), null);
    });

    it("um centavo de diferenca ja e movimento", () => {
      const andou = { ...viva3, close: 22.79 };
      assert.equal(candleParcial([fechado], andou), andou);
    });

    it("barra sem abertura nao esconde o candle", () => {
      // Papel com um negocio so no dia: nulo nunca e igual a um preco, entao a
      // comparacao falha e o candle passa. Na duvida, desenhar.
      const semAbertura = barra("2026-09-22", {
        open: null,
        high: 23.79,
        low: 22.12,
        close: 22.78,
      });
      assert.equal(candleParcial([semAbertura], viva3), viva3);
    });

    it("compara com duas casas, a precisao da B3", () => {
      // O banco guarda NUMERIC(18,4): 22.7800 e o mesmo 22,78 do candle.
      const comQuatroCasas = barra("2026-09-22", {
        open: 23.76,
        high: 23.79,
        low: 22.12,
        close: 22.78,
      });
      assert.equal(candleParcial([comQuatroCasas], viva3), null);
    });
  });

  describe("fim de semana", () => {
    // 26/09/2026 e sabado, 27/09 e domingo. A cotacao guardada e a de sexta,
    // mas a brapi a carimba com o relogio de agora -- e "sabado > sexta" era
    // verdade, entao o candle de sabado aparecia.
    const sabado = montarCandle("ALPA4", "brapi", {
      ...campos(),
      hora: new Date("2026-09-26T14:00:00Z"),
    });
    const domingo = montarCandle("ALPA4", "brapi", {
      ...campos(),
      hora: new Date("2026-09-27T14:00:00Z"),
    });

    it("nao existe pregao no sabado nem no domingo", () => {
      assert.equal(candleParcial([barra("2026-09-25")], sabado), null);
      assert.equal(candleParcial([barra("2026-09-25")], domingo), null);
    });

    it("vale mesmo sem barra nenhuma no grafico", () => {
      assert.equal(candleParcial([], sabado), null);
    });

    it("a sexta seguinte continua aparecendo", () => {
      const sexta = montarCandle("ALPA4", "yahoo", {
        ...campos(),
        hora: new Date("2026-09-25T14:00:00Z"),
      });
      assert.notEqual(candleParcial([barra("2026-09-24")], sexta), null);
    });
  });
});
