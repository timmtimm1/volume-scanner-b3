// A lista de moedas da aba Cripto: busca, filtros e preco da linha.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { contarFiltros, filtrarMoedas, precoDaLinha } from "./cripto-lista.ts";

const moeda = (ticker, nome, extra = {}) => ({
  ticker, nome, posicao: null, preco: 1, variacao: 0, setups: 0, comTrade: false, inclinacoes: null, ...extra,
});

const LINHAS = [
  moeda("BTC", "Bitcoin", { setups: 2 }),
  moeda("ETH", "Ethereum", { comTrade: true }),
  moeda("ASOL", "Aave Solana"),
  moeda("SOL", "Solana", { setups: 1, comTrade: true }),
];
const nenhumaEmAlta = () => false;
const tickers = (l) => l.map((x) => x.ticker);

describe("filtrarMoedas", () => {
  it("sem busca mantem a ordem de valor de mercado", () => {
    assert.deepEqual(tickers(filtrarMoedas(LINHAS, "", "todas", nenhumaEmAlta)), ["BTC", "ETH", "ASOL", "SOL"]);
  });

  it("o ticker exato vem antes de quem so contem o texto", () => {
    assert.deepEqual(tickers(filtrarMoedas(LINHAS, "sol", "todas", nenhumaEmAlta)), ["SOL", "ASOL"]);
  });

  it("acha pelo nome, sem ligar para maiuscula, acento ou espaco", () => {
    assert.deepEqual(tickers(filtrarMoedas(LINHAS, "  BÍTCOIN ", "todas", nenhumaEmAlta)), ["BTC"]);
  });

  it("busca e filtro valem juntos", () => {
    assert.deepEqual(tickers(filtrarMoedas(LINHAS, "e", "trades", nenhumaEmAlta)), ["ETH"]);
  });

  it("os filtros de sinal, alta e trades", () => {
    assert.deepEqual(tickers(filtrarMoedas(LINHAS, "", "sinal", nenhumaEmAlta)), ["BTC", "SOL"]);
    assert.deepEqual(tickers(filtrarMoedas(LINHAS, "", "trades", nenhumaEmAlta)), ["ETH", "SOL"]);
    assert.deepEqual(tickers(filtrarMoedas(LINHAS, "", "alta", (l) => l.ticker === "ETH")), ["ETH"]);
  });
});

describe("contarFiltros", () => {
  it("conta cada filtro", () => {
    assert.deepEqual(contarFiltros(LINHAS, (l) => l.ticker === "BTC"), { todas: 4, sinal: 2, alta: 1, trades: 2 });
  });
});

describe("precoDaLinha", () => {
  const hoje = (dia, ultimo) => ({ moeda: "BTC", dia, abertura: 1, maxima: 1, minima: 1, ultimo, volume: 1, hora: "" });

  it("sem a Binance usa o ultimo fechamento contra o anterior", () => {
    const r = precoDaLinha(110, 100, "2026-11-22", undefined);
    assert.equal(r.preco, 110);
    assert.ok(Math.abs(r.variacao - 0.1) < 1e-12);
  });

  it("com o dia novo compara com o ultimo candle fechado", () => {
    const r = precoDaLinha(100, 50, "2026-11-22", hoje("2026-11-23", 120));
    assert.equal(r.preco, 120);
    assert.ok(Math.abs(r.variacao - 0.2) < 1e-12);
  });

  it("se o banco ja tem o candle de hoje, a base e o de ontem", () => {
    const r = precoDaLinha(120, 100, "2026-11-23", hoje("2026-11-23", 125));
    assert.ok(Math.abs(r.variacao - 0.25) < 1e-12);
  });

  it("sem base nao inventa variacao", () => {
    assert.equal(precoDaLinha(100, null, "2026-11-22", undefined).variacao, null);
    assert.equal(precoDaLinha(null, null, null, undefined).preco, null);
  });
});
