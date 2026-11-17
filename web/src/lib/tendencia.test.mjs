// Tendencia pelas medias escolhidas: alta, lateral, baixa ou sem historico.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  ESCOLHA_PADRAO,
  alternar,
  classificar,
  contar,
  escolhaDoTexto,
  nomeDaEscolha,
  passaNoFiltro,
} from "./tendencia.ts";

const todas = (v) => ({
  mme9: v, mme20: v, mme50: v, mme80: v, mme200: v,
  mma9: v, mma20: v, mma50: v, mma80: v, mma200: v,
});

const NOVE_E_80 = { tipo: "MME", periodos: [9, 80] };

describe("o ponto de partida", () => {
  it("nao exige a MME 9 subindo: o 9.4 e a 9 virando para baixo dentro da tendencia", () => {
    assert.ok(!ESCOLHA_PADRAO.periodos.includes(9));
    const correcao = { ...todas(1), mme9: -1 };
    assert.equal(classificar(correcao, ESCOLHA_PADRAO), "alta");
  });
});

describe("classificar", () => {
  it("todas subindo e alta; todas caindo e baixa", () => {
    assert.equal(classificar(todas(1), ESCOLHA_PADRAO), "alta");
    assert.equal(classificar(todas(-1), ESCOLHA_PADRAO), "baixa");
  });

  it("medias que discordam: lateral", () => {
    const inc = { ...todas(1), mme9: -1 };
    assert.equal(classificar(inc, NOVE_E_80), "lateral");
    // a media que discorda nao foi escolhida: continua alta
    assert.equal(classificar(inc, { tipo: "MME", periodos: [20, 80] }), "alta");
  });

  it("sem historico em uma das escolhidas: fica de fora (null)", () => {
    const nova = { ...todas(1), mme80: 0, mme200: 0 };
    assert.equal(classificar(nova, NOVE_E_80), null);
    assert.equal(classificar(nova, { tipo: "MME", periodos: [9, 20] }), "alta");
  });

  it("o tipo escolhe as colunas: MMA nao olha a MME", () => {
    const inc = { ...todas(-1), mme9: 1, mme80: 1 };
    assert.equal(classificar(inc, { tipo: "MME", periodos: [9, 80] }), "alta");
    assert.equal(classificar(inc, { tipo: "MMA", periodos: [9, 80] }), "baixa");
  });
});

describe("contar", () => {
  it("um por estado e os sem historico a parte", () => {
    const linhas = [
      { inclinacoes: todas(1) },
      { inclinacoes: todas(1) },
      { inclinacoes: todas(-1) },
      { inclinacoes: { ...todas(1), mme9: -1 } },
      { inclinacoes: { ...todas(1), mme80: 0 } },
    ];
    assert.deepEqual(contar(linhas, NOVE_E_80), { alta: 2, lateral: 1, baixa: 1, sem: 1 });
  });
});

describe("alternar", () => {
  it("liga na ordem dos periodos e desliga", () => {
    const com20 = alternar(NOVE_E_80, 20);
    assert.deepEqual(com20.periodos, [9, 20, 80]);
    assert.deepEqual(alternar(com20, 9).periodos, [20, 80]);
    assert.equal(nomeDaEscolha(com20), "MME 9 + 20 + 80");
  });

  it("a ultima media nao desliga", () => {
    const so9 = { tipo: "MME", periodos: [9] };
    assert.deepEqual(alternar(so9, 9), so9);
  });
});

describe("escolhaDoTexto", () => {
  it("le o que o filtro guardou", () => {
    const texto = JSON.stringify({ tipo: "MMA", periodos: [200, 9], filtro: "baixa" });
    assert.deepEqual(escolhaDoTexto(texto), {
      escolha: { tipo: "MMA", periodos: [9, 200] },
      filtro: "baixa",
    });
  });

  it("sem nada guardado, nao filtra: Todas, com MME 20 + 80", () => {
    assert.deepEqual(escolhaDoTexto(null), { escolha: ESCOLHA_PADRAO, filtro: "todas" });
    assert.equal(escolhaDoTexto(JSON.stringify({ tipo: "MME", periodos: [9], filtro: "x" })).filtro, "todas");
  });

  it("qualquer coisa estranha volta ao padrao", () => {
    for (const t of [null, "", "{", "[]", JSON.stringify({ tipo: "X", periodos: [9] }), JSON.stringify({ tipo: "MME", periodos: [7] })]) {
      assert.deepEqual(escolhaDoTexto(t).escolha, ESCOLHA_PADRAO, String(t));
    }
  });
});

describe("passaNoFiltro", () => {
  it("todas deixa passar tudo, inclusive sem historico; os outros, so o proprio estado", () => {
    assert.equal(passaNoFiltro(null, "todas"), true);
    assert.equal(passaNoFiltro("baixa", "todas"), true);
    assert.equal(passaNoFiltro("alta", "alta"), true);
    assert.equal(passaNoFiltro("lateral", "alta"), false);
    assert.equal(passaNoFiltro(null, "alta"), false);
  });
});

