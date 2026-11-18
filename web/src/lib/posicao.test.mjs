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
import { regrasDoDiario } from "./mercado.ts";

const B3 = regrasDoDiario("b3");

// compra 100x38,20 (01/09) -> compra 50x37,60 (03/09) -> venda 80x39,90 (10/09)
const REFERENCIA = [
  { id: 1, tipo: "compra", data: "2025-09-01", quantidade: 100, preco: 38.2 },
  { id: 2, tipo: "compra", data: "2025-09-03", quantidade: 50, preco: 37.6 },
  { id: 3, tipo: "venda", data: "2025-09-10", quantidade: 80, preco: 39.9 },
];

describe("aplicarOperacoes", () => {
  it("exemplo de referencia: compra, compra, venda parcial", () => {
    const r = aplicarOperacoes(REFERENCIA, B3);
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
    const r = aplicarOperacoes(embaralhado, B3);
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
    const r = aplicarOperacoes(ops, B3);
    assert.deepEqual(
      r.ordenadas.map((o) => o.id),
      [3, 5],
    );
  });

  it("venda que zera a posicao encerra o trade", () => {
    const r = aplicarOperacoes([
      { id: 1, tipo: "compra", data: "2025-09-01", quantidade: 100, preco: 10 },
      { id: 2, tipo: "venda", data: "2025-09-05", quantidade: 100, preco: 12 },
    ], B3);
    assert.equal(r.encerradoEm, "2025-09-05");
    assert.deepEqual(r.estados.at(-1), {
      quantidade: 0,
      precoMedio: 10,
      custoComprado: 1000,
      realizado: 200,
    });
  });

  it("lista vazia lanca OperacaoInvalida", () => {
    assert.throws(() => aplicarOperacoes([], B3), OperacaoInvalida);
  });

  it("primeira operacao tem de ser compra", () => {
    assert.throws(
      () =>
        aplicarOperacoes([
          { id: 1, tipo: "venda", data: "2025-09-01", quantidade: 10, preco: 10 },
        ], B3),
      OperacaoInvalida,
    );
  });

  it("venda maior que a posicao lanca erro com quantidade e data", () => {
    assert.throws(
      () =>
        aplicarOperacoes([
          { id: 1, tipo: "compra", data: "2025-09-01", quantidade: 10, preco: 10 },
          { id: 2, tipo: "venda", data: "2025-09-05", quantidade: 20, preco: 12 },
        ], B3),
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
        ], B3),
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
        ], B3),
      OperacaoInvalida,
    );
  });
});

describe("validarCampos", () => {
  it("normaliza uma entrada valida", () => {
    assert.deepEqual(
      validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: "100", preco: "38.2" }, B3),
      { tipo: "compra", data: "2025-09-01", quantidade: 100, preco: 38.2 },
    );
  });

  it("recusa tipo fora de compra/venda", () => {
    assert.throws(
      () => validarCampos({ tipo: "swap", data: "2025-09-01", quantidade: 1, preco: 1 }, B3),
      OperacaoInvalida,
    );
  });

  it("recusa data fora do formato", () => {
    assert.throws(
      () =>
        validarCampos({ tipo: "compra", data: "01/09/2025", quantidade: 1, preco: 1 }, B3),
      OperacaoInvalida,
    );
  });

  it("recusa data invalida no calendario", () => {
    assert.throws(
      () => validarCampos({ tipo: "compra", data: "2026-02-30", quantidade: 1, preco: 1 }, B3),
      OperacaoInvalida,
    );
  });

  it("recusa quantidade nao inteira ou nao positiva", () => {
    assert.throws(
      () => validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: 1.5, preco: 1 }, B3),
      OperacaoInvalida,
    );
    assert.throws(
      () => validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: 0, preco: 1 }, B3),
      OperacaoInvalida,
    );
  });

  it("recusa preco nao finito, nao positivo ou com mais de 2 casas", () => {
    assert.throws(
      () => validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: 1, preco: 0 }, B3),
      OperacaoInvalida,
    );
    assert.throws(
      () =>
        validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: 1, preco: Infinity }, B3),
      OperacaoInvalida,
    );
    assert.throws(
      () =>
        validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: 1, preco: 10.123 }, B3),
      OperacaoInvalida,
    );
  });
});

