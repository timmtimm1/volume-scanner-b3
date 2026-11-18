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
  ordenarTrades,
} from "./diario.ts";
import { aplicarOperacoes, marcarAgora } from "./posicao.ts";
import { regrasDoDiario } from "./mercado.ts";

const B3 = regrasDoDiario("b3");

const compra = (quantidade, preco) => ({ tipo: "compra", quantidade, preco });
const venda = (quantidade, preco) => ({ tipo: "venda", quantidade, preco });

/** Monta o trade como o site o devolve: estado depois da ultima operacao. */
function trade(operacoes, stop, extra = {}) {
  const ord = operacoes.map((o, i) => ({ id: i + 1, data: `2026-09-${10 + i}`, ...o }));
  const { estados, encerradoEm } = aplicarOperacoes(ord, B3);
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

  it("em cripto o stop aceita as dez casas do preco", () => {
    const cripto = (e) => validarCamposDoDiario(e, CATEGORIAS_DE_SETUP, 10);
    assert.equal(cripto({ stop: "0.0000041987" }).stop, 0.0000041987);
    assert.throws(() => cripto({ stop: 0.00000419871 }), /10 casas/);
    // e a B3 segue com duas
    assert.throws(() => v({ stop: 0.0000041987 }), /2 casas/);
  });

  it("recusa setupId que nao e inteiro positivo", () => {
    for (const setupId of [0, -3, 1.5, "x"]) {
      assert.throws(() => v({ setupId }), DiarioInvalido);
    }
  });
});

describe("ordenarTrades", () => {
  it("abertos primeiro, depois o mais recente, empate pelo id maior", () => {
    const t = [
      { id: 1, abertoEm: "2026-09-01", encerradoEm: "2026-09-10", mercado: "b3" },
      { id: 1, abertoEm: "2026-11-17", encerradoEm: null, mercado: "cripto" },
      { id: 4, abertoEm: "2026-10-01", encerradoEm: null, mercado: "b3" },
      { id: 2, abertoEm: "2026-11-01", encerradoEm: "2026-11-15", mercado: "cripto" },
      { id: 3, abertoEm: "2026-11-02", encerradoEm: "2026-11-15", mercado: "b3" },
    ];
    assert.deepEqual(
      ordenarTrades(t).map((x) => `${x.mercado}${x.id}`),
      ["cripto1", "b34", "b33", "cripto2", "b31"],
    );
  });
});


describe("R na venda a descoberto (cripto)", () => {
  const CRIPTO = regrasDoDiario("cripto");
  /** Como `trade`, com as regras de cripto (a venda abre o trade vendido). */
  function vendido(operacoes, stop) {
    const ord = operacoes.map((o, i) => ({ id: i + 1, data: `2026-11-${10 + i}`, ...o }));
    const { estados, lado } = aplicarOperacoes(ord, CRIPTO);
    return { stop, operacoes, lado, ...estados.at(-1) };
  }

  it("o risco e o stop ACIMA da venda: soma de quantidade x (stop - preco) das vendas", () => {
    // vende 0,5 a 600 com stop em 620: arrisca 0,5 x 20 = 10
    assert.equal(riscoEmReais(vendido([venda(0.5, 600)], 620)), 10);
    // vender mais aumenta o risco; a recompra nao entra
    assert.equal(riscoEmReais(vendido([venda(0.5, 600), venda(0.25, 610), compra(0.3, 590)], 620)), 12.5);
  });

  it("sem lado na entrada, vale a primeira operacao", () => {
    assert.equal(riscoEmReais({ stop: 620, operacoes: [venda(0.5, 600)] }), 10);
  });

  it("stop abaixo da venda nao tem R", () => {
    assert.equal(riscoEmReais(vendido([venda(0.5, 600)], 590)), null);
  });

  it("o R anda com o preco ao contrario: caiu, ganhou", () => {
    const t = vendido([venda(0.5, 600)], 620);
    // PM 599,70; a 580: -0,5 x (580 - 599,70) = 9,85 sobre risco 10
    assert.equal(resultadoEmRDoTrade(t, 580), 0.985);
    assert.ok(resultadoEmRDoTrade(t, 620) < -1, "no stop, um pouco pior que -1 R pela taxa");
  });
});
