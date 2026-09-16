// A regua do grafico: medir nivel e movimento. `npm test`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { medirMovimento, medirNivel } from "./regua.ts";

const perto = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-9, msg ?? `${a} != ${b}`);

// Mesmo trade de referencia de `posicao.test.mjs`: 70 acoes, PM 38, realizado
// 152, custo comprado 5700 (compra 100x38,20 -> compra 50x37,60 -> venda
// 80x39,90).
const TRADE = { quantidade: 70, precoMedio: 38, custoComprado: 5700, realizado: 152 };

describe("medirNivel", () => {
  it("exemplo de referencia: agora 50,43 ate um nivel de 55,00", () => {
    const r = medirNivel({ agora: 50.43, nivel: 55.0, trade: TRADE });
    perto(r.porAcao, 4.57);
    perto(r.variacaoPct, 0.0906206623);
    assert.equal(r.direcao, "acima");

    assert.ok(r.trade);
    perto(r.trade.ateLa, 319.9);
    perto(r.trade.inteiro.resultado, 1342.0);
    perto(r.trade.inteiro.resultadoPct, 0.2354385965);
  });

  it("nivel abaixo de agora: direcao abaixo, por acao negativo", () => {
    const r = medirNivel({ agora: 50.43, nivel: 45.0, trade: TRADE });
    assert.equal(r.direcao, "abaixo");
    perto(r.porAcao, -5.43);
    assert.ok(r.variacaoPct < 0);
    assert.ok(r.trade && r.trade.ateLa < 0);
  });

  it("sem trade: o bloco do trade fica null", () => {
    const r = medirNivel({ agora: 50.43, nivel: 55.0 });
    assert.equal(r.trade, null);
  });

  it("trade com quantidade 0: fica null, nao ha posicao para medir", () => {
    const r = medirNivel({
      agora: 50.43,
      nivel: 55.0,
      trade: { quantidade: 0, precoMedio: 38, custoComprado: 5700, realizado: 152 },
    });
    assert.equal(r.trade, null);
  });

  it("nivel igual a agora: direcao abaixo (empate nao e alta)", () => {
    const r = medirNivel({ agora: 50.43, nivel: 50.43 });
    assert.equal(r.direcao, "abaixo");
    perto(r.porAcao, 0);
  });
});

describe("medirMovimento", () => {
  const DATAS = [
    "2026-09-01",
    "2026-09-02",
    "2026-09-03",
    "2026-09-04",
    "2026-09-07",
    "2026-09-08",
  ];

  it("do ponto mais antigo pro mais novo", () => {
    const r = medirMovimento({
      a: { data: "2026-09-02", preco: 40 },
      b: { data: "2026-09-07", preco: 44 },
      datas: DATAS,
    });
    assert.equal(r.de.data, "2026-09-02");
    assert.equal(r.ate.data, "2026-09-07");
    perto(r.porAcao, 4);
    perto(r.variacaoPct, 0.1);
  });

  it("em ordem invertida (b tocado antes de a, mas mais novo): mesmo resultado", () => {
    const r = medirMovimento({
      a: { data: "2026-09-07", preco: 44 },
      b: { data: "2026-09-02", preco: 40 },
      datas: DATAS,
    });
    assert.equal(r.de.data, "2026-09-02");
    assert.equal(r.de.preco, 40);
    assert.equal(r.ate.data, "2026-09-07");
    assert.equal(r.ate.preco, 44);
    perto(r.porAcao, 4);
  });

  it("mesma data: a ordem fica a dos toques, nao inverte", () => {
    const r = medirMovimento({
      a: { data: "2026-09-04", preco: 41 },
      b: { data: "2026-09-04", preco: 43 },
      datas: DATAS,
    });
    assert.equal(r.de.preco, 41);
    assert.equal(r.ate.preco, 43);
    assert.equal(r.pregoes, 0); // (04, 04] nao tem nenhuma data estritamente depois de 04 e <= 04
  });

  it("conta os pregoes em (de, ate], nao em [de, ate]", () => {
    const r = medirMovimento({
      a: { data: "2026-09-02", preco: 40 },
      b: { data: "2026-09-08", preco: 44 },
      datas: DATAS,
    });
    // datas depois de 02 e ate 08: 03, 04, 07, 08 -> 4 pregoes.
    assert.equal(r.pregoes, 4);
  });
});
