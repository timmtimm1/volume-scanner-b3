// Posicao de um trade real: aplicacao das operacoes e marcacao a mercado.
// Espelha `src/scanner/trades.py` -- o exemplo de referencia e o mesmo dos
// dois lados. `npm test`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  OperacaoInvalida,
  aplicarOperacoes,
  marcarAMercado,
  marcarAgora,
  validarCampos,
} from "./posicao.ts";

// compra 100x38,20 (01/09) -> compra 50x37,60 (03/09) -> venda 80x39,90 (10/09)
const REFERENCIA = [
  { id: 1, tipo: "compra", data: "2025-09-01", quantidade: 100, preco: 38.2 },
  { id: 2, tipo: "compra", data: "2025-09-03", quantidade: 50, preco: 37.6 },
  { id: 3, tipo: "venda", data: "2025-09-10", quantidade: 80, preco: 39.9 },
];

describe("aplicarOperacoes", () => {
  it("exemplo de referencia: compra, compra, venda parcial", () => {
    const r = aplicarOperacoes(REFERENCIA);
    assert.deepEqual(
      r.ordenadas.map((o) => o.id),
      [1, 2, 3],
    );
    assert.deepEqual(r.estados, [
      { quantidade: 100, precoMedio: 38.2, custoComprado: 3820, realizado: 0 },
      { quantidade: 150, precoMedio: 38, custoComprado: 5700, realizado: 0 },
      { quantidade: 70, precoMedio: 38, custoComprado: 5700, realizado: 152 },
    ]);
    assert.equal(r.abertoEm, "2025-09-01");
    assert.equal(r.encerradoEm, null);
  });

  it("ordena por (data, id), nao pela ordem de entrada", () => {
    const embaralhado = [REFERENCIA[2], REFERENCIA[0], REFERENCIA[1]];
    const r = aplicarOperacoes(embaralhado);
    assert.deepEqual(
      r.ordenadas.map((o) => o.id),
      [1, 2, 3],
    );
  });

  it("empate de data desempata por id", () => {
    const ops = [
      { id: 5, tipo: "compra", data: "2025-09-01", quantidade: 100, preco: 10 },
      { id: 3, tipo: "compra", data: "2025-09-01", quantidade: 10, preco: 10 },
    ];
    const r = aplicarOperacoes(ops);
    assert.deepEqual(
      r.ordenadas.map((o) => o.id),
      [3, 5],
    );
  });

  it("venda que zera a posicao encerra o trade", () => {
    const r = aplicarOperacoes([
      { id: 1, tipo: "compra", data: "2025-09-01", quantidade: 100, preco: 10 },
      { id: 2, tipo: "venda", data: "2025-09-05", quantidade: 100, preco: 12 },
    ]);
    assert.equal(r.encerradoEm, "2025-09-05");
    assert.deepEqual(r.estados.at(-1), {
      quantidade: 0,
      precoMedio: 10,
      custoComprado: 1000,
      realizado: 200,
    });
  });

  it("lista vazia lanca OperacaoInvalida", () => {
    assert.throws(() => aplicarOperacoes([]), OperacaoInvalida);
  });

  it("primeira operacao tem de ser compra", () => {
    assert.throws(
      () =>
        aplicarOperacoes([
          { id: 1, tipo: "venda", data: "2025-09-01", quantidade: 10, preco: 10 },
        ]),
      OperacaoInvalida,
    );
  });

  it("venda maior que a posicao lanca erro com quantidade e data", () => {
    assert.throws(
      () =>
        aplicarOperacoes([
          { id: 1, tipo: "compra", data: "2025-09-01", quantidade: 10, preco: 10 },
          { id: 2, tipo: "venda", data: "2025-09-05", quantidade: 20, preco: 12 },
        ]),
      (erro) =>
        erro instanceof OperacaoInvalida &&
        erro.message.includes("20") &&
        erro.message.includes("10") &&
        erro.message.includes("2025-09-05"),
    );
  });

  it("compra depois do trade encerrado lanca erro (abriria outro trade)", () => {
    assert.throws(
      () =>
        aplicarOperacoes([
          { id: 1, tipo: "compra", data: "2025-09-01", quantidade: 10, preco: 10 },
          { id: 2, tipo: "venda", data: "2025-09-05", quantidade: 10, preco: 12 },
          { id: 3, tipo: "compra", data: "2025-09-10", quantidade: 5, preco: 11 },
        ]),
      (erro) => erro instanceof OperacaoInvalida && /outro trade/.test(erro.message),
    );
  });

  it("qualquer operacao depois do encerramento lanca, nao so compra", () => {
    assert.throws(
      () =>
        aplicarOperacoes([
          { id: 1, tipo: "compra", data: "2025-09-01", quantidade: 10, preco: 10 },
          { id: 2, tipo: "venda", data: "2025-09-05", quantidade: 10, preco: 12 },
          { id: 3, tipo: "venda", data: "2025-09-10", quantidade: 5, preco: 11 },
        ]),
      OperacaoInvalida,
    );
  });
});

