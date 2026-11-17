// O dia de hoje das criptos: confirmacao da entrada e o candle em andamento.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { comCandleDeHoje, diaSeguinte, horaEmBrasilia, situacaoDaEntrada } from "./cripto-hoje.ts";

const hoje = {
  moeda: "AAVE", dia: "2026-11-17", abertura: 108.2, maxima: 114.29, minima: 105.1,
  ultimo: 112.4, volume: 2.5e7, hora: "2026-11-17T12:47:00.000Z",
};

describe("dia de hoje das criptos", () => {
  it("o dia seguinte atravessa mes e ano", () => {
    assert.equal(diaSeguinte("2026-11-16"), "2026-11-17");
    assert.equal(diaSeguinte("2026-11-30"), "2026-12-01");
    assert.equal(diaSeguinte("2026-12-31"), "2027-01-01");
  });

  it("a entrada passou quando a maxima de hoje chegou no gatilho", () => {
    const s = situacaoDaEntrada(111.05, "2026-11-16", hoje);
    assert.equal(s.passou, true);
    assert.equal(s.maxima, 114.29);
    assert.equal(s.ultimo, 112.4);
  });

  it("tocar exatamente o gatilho conta, como no alerta", () => {
    assert.equal(situacaoDaEntrada(114.29, "2026-11-16", hoje).passou, true);
  });

  it("ainda nao passou: diz quanto falta a partir do preco de agora", () => {
    const s = situacaoDaEntrada(120, "2026-11-16", hoje);
    assert.equal(s.passou, false);
    assert.ok(Math.abs(s.falta - (120 / 112.4 - 1)) < 1e-12);
  });

  it("fora do dia da confirmacao nao mostra nada", () => {
    // as 21h05, antes do pipeline: a lista e de anteontem, "hoje" ja e outro dia
    assert.equal(situacaoDaEntrada(111.05, "2026-11-15", hoje), null);
    assert.equal(situacaoDaEntrada(111.05, "2026-11-17", hoje), null);
    assert.equal(situacaoDaEntrada(111.05, "2026-11-16", undefined), null);
  });

  it("o candle de hoje entra no fim das barras, e so uma vez", () => {
    const barras = [{ tradeDate: "2026-11-16", open: 1, high: 2, low: 0.5, close: 1.5, volumeFinancial: 10 }];
    const com = comCandleDeHoje(barras, hoje);
    assert.equal(com.length, 2);
    assert.deepEqual(com[1], {
      tradeDate: "2026-11-17", open: 108.2, high: 114.29, low: 105.1, close: 112.4, volumeFinancial: 2.5e7,
    });
    assert.equal(comCandleDeHoje(com, hoje).length, 2);
    assert.equal(comCandleDeHoje(barras, undefined), barras);
  });

  it("a hora sai no horario de Brasilia", () => {
    assert.equal(horaEmBrasilia("2026-11-17T12:47:00.000Z"), "09:47");
  });
});
