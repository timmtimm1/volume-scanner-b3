// A aba Setups: secoes, resumo do historico e situacao do alerta.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  contraOMercado,
  desdeAEntrada,
  nomeDosPadroes,
  resumoDoHistorico,
  separar,
  situacaoDoAlerta,
} from "./setups-tela.ts";

function setup(campos) {
  return {
    id: 1,
    ticker: "SAPR11",
    tradeDate: "2026-10-20",
    categoria: "reversao",
    padroes: ["martelo"],
    toques: 3,
    virou: false,
    furou: false,
    rvol: 2.3,
    destaque: false,
    contexto: [],
    fechamento: 40,
    maxima: 40,
    minima: 38.46,
    suporte: 38.5,
    resistencia: 45.13,
    espacoR: 3.3,
    riscoPct: 3.85,
    aoVivo: true,
    estado: "armado",
    confirmadoEm: null,
    entrada: null,
    encerradoEm: null,
    saida: null,
    r: { 5: null, 10: null, 20: null },
    m: { 5: null, 10: null, 20: null },
    rc: { 5: null, 10: null, 20: null },
    alerta: null,
    ultimoFechamento: 40,
    ultimoPregao: "2026-10-20",
    pregoesDesde: null,
    ...campos,
  };
}

describe("separar", () => {
  const lista = [
    setup({ id: 1, estado: "armado", rvol: 1.6 }),
    setup({ id: 2, estado: "armado", rvol: 3.1 }),
    setup({ id: 3, estado: "confirmado", confirmadoEm: "2026-10-15" }),
    setup({ id: 4, categoria: "forca", padroes: ["forca"], estado: "armado" }),
    setup({ id: 5, estado: "stop", tradeDate: "2026-10-01", aoVivo: true }),
    setup({ id: 6, estado: "prazo", tradeDate: "2026-09-01", aoVivo: false }),
  ];

  it("armados por volume, so candle de reversao", () => {
    assert.deepEqual(separar(lista, false).armados.map((s) => s.id), [2, 1]);
  });

  it("forca vai a parte, mesmo armada", () => {
    const s = separar(lista, false);
    assert.deepEqual(s.forca.map((x) => x.id), [4]);
    assert.ok(!s.armados.some((x) => x.categoria === "forca"));
  });

  it("historico so com os ao vivo, a menos que se peca os retroativos", () => {
    assert.deepEqual(separar(lista, false).historico.map((s) => s.id), [5]);
    assert.deepEqual(separar(lista, true).historico.map((s) => s.id), [5, 6]);
  });

  it("em andamento e o confirmado", () => {
    assert.deepEqual(separar(lista, false).emAndamento.map((s) => s.id), [3]);
  });
});

describe("resumoDoHistorico", () => {
  it("media contra o mercado so de quem tem 20 pregoes, so reversao", () => {
    const r = resumoDoHistorico([
      setup({ estado: "stop", confirmadoEm: "2026-10-02", r: { 5: 0, 10: 0, 20: 0.05 }, m: { 5: 0, 10: 0, 20: 0.01 } }),
      setup({ estado: "nao_confirmou", r: { 5: 0, 10: 0, 20: -0.02 }, m: { 5: 0, 10: 0, 20: 0.0 } }),
      setup({ estado: "prazo", confirmadoEm: "2026-09-02" }),
      setup({ categoria: "forca", estado: "stop", r: { 5: 0, 10: 0, 20: 0.5 }, m: { 5: 0, 10: 0, 20: 0 } }),
    ]);
    assert.equal(r.setups, 3);
    assert.equal(r.confirmaram, 2);
    assert.equal(r.comResultado, 2);
    assert.ok(Math.abs(r.media20 - 0.01) < 1e-12);
  });

  it("sem resultado ainda, media nula", () => {
    assert.equal(resumoDoHistorico([setup({})]).media20, null);
  });
});

describe("contas", () => {
  it("contra o mercado e desde a entrada", () => {
    const s = setup({ r: { 5: 0.04, 10: null, 20: null }, m: { 5: 0.01, 10: null, 20: null }, entrada: 40, ultimoFechamento: 42 });
    assert.ok(Math.abs(contraOMercado(s, 5) - 0.03) < 1e-12);
    assert.equal(contraOMercado(s, 10), null);
    assert.ok(Math.abs(desdeAEntrada(s) - 0.05) < 1e-12);
  });

  it("nome dos padroes", () => {
    assert.equal(nomeDosPadroes({ padroes: ["martelo", "engolfo"] }), "Martelo + Engolfo de alta");
  });
});

describe("situacaoDoAlerta", () => {
  const alerta = { preco: 40.01, disparadoEm: null, precoDisparo: null, expiraEm: "2026-10-21" };

  it("vigiando ate o pregao da confirmacao", () => {
    assert.equal(situacaoDoAlerta(setup({ alerta }), "2026-10-21"), "alerta vigiando até 21/10");
  });

  it("vencido depois dele", () => {
    assert.equal(situacaoDoAlerta(setup({ alerta }), "2026-10-22"), "alerta venceu sem romper");
  });

  it("disparado mostra a hora de Sao Paulo e o preco", () => {
    const s = setup({ alerta: { ...alerta, disparadoEm: "2026-10-21T13:42:00Z", precoDisparo: 40.05 } });
    assert.equal(situacaoDoAlerta(s, "2026-10-21"), "alerta rompeu às 10:42 a R$ 40,05");
  });

  it("sem alerta, nada", () => {
    assert.equal(situacaoDoAlerta(setup({}), "2026-10-21"), null);
  });
});
