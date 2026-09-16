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
  it("do inicio para a ponta, na ordem do gesto", () => {
    const r = medirMovimento({
      inicio: { indice: 2, preco: 40 },
      fim: { indice: 7, preco: 44 },
    });
    perto(r.porAcao, 4);
    perto(r.variacaoPct, 0.1);
    assert.equal(r.candles, 5);
  });

  it("arrastar para a esquerda tambem vale: a ponta fica com indice menor que o inicio", () => {
    const r = medirMovimento({
      inicio: { indice: 7, preco: 44 },
      fim: { indice: 2, preco: 40 },
    });
    perto(r.porAcao, -4);
    perto(r.variacaoPct, -4 / 44);
    assert.equal(r.candles, 5);
  });

  it("nao reordena por indice -- o inicio e sempre o primeiro tocado, mesmo se a ponta ficou 'antes'", () => {
    // Mesmo par de precos do teste anterior, mas com o gesto na outra ordem:
    // a variacao inverte, porque agora e do preco 40 para o 44.
    const r = medirMovimento({
      inicio: { indice: 2, preco: 44 },
      fim: { indice: 7, preco: 40 },
    });
    perto(r.porAcao, -4);
    perto(r.variacaoPct, -4 / 44);
  });

  it("mesmo indice (gesto sem se mover no eixo do tempo): 0 candles", () => {
    const r = medirMovimento({
      inicio: { indice: 4, preco: 41 },
      fim: { indice: 4, preco: 43 },
    });
    perto(r.porAcao, 2);
    assert.equal(r.candles, 0);
  });

  it("inicio e fim iguais: variacao zero", () => {
    const r = medirMovimento({
      inicio: { indice: 4, preco: 41 },
      fim: { indice: 4, preco: 41 },
    });
    perto(r.porAcao, 0);
    perto(r.variacaoPct, 0);
    assert.equal(r.candles, 0);
  });
});
