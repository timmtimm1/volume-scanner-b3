// O estado que o historico guarda para quem sai e volta. `npm test`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { chaveDoEvento, lerEstadoDoHistorico, temFiltro } from "./estado-do-historico.ts";

const MINIMO = 3;
const LEVA = 100;

const COMPLETO = {
  corte: 4.5,
  busca: "petr",
  desde: "2026-09-01",
  ate: "2026-10-08",
  ordemZ: "desc",
  linhas: 300,
  selecionado: "PETR4|2026-10-08",
  rolagem: 1840,
};

describe("lerEstadoDoHistorico", () => {
  it("sem nada salvo, null", () => {
    assert.equal(lerEstadoDoHistorico(null, MINIMO, LEVA), null);
    assert.equal(lerEstadoDoHistorico("", MINIMO, LEVA), null);
  });

  it("texto que nao e estado, null", () => {
    assert.equal(lerEstadoDoHistorico("{quebrado", MINIMO, LEVA), null);
    assert.equal(lerEstadoDoHistorico("[1,2]", MINIMO, LEVA), null);
    assert.equal(lerEstadoDoHistorico("42", MINIMO, LEVA), null);
    assert.equal(lerEstadoDoHistorico("null", MINIMO, LEVA), null);
  });

  it("estado completo volta igual", () => {
    assert.deepEqual(lerEstadoDoHistorico(JSON.stringify(COMPLETO), MINIMO, LEVA), COMPLETO);
  });

  it("campo fora do lugar volta ao padrao sem apagar os outros", () => {
    const r = lerEstadoDoHistorico(
      JSON.stringify({
        ...COMPLETO,
        corte: 2, // abaixo do piso do site
        desde: "01/09/2026",
        ordemZ: "lado",
        linhas: 50,
        rolagem: -10,
        selecionado: 7,
      }),
      MINIMO,
      LEVA,
    );
    assert.deepEqual(r, {
      corte: MINIMO,
      busca: "petr",
      desde: "",
      ate: "2026-10-08",
      ordemZ: null,
      linhas: LEVA,
      selecionado: null,
      rolagem: 0,
    });
  });

  it("corte acima do teto do controle volta ao piso", () => {
    const r = lerEstadoDoHistorico(JSON.stringify({ ...COMPLETO, corte: 12 }), MINIMO, LEVA);
    assert.equal(r?.corte, MINIMO);
  });

  it("busca longa demais e cortada", () => {
    const r = lerEstadoDoHistorico(JSON.stringify({ ...COMPLETO, busca: "x".repeat(500) }), MINIMO, LEVA);
    assert.equal(r?.busca.length, 60);
  });
});

describe("temFiltro", () => {
  const PADRAO = { corte: MINIMO, busca: "", desde: "", ate: "", ordemZ: null };

  it("tudo no padrao, sem filtro", () => {
    assert.equal(temFiltro(PADRAO, MINIMO), false);
    assert.equal(temFiltro({ ...PADRAO, busca: "   " }, MINIMO), false);
  });

  it("qualquer campo fora do padrao conta", () => {
    assert.equal(temFiltro({ ...PADRAO, corte: 6 }, MINIMO), true);
    assert.equal(temFiltro({ ...PADRAO, busca: "vale" }, MINIMO), true);
    assert.equal(temFiltro({ ...PADRAO, desde: "2026-09-01" }, MINIMO), true);
    assert.equal(temFiltro({ ...PADRAO, ate: "2026-09-01" }, MINIMO), true);
    assert.equal(temFiltro({ ...PADRAO, ordemZ: "asc" }, MINIMO), true);
  });
});

describe("chaveDoEvento", () => {
  it("papel e pregao", () => {
    assert.equal(chaveDoEvento({ ticker: "VALE3", tradeDate: "2026-10-08" }), "VALE3|2026-10-08");
  });
});
