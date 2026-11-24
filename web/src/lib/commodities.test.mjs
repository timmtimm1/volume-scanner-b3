// As commodities da página Análise: a lista, o grupo na URL e os endereços das abas.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  COMMODITIES,
  commodityDe,
  eCommodity,
  grupoDaUrl,
  hrefDaAnalise,
} from "./commodities.ts";

describe("COMMODITIES", () => {
  it("cada entrada tem ticker igual à chave, tipo válido, detalhes e par em USDT", () => {
    for (const [chave, c] of Object.entries(COMMODITIES)) {
      assert.equal(c.ticker, chave);
      assert.ok(c.tipo === "token" || c.tipo === "contrato", chave);
      assert.ok(c.detalhes.length > 0, chave);
      assert.ok(c.par.endsWith("USDT"), chave);
    }
  });

  it("são 10: 2 tokens e 8 contratos", () => {
    const todas = Object.values(COMMODITIES);
    assert.equal(todas.length, 10);
    assert.equal(todas.filter((c) => c.tipo === "token").length, 2);
    assert.equal(todas.filter((c) => c.tipo === "contrato").length, 8);
  });
});

describe("eCommodity e commodityDe", () => {
  it("reconhece as commodities e nada mais", () => {
    assert.equal(eCommodity("XAU"), true);
    assert.equal(eCommodity("BTC"), false);
    assert.equal(eCommodity("toString"), false);
  });

  it("commodityDe devolve a entrada ou null", () => {
    assert.equal(commodityDe("BTC"), null);
    assert.equal(commodityDe("toString"), null);
    assert.equal(commodityDe("CL")?.nome, "Petróleo WTI");
  });
});

describe("grupoDaUrl", () => {
  it("só commodity vira commodity", () => {
    assert.equal(grupoDaUrl("commodity"), "commodity");
    assert.equal(grupoDaUrl("cripto"), "cripto");
    assert.equal(grupoDaUrl(undefined), "cripto");
    assert.equal(grupoDaUrl("lixo"), "cripto");
    assert.equal(grupoDaUrl(["commodity"]), "cripto");
  });
});

describe("hrefDaAnalise", () => {
  it("as seis combinações", () => {
    assert.equal(hrefDaAnalise("ano", "cripto"), "/analise");
    assert.equal(hrefDaAnalise("sazonalidade", "cripto"), "/analise?aba=sazonalidade");
    assert.equal(hrefDaAnalise("rankings", "cripto"), "/analise?aba=rankings");
    assert.equal(hrefDaAnalise("ano", "commodity"), "/analise?grupo=commodity");
    assert.equal(
      hrefDaAnalise("sazonalidade", "commodity"),
      "/analise?aba=sazonalidade&grupo=commodity",
    );
    assert.equal(hrefDaAnalise("rankings", "commodity"), "/analise?aba=rankings&grupo=commodity");
  });
});
