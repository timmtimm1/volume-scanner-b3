// O que muda de um mercado para o outro na tela: passo de preco, casas e textos.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { calcularLote, calcularLoteFracionado, calcularLoteFracionadoVenda } from "./lote.ts";
import { CATEGORIAS_DO_ESTUDO } from "./config.ts";
import { TICKER } from "./ticker.ts";
import {
  arredondarPreco,
  diaDoMercado,
  linkDoTrade,
  precoParaCampo,
  quantidadeParaCampo,
  regrasDoDiario,
  tickerValido,
  casasDoPreco,
  gatilhoNoMercado,
  linkDaFichaNoMercado,
  mercadoDe,
  passoDoPreco,
  preco,
  quantidade,
  stopNoMercado,
  textos,
  valor,
  valorComSinal,
} from "./mercado.ts";

describe("mercado da tela", () => {
  it("qualquer coisa que nao seja 'cripto' e a B3", () => {
    assert.equal(mercadoDe("cripto"), "cripto");
    assert.equal(mercadoDe(null), "b3");
    assert.equal(mercadoDe("crypto"), "b3");
  });

  it("na B3 o passo e sempre 1 centavo e o preco tem duas casas", () => {
    assert.equal(passoDoPreco("b3", 34.5), 0.01);
    assert.equal(gatilhoNoMercado("b3", 34.5), 34.51);
    assert.equal(stopNoMercado("b3", 30), 29.99);
    assert.equal(preco("b3", 34.5), "R$ 34,50");
  });

  it("em cripto o passo e a quinta casa significativa, a mesma conta do pipeline", () => {
    assert.equal(passoDoPreco("cripto", 65351.05), 1);
    assert.ok(Math.abs(passoDoPreco("cripto", 0.52) - 0.00001) < 1e-15);
    assert.ok(Math.abs(passoDoPreco("cripto", 0.000004) - 1e-10) < 1e-20);
    for (const p of [65351.05, 3120, 9.99, 10, 0.52, 0.000004]) {
      const fracao = passoDoPreco("cripto", p) / p;
      assert.ok(fracao > 0.00001 && fracao <= 0.0001, `passo de ${p}`);
    }
  });

  it("gatilho e stop de cripto ficam um passo alem da maxima e da minima, sem ruido de ponto flutuante", () => {
    assert.equal(gatilhoNoMercado("cripto", 0.7124), 0.71241);
    assert.equal(stopNoMercado("cripto", 0.4784), 0.47839);
    assert.equal(gatilhoNoMercado("cripto", 65000), 65001);
    assert.equal(stopNoMercado("cripto", 0.00000412), 0.0000041199);
    assert.ok(gatilhoNoMercado("cripto", 0.057036) > 0.057036);
  });

  it("um preco minusculo nao vira zero na tela", () => {
    assert.equal(casasDoPreco(65351.05), 0);
    assert.equal(casasDoPreco(312.4), 2);
    assert.equal(casasDoPreco(0.52), 5);
    assert.equal(casasDoPreco(0.00000412), 10);
    assert.equal(preco("cripto", 65351.05), "US$ 65.351");
    assert.equal(preco("cripto", 0.71241), "US$ 0,71241");
    assert.equal(preco("cripto", 0.00000412), "US$ 0,0000041200");
    assert.equal(preco("cripto", null), "—");
    assert.equal(arredondarPreco("cripto", 0.1 + 0.2), 0.3);
  });

  it("valor em dinheiro e tamanho da posicao falam a lingua do mercado", () => {
    assert.equal(valor("b3", 1500, 0), "R$ 1.500");
    assert.equal(valor("cripto", 1500, 0), "US$ 1.500");
    assert.equal(valorComSinal("cripto", -12.5), "−US$ 12,50");
    assert.equal(quantidade("b3", 1, "PETR4"), "1 ação");
    assert.equal(quantidade("b3", 150, "PETR4"), "150 ações");
    assert.equal(quantidade("cripto", 0.0153, "BTC"), "0,0153 BTC");
    assert.equal(quantidade("cripto", 1403.5, "ASTER"), "1.404 ASTER");
  });

  it("a nota do semaforo vem do periodo de conferencia de cada mercado", () => {
    assert.equal(textos("b3").periodoDaNota, "2016-2026");
    assert.equal(textos("cripto").periodoDaNota, "2022-2026");
    assert.deepEqual(textos("cripto").dia, ["dia", "dias"]);
  });

  it("a ficha de cripto mora em /cripto", () => {
    assert.equal(linkDaFichaNoMercado("b3", "PETR4", "2026-11-13"), "/papel/PETR4?foco=2026-11-13");
    assert.equal(linkDaFichaNoMercado("cripto", "BTC", "2026-11-15"), "/cripto/BTC?foco=2026-11-15");
  });
});

