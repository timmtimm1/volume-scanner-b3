// Calculadora de lote e validacao do perfil de risco. `npm test`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  PerfilInvalido,
  calcularLote,
  numeroDoTexto,
  validarPerfil,
} from "./lote.ts";

describe("calcularLote", () => {
  it("caso normal: o risco manda", () => {
    // R$ 10.000 x 1% = R$ 100 de risco; entrada 20,00, stop 19,00 -> R$ 1 por acao
    const l = calcularLote({ capital: 10000, riscoPct: 1, entrada: 20, stop: 19 });
    assert.equal(l.quantidade, 100);
    assert.equal(l.perdaMaxima, 100);
    assert.equal(l.valorPosicao, 2000);
    assert.ok(Math.abs(l.pctDoCapital - 0.01) < 1e-12);
    assert.equal(l.limitadoPeloCapital, false);
  });

  it("arredonda para baixo, em acoes inteiras", () => {
    // risco de R$ 100 / R$ 0,30 por acao = 333,33 -> 333
    const l = calcularLote({ capital: 10000, riscoPct: 1, entrada: 10, stop: 9.7 });
    assert.equal(l.quantidade, 333);
    assert.equal(l.perdaMaxima, 99.9);
    assert.ok(l.pctDoCapital < 0.01);
  });

  it("ponto flutuante nao tira uma acao: 100 / 0,5 = 200", () => {
    const l = calcularLote({ capital: 10000, riscoPct: 1, entrada: 10, stop: 9.5 });
    assert.equal(l.quantidade, 200);
  });

  it("limitado pelo capital: stop curto pede mais acoes do que o capital compra", () => {
    // risco permite 100 / 0,10 = 1000 acoes (R$ 50.000); o capital de R$ 10.000 compra 200
    const l = calcularLote({ capital: 10000, riscoPct: 1, entrada: 50, stop: 49.9 });
    assert.equal(l.quantidade, 200);
    assert.equal(l.valorPosicao, 10000);
    assert.equal(l.perdaMaxima, 20);
    assert.equal(l.limitadoPeloCapital, true);
  });

  it("empate entre risco e capital nao conta como limitado pelo capital", () => {
    // risco: 100 / 0,50 = 200 acoes; capital: 10000 / 50 = 200 acoes
    const l = calcularLote({ capital: 10000, riscoPct: 1, entrada: 50, stop: 49.5 });
    assert.equal(l.quantidade, 200);
    assert.equal(l.limitadoPeloCapital, false);
  });

  it("capital menor que uma acao: zero, limitado pelo capital", () => {
    const l = calcularLote({ capital: 30, riscoPct: 1, entrada: 50, stop: 40 });
    assert.equal(l.quantidade, 0);
    assert.equal(l.valorPosicao, 0);
    assert.equal(l.limitadoPeloCapital, false); // risco tambem da zero: 0,30 / 10
  });

  it("entrada igual ou abaixo do stop: sem lote", () => {
    for (const stop of [20, 21]) {
      const l = calcularLote({ capital: 10000, riscoPct: 1, entrada: 20, stop });
      assert.equal(l.quantidade, 0);
      assert.equal(l.perdaMaxima, 0);
      assert.equal(l.limitadoPeloCapital, false);
    }
  });

  it("capital ausente (ou dado faltando): sem lote, sem NaN", () => {
    for (const falta of ["capital", "riscoPct", "entrada", "stop"]) {
      const e = { capital: 10000, riscoPct: 1, entrada: 20, stop: 19, [falta]: null };
      const l = calcularLote(e);
      assert.equal(l.quantidade, 0);
      assert.equal(l.pctDoCapital, 0);
    }
    assert.equal(calcularLote({ capital: undefined, riscoPct: 1, entrada: 20, stop: 19 }).quantidade, 0);
    assert.equal(calcularLote({ capital: 0, riscoPct: 1, entrada: 20, stop: 19 }).quantidade, 0);
  });
});

describe("numeroDoTexto", () => {
  it("entende o jeito brasileiro e o simples", () => {
    assert.equal(numeroDoTexto("10.000,50"), 10000.5);
    assert.equal(numeroDoTexto("10000,5"), 10000.5);
    assert.equal(numeroDoTexto("10000.5"), 10000.5);
    assert.equal(numeroDoTexto("10.000"), 10000);
    assert.equal(numeroDoTexto(" 1,5 "), 1.5);
    assert.equal(numeroDoTexto("1.5"), 1.5);
  });
  it("devolve null para o que nao e numero", () => {
    assert.equal(numeroDoTexto(""), null);
    assert.equal(numeroDoTexto("abc"), null);
    assert.equal(numeroDoTexto("1,2,3"), null);
    assert.equal(numeroDoTexto("-5"), null);
  });
});

describe("validarPerfil", () => {
  it("aceita capital e risco validos", () => {
    assert.deepEqual(validarPerfil({ capital: 10000, riscoPct: 1 }), { capital: 10000, riscoPct: 1 });
    assert.deepEqual(validarPerfil({ capital: 2500.5, riscoPct: 0.25 }), {
      capital: 2500.5,
      riscoPct: 0.25,
    });
    assert.deepEqual(validarPerfil({ capital: "800", riscoPct: "10" }), { capital: 800, riscoPct: 10 });
  });

  it("recusa capital zero, negativo, ausente ou com tres casas", () => {
    for (const capital of [0, -1, undefined, null, "x", NaN, 1.234, 1e13]) {
      assert.throws(() => validarPerfil({ capital, riscoPct: 1 }), PerfilInvalido);
    }
  });

  it("recusa risco zero, acima de 10, ausente ou com tres casas", () => {
    for (const riscoPct of [0, -1, 10.01, 11, undefined, null, "x", 0.123]) {
      assert.throws(() => validarPerfil({ capital: 1000, riscoPct }), PerfilInvalido);
    }
  });
});