describe("marcarAMercado", () => {
  const operacoesDaReferencia = () => {
    const r = aplicarOperacoes(REFERENCIA, B3);
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

describe("diario em cripto: taxa da Binance saindo da moeda", () => {
  const CRIPTO = regrasDoDiario("cripto");
  const PM = 994.5 / 0.0152847; // custo dividido pelas moedas que ficaram

  it("compra de 0,0153 BTC deixa 0,0152847 na posicao, e o PM inclui a taxa", () => {
    const r = aplicarOperacoes(
      [{ id: 1, tipo: "compra", data: "2026-11-17", quantidade: 0.0153, preco: 65000 }],
      CRIPTO,
    );
    const e = r.estados[0];
    assert.equal(e.quantidade, 0.0152847);
    assert.equal(e.custoComprado, 994.5); // 0,0153 x 65.000: o que saiu da conta
    assert.ok(Math.abs(e.precoMedio - PM) < 1e-9);
    assert.equal(r.encerradoEm, null);
  });

  it("vender o saldo todo fecha o trade, com a taxa da venda saindo dos dolares", () => {
    const r = aplicarOperacoes(
      [
        { id: 1, tipo: "compra", data: "2026-11-17", quantidade: 0.0153, preco: 65000 },
        { id: 2, tipo: "venda", data: "2026-11-19", quantidade: 0.0152847, preco: 66000 },
      ],
      CRIPTO,
    );
    // 0,0152847 x (66.000 x 0,999 - PM) = 1.007,78 recebidos - 994,50 pagos
    assert.equal(r.estados[1].realizado, 13.28);
    assert.equal(r.estados[1].quantidade, 0);
    assert.equal(r.encerradoEm, "2026-11-19");
  });

  it("vendas parciais: o PM nao muda e o resto fecha exatamente", () => {
    const r = aplicarOperacoes(
      [
        { id: 1, tipo: "compra", data: "2026-11-17", quantidade: 0.0153, preco: 65000 },
        { id: 2, tipo: "venda", data: "2026-11-18", quantidade: 0.01, preco: 66000 },
        { id: 3, tipo: "venda", data: "2026-11-19", quantidade: 0.0052847, preco: 64000 },
      ],
      CRIPTO,
    );
    assert.equal(r.estados[1].quantidade, 0.0052847);
    assert.equal(r.estados[1].precoMedio, r.estados[0].precoMedio);
    assert.equal(r.estados[1].realizado, 8.69);
    assert.equal(r.estados[2].realizado, 2.72); // 8,69 - 5,97
    assert.equal(r.encerradoEm, "2026-11-19");
  });

  it("comprar e vender no mesmo preco perde as duas taxas", () => {
    const r = aplicarOperacoes(
      [
        { id: 1, tipo: "compra", data: "2026-11-17", quantidade: 0.0153, preco: 65000 },
        { id: 2, tipo: "venda", data: "2026-11-17", quantidade: 0.0152847, preco: 65000 },
      ],
      CRIPTO,
    );
    assert.equal(r.estados[1].realizado, -1.99); // ~0,2% de 994,50
  });

  it("vender mais do que o saldo depois da taxa e erro", () => {
    assert.throws(
      () =>
        aplicarOperacoes(
          [
            { id: 1, tipo: "compra", data: "2026-11-17", quantidade: 0.0153, preco: 65000 },
            { id: 2, tipo: "venda", data: "2026-11-18", quantidade: 0.0153, preco: 66000 },
          ],
          CRIPTO,
        ),
      (erro) => erro instanceof OperacaoInvalida && erro.message.includes("0.0152847"),
    );
  });

  it("moeda de preco minusculo e quantidade grande nao perde a conta", () => {
    const r = aplicarOperacoes(
      [
        { id: 1, tipo: "compra", data: "2026-11-17", quantidade: 8_000_000, preco: 0.0000125 },
        { id: 2, tipo: "venda", data: "2026-11-18", quantidade: 7_992_000, preco: 0.000015 },
      ],
      CRIPTO,
    );
    assert.equal(r.estados[0].quantidade, 7_992_000);
    assert.equal(r.estados[0].custoComprado, 100);
    // 7.992.000 x 0,000015 x 0,999 = 119,76 recebidos - 100 pagos
    assert.equal(r.estados[1].realizado, 19.76);
    assert.equal(r.encerradoEm, "2026-11-18");
  });

  it("aceita quantidade com ate 8 casas e preco com ate 10", () => {
    const op = validarCampos(
      { tipo: "compra", data: "2026-11-17", quantidade: "0.00076923", preco: "0.0000042123" },
      CRIPTO,
    );
    assert.equal(op.quantidade, 0.00076923);
    assert.equal(op.preco, 0.0000042123);
    assert.throws(
      () => validarCampos({ tipo: "compra", data: "2026-11-17", quantidade: 0.123456789, preco: 1 }, CRIPTO),
      /8 casas/,
    );
    assert.throws(
      () => validarCampos({ tipo: "compra", data: "2026-11-17", quantidade: 1, preco: 0.00000421234 }, CRIPTO),
      /10 casas/,
    );
  });

  it("na B3 continua so acao inteira, centavo e PM de seis casas", () => {
    assert.throws(
      () => validarCampos({ tipo: "compra", data: "2025-09-01", quantidade: 0.5, preco: 10 }, B3),
      /inteiro/,
    );
    const r = aplicarOperacoes(
      [
        { id: 1, tipo: "compra", data: "2025-09-01", quantidade: 3, preco: 10 },
        { id: 2, tipo: "compra", data: "2025-09-02", quantidade: 4, preco: 10.01 },
      ],
      B3,
    );
    assert.equal(r.estados[1].precoMedio, 10.005714); // 70,04 / 7, em seis casas
    assert.equal(r.estados[1].quantidade, 7);
  });
});

describe("venda a descoberto (cripto): taxa dos futuros em dolar", () => {
  const CRIPTO = regrasDoDiario("cripto");
  const VENDA = { id: 1, tipo: "venda", data: "2026-11-17", quantidade: 0.5, preco: 600 };

  it("a venda abre o trade vendido: quantidade negativa, PM com a taxa descontada", () => {
    const r = aplicarOperacoes([VENDA], CRIPTO);
    assert.equal(r.lado, "venda");
    // 600 x (1 - 0,0005) = 599,70; custo = o valor vendido, base do percentual
    assert.deepEqual(r.estados[0], { quantidade: -0.5, precoMedio: 599.7, custoComprado: 300, realizado: 0 });
    assert.equal(r.encerradoEm, null);
  });

  it("a recompra realiza o que o preco caiu, menos a taxa, e fecha o trade", () => {
    const r = aplicarOperacoes(
      [VENDA, { id: 2, tipo: "compra", data: "2026-11-19", quantidade: 0.5, preco: 550 }],
      CRIPTO,
    );
    // 0,5 x (599,70 - 550 x 1,0005) = 299,85 recebidos - 275,1375 pagos = 24,7125
    assert.equal(r.estados[1].realizado, 24.71);
    assert.equal(r.estados[1].quantidade, 0);
    assert.ok(!Object.is(r.estados[1].quantidade, -0), "zerado e 0, nao -0");
    assert.equal(r.encerradoEm, "2026-11-19");
  });

  it("vender mais muda o PM; recompras parciais realizam aos poucos", () => {
    const r = aplicarOperacoes(
      [
        VENDA,
        { id: 2, tipo: "venda", data: "2026-11-18", quantidade: 0.25, preco: 630 },
        { id: 3, tipo: "compra", data: "2026-11-19", quantidade: 0.3, preco: 590 },
        { id: 4, tipo: "compra", data: "2026-11-20", quantidade: 0.45, preco: 640 },
      ],
      CRIPTO,
    );
    // PM = (0,5 x 599,70 + 0,25 x 630 x 0,9995) / 0,75 = 609,695
    assert.deepEqual(r.estados[1], { quantidade: -0.75, precoMedio: 609.695, custoComprado: 457.5, realizado: 0 });
    // 0,3 x (609,695 - 590 x 1,0005) = 5,82
    assert.deepEqual(r.estados[2], { quantidade: -0.45, precoMedio: 609.695, custoComprado: 457.5, realizado: 5.82 });
    // + 0,45 x (609,695 - 640 x 1,0005) = 5,82 - 13,78125: o preco subiu, perdeu
    assert.equal(r.estados[3].realizado, -7.96);
    assert.equal(r.encerradoEm, "2026-11-20");
  });

  it("recomprar mais do que deve e erro", () => {
    assert.throws(
      () =>
        aplicarOperacoes(
          [VENDA, { id: 2, tipo: "compra", data: "2026-11-19", quantidade: 0.6, preco: 550 }],
          CRIPTO,
        ),
      /recompra de 0.6 maior que a posicao vendida de 0.5/,
    );
  });

  it("depois de zerado, outra venda abre outro trade", () => {
    assert.throws(
      () =>
        aplicarOperacoes(
          [
            VENDA,
            { id: 2, tipo: "compra", data: "2026-11-19", quantidade: 0.5, preco: 550 },
            { id: 3, tipo: "venda", data: "2026-11-20", quantidade: 0.1, preco: 560 },
          ],
          CRIPTO,
        ),
      /trade ja encerrado em 2026-11-19/,
    );
  });

  it("na B3 o trade continua tendo de abrir com compra", () => {
    assert.throws(
      () => aplicarOperacoes([{ ...VENDA, quantidade: 100, preco: 38.2 }], B3),
      /a primeira operacao de um trade tem de ser uma compra/,
    );
  });

  it("regras sem o campo `vendido` tambem nao deixam", () => {
    const semCampo = { ...CRIPTO };
    delete semCampo.vendido;
    assert.throws(() => aplicarOperacoes([VENDA], semCampo), /tem de ser uma compra/);
  });

  it("a mesma formula marca o vendido: o preco caiu, o resultado sobe", () => {
    const estado = { quantidade: -0.5, precoMedio: 599.7, custoComprado: 300, realizado: 0 };
    const m = marcarAgora(estado, 580);
    // -0,5 x (580 - 599,70) = 9,85
    assert.equal(m.resultado, 9.85);
    assert.equal(m.resultadoPct, 9.85 / 300);
    assert.equal(m.valor, -290);
    const [s] = marcarAMercado({
      operacoes: [{ data: "2026-11-17", estado }],
      pregoes: ["2026-11-18"],
      fechamentos: [{ data: "2026-11-18", close: 620 }],
      desde: "2026-11-18",
      ate: "2026-11-18",
    });
    // subiu para 620: -0,5 x (620 - 599,70) = -10,15
    assert.equal(s.resultado, -10.15);
    assert.equal(s.valorPosicao, -310);
  });
});