describe("lote fracionado (cripto)", () => {
  const perfil = { capital: 1000, riscoPct: 1 };

  it("arrisca exatamente o risco do perfil, com fracao da moeda", () => {
    // risco de US$ 10; US$ 2.000 entre a entrada e o stop -> 0,005 BTC
    const lote = calcularLoteFracionado({ ...perfil, entrada: 65000, stop: 63000 });
    assert.equal(lote.quantidade, 0.005);
    assert.equal(lote.perdaMaxima, 10);
    assert.equal(lote.valorPosicao, 325);
    assert.equal(lote.limitadoPeloCapital, false);
    // a conta da B3, de acoes inteiras, diria que nao cabe nenhuma
    assert.equal(calcularLote({ ...perfil, entrada: 65000, stop: 63000 }).quantidade, 0);
  });

  it("moeda de fracao de centavo nao perde o risco no arredondamento", () => {
    const lote = calcularLoteFracionado({ ...perfil, entrada: 0.00000425, stop: 0.00000401 });
    assert.ok(Math.abs(lote.perdaMaxima - 10) < 0.01);
    assert.ok(lote.quantidade > 41_000_000 && lote.quantidade < 42_000_000);
  });

  it("stop muito curto: o limite passa a ser o capital, nunca alavanca", () => {
    const lote = calcularLoteFracionado({ ...perfil, entrada: 100, stop: 99.9 });
    assert.equal(lote.quantidade, 10);
    assert.equal(lote.valorPosicao, 1000);
    assert.equal(lote.limitadoPeloCapital, true);
    assert.equal(lote.perdaMaxima, 1);
  });

  it("posicao abaixo do minimo da corretora (US$ 5) nao cabe", () => {
    const lote = calcularLoteFracionado({ capital: 20, riscoPct: 1, entrada: 100, stop: 50 });
    assert.equal(lote.quantidade, 0);
  });

  it("dado faltando ou stop acima da entrada: sem lote", () => {
    assert.equal(calcularLoteFracionado({ ...perfil, entrada: 10, stop: 10 }).quantidade, 0);
    assert.equal(calcularLoteFracionado({ ...perfil, entrada: 10, stop: 11 }).quantidade, 0);
    assert.equal(calcularLoteFracionado({ capital: null, riscoPct: 1, entrada: 10, stop: 9 }).quantidade, 0);
  });
});

describe("lote fracionado da venda (cripto, futuros)", () => {
  const perfil = { capital: 1000, riscoPct: 1 };

  it("o risco e o stop ACIMA da entrada", () => {
    // vende a 73,50 com stop em 76,20: US$ 2,70 por moeda; risco de US$ 10
    const lote = calcularLoteFracionadoVenda({ ...perfil, entrada: 73.5, stop: 76.2 });
    assert.ok(Math.abs(lote.quantidade - 10 / 2.7) < 1e-6);
    assert.ok(Math.abs(lote.perdaMaxima - 10) < 0.01);
    assert.equal(lote.limitadoPeloCapital, false);
  });

  it("sem alavancagem: a posicao vendida nao passa do capital", () => {
    const lote = calcularLoteFracionadoVenda({ ...perfil, entrada: 100, stop: 100.1 });
    assert.equal(lote.valorPosicao, 1000);
    assert.equal(lote.limitadoPeloCapital, true);
  });

  it("stop abaixo da entrada nao e venda", () => {
    assert.equal(calcularLoteFracionadoVenda({ ...perfil, entrada: 100, stop: 90 }).quantidade, 0);
  });
});

describe("regras do diario de trades", () => {
  it("B3: sem taxa, acao inteira, centavo e PM de seis casas (as contas de sempre)", () => {
    assert.deepEqual(regrasDoDiario("b3"), {
      taxa: 0,
      casasDaQuantidade: 0,
      casasDaPosicao: 0,
      casasDoPreco: 2,
      casasDoPrecoMedio: 6,
      todoDia: false,
      categoriasDoEstudo: [],
    });
  });

  it("cripto: 0,1% da Binance, oito casas de moeda e dez de preco", () => {
    const r = regrasDoDiario("cripto");
    assert.equal(r.taxa, 0.001);
    assert.equal(r.casasDaQuantidade, 8);
    assert.equal(r.casasDoPreco, 10); // o numeric(28, 10) da migration 0027
    assert.equal(r.todoDia, true);
  });

  it("o setup do estudo no diario e um que o config conhece", () => {
    for (const c of regrasDoDiario("cripto").categoriasDoEstudo) {
      assert.ok(CATEGORIAS_DO_ESTUDO.includes(c), c);
    }
  });

  it("o dia de cripto e o UTC; o da B3, o de Sao Paulo", () => {
    const meiaNoiteEMeiaUtc = new Date("2026-11-18T00:30:00Z"); // 21h30 de 17/11 em Brasilia
    assert.equal(diaDoMercado("b3", meiaNoiteEMeiaUtc), "2026-11-17");
    assert.equal(diaDoMercado("cripto", meiaNoiteEMeiaUtc), "2026-11-18");
  });

  it("ticker de cada mercado; a regra da B3 e a mesma de ticker.ts", () => {
    for (const t of ["PETR4", "BPAC11", "TAEE11B", "B3SA3"]) assert.ok(tickerValido("b3", t), t);
    assert.ok(!tickerValido("b3", "BTC"));
    for (const m of ["BTC", "1INCH", "RENDER"]) assert.ok(tickerValido("cripto", m), m);
    assert.ok(!tickerValido("cripto", "BTC/USDT"));
    assert.ok(!tickerValido("cripto", "../x"));
    for (const t of ["PETR4", "BTC", "TAEE11B", "petr4", "PETR", "B3SA3"]) {
      assert.equal(tickerValido("b3", t), TICKER.test(t), t);
    }
  });

  it("link do trade leva o mercado, porque os ids repetem", () => {
    assert.equal(linkDoTrade("b3", 7), "/trades/7");
    assert.equal(linkDoTrade("cripto", 7), "/trades/7?mercado=cripto");
    assert.equal(linkDaFichaNoMercado("cripto", "BTC"), "/cripto/BTC");
  });

  it("numeros para o campo do formulario, com virgula e sem milhar", () => {
    assert.equal(quantidadeParaCampo("cripto", 0.0152847), "0,0152847");
    assert.equal(quantidadeParaCampo("b3", 100), "100");
    assert.equal(precoParaCampo("b3", 38.2), "38,20");
    assert.equal(precoParaCampo("cripto", 65351.5), "65351,5");
    assert.equal(precoParaCampo("cripto", 0.52341), "0,52341");
  });
});

