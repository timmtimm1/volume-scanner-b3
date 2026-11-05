// Risco e resultado em R, estatistica por setup e validacao dos campos do diario. `npm test`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { CATEGORIAS_DE_SETUP } from "./config.ts";
import {
  DiarioInvalido,
  estatisticaPorSetup,
  resultadoEmRDoTrade,
  riscoEmReais,
  validarCamposDoDiario,
} from "./diario.ts";
import { aplicarOperacoes, marcarAgora } from "./posicao.ts";

const compra = (quantidade, preco) => ({ tipo: "compra", quantidade, preco });
const venda = (quantidade, preco) => ({ tipo: "venda", quantidade, preco });

/** Monta o trade como o site o devolve: estado depois da ultima operacao. */
function trade(operacoes, stop, extra = {}) {
  const ord = operacoes.map((o, i) => ({ id: i + 1, data: `2026-09-${10 + i}`, ...o }));
  const { estados, encerradoEm } = aplicarOperacoes(ord);
  const e = estados.at(-1);
  return { stop, operacoes, encerradoEm, categoriaSetup: null, ...e, ...extra };
}

describe("riscoEmReais", () => {
  it("uma compra: quantidade x (preco - stop)", () => {
    assert.equal(riscoEmReais(trade([compra(100, 20)], 19)), 100);
  });

  it("soma sobre todas as compras, cada uma com o seu preco; venda nao entra", () => {
    // 100 x (20 - 19) + 50 x (21 - 19) = 200
    assert.equal(riscoEmReais(trade([compra(100, 20), compra(50, 21), venda(30, 22)], 19)), 200);
  });

  it("sem stop: null", () => {
    assert.equal(riscoEmReais(trade([compra(100, 20)], null)), null);
  });

  it("alguma compra a preco <= stop: null", () => {
    assert.equal(riscoEmReais(trade([compra(100, 20), compra(10, 19)], 19)), null);
    assert.equal(riscoEmReais(trade([compra(100, 18)], 19)), null);
  });
});

describe("resultadoEmRDoTrade", () => {
  it("trade aberto: o resultado de agora sobre o risco", () => {
    // 100 a 20, stop 19 (risco 100); a 22 -> +200 = +2 R
    assert.equal(resultadoEmRDoTrade(trade([compra(100, 20)], 19), 22), 2);
    assert.equal(resultadoEmRDoTrade(trade([compra(100, 20)], 19), 18.5), -1.5);
  });

  it("encerrado: so o realizado", () => {
    const t = trade([compra(100, 20), venda(100, 19)], 19.5);
    // risco 50, realizado -100 -> -2 R
    assert.equal(resultadoEmRDoTrade(t, null), -2);
  });

  it("sem stop ou compra no stop: null", () => {
    assert.equal(resultadoEmRDoTrade(trade([compra(100, 20)], null), 22), null);
    assert.equal(resultadoEmRDoTrade(trade([compra(100, 19)], 19), 22), null);
  });

  it("o resultado total e o mesmo de marcarAgora (parcial vendido + o que sobra)", () => {
    const t = trade([compra(100, 20), compra(50, 21), venda(60, 23)], 19);
    for (const preco of [null, 18, 21.37, 25]) {
      const total = marcarAgora(t, preco).resultado;
      const risco = riscoEmReais(t);
      assert.ok(Math.abs(resultadoEmRDoTrade(t, preco) - total / risco) < 1e-12);
    }
  });
});

describe("estatisticaPorSetup", () => {
  const ordem = ["9.1", "9.2", "forca"];
  // encerrado com 9.1: +2 R, -1 R; com forca: +0,5 R; sem setup: -1 R; um 9.2 sem stop; um aberto
  const trades = [
    trade([compra(100, 20), venda(100, 22)], 19, { categoriaSetup: "9.1" }),
    trade([compra(100, 20), venda(100, 19)], 19, { categoriaSetup: "9.1" }),
    trade([compra(100, 20), venda(100, 20.5)], 19, { categoriaSetup: "forca" }),
    trade([compra(100, 20), venda(100, 19)], 19, { categoriaSetup: null }),
    trade([compra(100, 20), venda(100, 21)], null, { categoriaSetup: "9.2" }),
    trade([compra(100, 20)], 19, { categoriaSetup: "9.1" }),
  ];

  it("so encerrados, na ordem fixa, com os sem setup por ultimo", () => {
    const linhas = estatisticaPorSetup(trades, ordem);
    assert.deepEqual(
      linhas.map((l) => l.categoria),
      ["9.1", "9.2", "forca", null],
    );
    const nove1 = linhas[0];
    assert.equal(nove1.encerrados, 2);
    assert.equal(nove1.comR, 2);
    assert.equal(nove1.acerto, 0.5);
    assert.equal(nove1.mediaR, 0.5);
    assert.equal(nove1.somaR, 1);
  });

  it("encerrado sem stop conta nos trades mas nao no R", () => {
    const nove2 = estatisticaPorSetup(trades, ordem)[1];
    assert.equal(nove2.encerrados, 1);
    assert.equal(nove2.comR, 0);
    assert.equal(nove2.acerto, null);
    assert.equal(nove2.mediaR, null);
    assert.equal(nove2.somaR, 0);
  });

  it("a ordem nao depende do resultado", () => {
    const linhas = estatisticaPorSetup([...trades].reverse(), ordem);
    assert.deepEqual(
      linhas.map((l) => l.categoria),
      ["9.1", "9.2", "forca", null],
    );
  });

  it("setup sem trade encerrado nao aparece; sem trades, lista vazia", () => {
    assert.deepEqual(estatisticaPorSetup([trades[5]], ordem), []);
    assert.deepEqual(estatisticaPorSetup([], ordem), []);
  });
});

describe("validarCamposDoDiario", () => {
  const v = (e) => validarCamposDoDiario(e, CATEGORIAS_DE_SETUP);

  it("tudo opcional: vazio vale sem setup e sem stop", () => {
    const vazio = { setupId: null, categoriaSetup: null, stop: null };
    assert.deepEqual(v({}), vazio);
    assert.deepEqual(v({ setupId: null, categoriaSetup: "", stop: "" }), vazio);
  });

  it("aceita setup, categoria e stop validos", () => {
    assert.deepEqual(v({ setupId: 12, categoriaSetup: "9.4", stop: 18.75 }), {
      setupId: 12,
      categoriaSetup: "9.4",
      stop: 18.75,
    });
    assert.equal(v({ stop: "19.5" }).stop, 19.5);
  });

  it("recusa categoria desconhecida", () => {
    assert.throws(() => v({ categoriaSetup: "xpto" }), DiarioInvalido);
    assert.throws(() => v({ categoriaSetup: 5 }), DiarioInvalido);
  });

  it("recusa stop zero, negativo, texto ou com tres casas", () => {
    for (const stop of [0, -1, "abc", 1.234, 1e12]) {
      assert.throws(() => v({ stop }), DiarioInvalido);
    }
  });

  it("recusa setupId que nao e inteiro positivo", () => {
    for (const setupId of [0, -3, 1.5, "x"]) {
      assert.throws(() => v({ setupId }), DiarioInvalido);
    }
  });
});