describe("validarCampos", () => {
  it("normaliza uma entrada valida", () => {
    assert.deepEqual(
      validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: "100", preco: "38.2" }),
      { tipo: "compra", data: "2025-09-01", quantidade: 100, preco: 38.2 },
    );
  });

  it("recusa tipo fora de compra/venda", () => {
    assert.throws(
      () => validarCampos({ tipo: "swap", data: "2025-09-01", quantidade: 1, preco: 1 }),
      OperacaoInvalida,
    );
  });

  it("recusa data fora do formato", () => {
    assert.throws(
      () =>
        validarCampos({ tipo: "compra", data: "01/09/2025", quantidade: 1, preco: 1 }),
      OperacaoInvalida,
    );
  });

  it("recusa data invalida no calendario", () => {
    assert.throws(
      () => validarCampos({ tipo: "compra", data: "2026-02-30", quantidade: 1, preco: 1 }),
      OperacaoInvalida,
    );
  });

  it("recusa quantidade nao inteira ou nao positiva", () => {
    assert.throws(
      () => validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: 1.5, preco: 1 }),
      OperacaoInvalida,
    );
    assert.throws(
      () => validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: 0, preco: 1 }),
      OperacaoInvalida,
    );
  });

  it("recusa preco nao finito, nao positivo ou com mais de 2 casas", () => {
    assert.throws(
      () => validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: 1, preco: 0 }),
      OperacaoInvalida,
    );
    assert.throws(
      () =>
        validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: 1, preco: Infinity }),
      OperacaoInvalida,
    );
    assert.throws(
      () =>
        validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: 1, preco: 10.123 }),
      OperacaoInvalida,
    );
  });
});

describe("marcarAMercado", () => {
  const operacoesDaReferencia = () => {
    const r = aplicarOperacoes(REFERENCIA);
    return r.ordenadas.map((o, i) => ({ data: o.data, estado: r.estados[i] }));
  };

  it("resultado com o fechamento do dia (exemplo de referencia)", () => {
    const snaps = marcarAMercado({
      operacoes: operacoesDaReferencia(),
      pregoes: ["2025-09-10"],
      fechamentos: [{ data: "2025-09-10", close: 39.1 }],
      desde: "2025-09-01",
      ate: "2025-09-10",
    });
    assert.equal(snaps.length, 1);
    assert.deepEqual(snaps[0], {
      data: "2025-09-10",
      quantidade: 70,
      precoMedio: 38,
      custoComprado: 5700,
      realizado: 152,
      fechamento: 39.1,
      valorPosicao: 2737,
      resultado: 229,
      semNegocio: false,
    });
  });

  it("dia sem negocio usa o ultimo close (ffill) e marca semNegocio", () => {
    const snaps = marcarAMercado({
      operacoes: operacoesDaReferencia(),
      pregoes: ["2025-09-10", "2025-09-11", "2025-09-12"],
      fechamentos: [
        { data: "2025-09-10", close: 39.1 },
        // sem close em 09-11: feriado ou papel sem negocio
        { data: "2025-09-12", close: 40 },
      ],
      desde: "2025-09-10",
      ate: "2025-09-12",
    });
    assert.equal(snaps.length, 3);
    assert.equal(snaps[1].data, "2025-09-11");
    assert.equal(snaps[1].fechamento, 39.1);
    assert.equal(snaps[1].semNegocio, true);
    assert.equal(snaps[0].semNegocio, false);
    assert.equal(snaps[2].semNegocio, false);
  });

  it("pregao antes da primeira operacao nao gera snapshot", () => {
    const snaps = marcarAMercado({
      operacoes: operacoesDaReferencia(),
      pregoes: ["2025-08-29", "2025-09-01"],
      fechamentos: [
        { data: "2025-08-29", close: 37 },
        { data: "2025-09-01", close: 38.5 },
      ],
      desde: "2025-08-29",
      ate: "2025-09-01",
    });
    assert.equal(snaps.length, 1);
    assert.equal(snaps[0].data, "2025-09-01");
  });

  it("respeita o intervalo desde/ate mesmo com mais pregoes disponiveis", () => {
    const snaps = marcarAMercado({
      operacoes: operacoesDaReferencia(),
      pregoes: ["2025-09-01", "2025-09-03", "2025-09-10", "2025-09-11"],
      fechamentos: [
        { data: "2025-09-01", close: 38.2 },
        { data: "2025-09-03", close: 37.6 },
        { data: "2025-09-10", close: 39.9 },
        { data: "2025-09-11", close: 40 },
      ],
      desde: "2025-09-03",
      ate: "2025-09-10",
    });
    assert.deepEqual(
      snaps.map((s) => s.data),
      ["2025-09-03", "2025-09-10"],
    );
  });
});

describe("marcarAgora", () => {
  // Estado final do exemplo de referencia: 70 acoes, PM 38, custo 5700, realizado 152.
  const abertoParcial = { quantidade: 70, precoMedio: 38, custoComprado: 5700, realizado: 152 };
  // Estado de um trade encerrado (venda de 100x12 sobre compra de 100x10).
  const encerrado = { quantidade: 0, precoMedio: 10, custoComprado: 1000, realizado: 200 };

  it("com preco: realizado mais o nao realizado, % sobre o custo, valor da posicao", () => {
    const m = marcarAgora(abertoParcial, 39.9);
    assert.equal(m.resultado, 285); // 152 + 70 * (39.9 - 38)
    assert.equal(m.resultadoPct, 285 / 5700);
    assert.equal(m.valor, 2793); // 70 * 39.9
  });

  it("sem preco: resultado e so o realizado, sem valor de posicao", () => {
    const m = marcarAgora(abertoParcial, null);
    assert.equal(m.resultado, 152);
    assert.equal(m.resultadoPct, 152 / 5700);
    assert.equal(m.valor, null);
  });

  it("trade encerrado: resultado e o realizado mesmo com preco informado, sem valor", () => {
    const m = marcarAgora(encerrado, 12.5);
    assert.equal(m.resultado, 200);
    assert.equal(m.resultadoPct, 200 / 1000);
    assert.equal(m.valor, null); // quantidade zerada: nao ha posicao para valer algo
  });
});
