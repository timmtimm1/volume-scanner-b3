// A curva do patrimonio: capital + resultado de todos os trades, dia a dia.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { montarCurva, resumirCurva } from "./patrimonio.ts";

const op = (data, quantidadeApos, realizadoApos = 0) => ({ data, quantidadeApos, realizadoApos });
const snap = (data, resultado) => ({ data, resultado });
const valores = (c) => c.map((p) => p.patrimonio);

describe("montarCurva", () => {
  it("sem trade nenhum nao ha curva", () => {
    assert.deepEqual(montarCurva(1000, [], "2026-11-23"), []);
    assert.deepEqual(montarCurva(1000, [{ id: 1, operacoes: [], snapshots: [] }], "2026-11-23"), []);
  });

  it("comeca no capital, no dia anterior ao primeiro trade", () => {
    const c = montarCurva(1000, [{ id: 1, operacoes: [op("2026-11-20", 1)], snapshots: [snap("2026-11-20", 10)] }], "2026-11-20");
    assert.deepEqual(c[0], { dia: "2026-11-19", patrimonio: 1000, realizado: 0, aberto: 0 });
    assert.equal(c[1].patrimonio, 1010);
    assert.equal(c[1].aberto, 10);
  });

  it("trade encerrado continua contando depois de fechar", () => {
    const t = {
      id: 1,
      operacoes: [op("2026-11-20", 1), op("2026-11-21", 0, 25)],
      snapshots: [snap("2026-11-20", 10), snap("2026-11-21", 25)],
    };
    const c = montarCurva(1000, [t], "2026-11-23");
    assert.deepEqual(valores(c), [1000, 1010, 1025, 1025, 1025]);
    assert.equal(c.at(-1).realizado, 25);
    assert.equal(c.at(-1).aberto, 0);
  });

  it("trade fechado hoje conta hoje, antes da marcacao da noite", () => {
    const t = { id: 1, operacoes: [op("2026-11-22", 1), op("2026-11-23", 0, -40)], snapshots: [snap("2026-11-22", 5)] };
    assert.deepEqual(valores(montarCurva(1000, [t], "2026-11-23")), [1000, 1005, 960]);
  });

  it("trade aberto usa o preco de agora so no dia de hoje", () => {
    const t = { id: 1, operacoes: [op("2026-11-22", 1)], snapshots: [snap("2026-11-22", 5)], resultadoAgora: 30 };
    assert.deepEqual(valores(montarCurva(1000, [t], "2026-11-23")), [1000, 1005, 1030]);
  });

  it("dia sem snapshot repete o ultimo resultado", () => {
    const t = { id: 1, operacoes: [op("2026-11-20", 1)], snapshots: [snap("2026-11-20", 7)] };
    assert.deepEqual(valores(montarCurva(1000, [t], "2026-11-22")), [1000, 1007, 1007, 1007]);
  });

  it("operacao mais nova que o snapshot manda no realizado", () => {
    const t = { id: 1, operacoes: [op("2026-11-20", 2), op("2026-11-21", 1, 12)], snapshots: [snap("2026-11-20", 9)] };
    assert.deepEqual(valores(montarCurva(1000, [t], "2026-11-21")), [1000, 1009, 1012]);
  });

  it("posicao vendida (quantidade negativa) entra igual", () => {
    const t = { id: 1, operacoes: [op("2026-11-22", -0.5)], snapshots: [snap("2026-11-22", -15)] };
    assert.equal(montarCurva(1000, [t], "2026-11-22").at(-1).patrimonio, 985);
  });

  it("soma varios trades no mesmo dia", () => {
    const a = { id: 1, operacoes: [op("2026-11-22", 1)], snapshots: [snap("2026-11-22", 10)] };
    const b = { id: 2, operacoes: [op("2026-11-22", 1)], snapshots: [snap("2026-11-22", -4)] };
    assert.equal(montarCurva(1000, [a, b], "2026-11-22").at(-1).patrimonio, 1006);
  });
});

describe("resumirCurva", () => {
  const ponto = (dia, patrimonio, realizado = 0, aberto = 0) => ({ dia, patrimonio, realizado, aberto });

  it("sem curva, tudo fica no capital", () => {
    const r = resumirCurva(1000, []);
    assert.equal(r.atual, 1000);
    assert.equal(r.resultado, 0);
    assert.equal(r.maiorQueda, 0);
  });

  it("resultado e maior queda do topo ao fundo", () => {
    const r = resumirCurva(1000, [ponto("a", 1000), ponto("b", 1200), ponto("c", 900), ponto("d", 1100, 60, 40)]);
    assert.equal(r.atual, 1100);
    assert.equal(r.resultado, 100);
    assert.ok(Math.abs(r.resultadoPct - 0.1) < 1e-12);
    assert.equal(r.maiorQueda, -300);
    assert.ok(Math.abs(r.maiorQuedaPct + 0.25) < 1e-12);
    assert.equal(r.realizado, 60);
    assert.equal(r.aberto, 40);
  });
});
