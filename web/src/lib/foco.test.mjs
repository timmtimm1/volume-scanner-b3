// Regressao de 21/10/2026: o link do setup abria o grafico no evento antigo.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { focoDoGrafico } from "./foco.ts";
import { linkDaFicha } from "./setups-tela.ts";

const DATAS = ["2026-04-24", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"];

describe("focoDoGrafico", () => {
  it("o foco do setup ganha do evento, com mais pregoes depois", () => {
    assert.deepEqual(focoDoGrafico("2026-10-14", DATAS, "2026-04-24"), { dia: "2026-10-14", depois: 25 });
  });

  it("sem foco, vale o evento como sempre", () => {
    assert.deepEqual(focoDoGrafico(null, DATAS, "2026-04-24"), { dia: "2026-04-24", depois: 14 });
  });

  it("foco fora do grafico nao vale", () => {
    assert.equal(focoDoGrafico("2025-01-02", DATAS, "2026-04-24").dia, "2026-04-24");
  });
});

describe("linkDaFicha", () => {
  it("o setup abre com foco no candle, nunca como evento (?data=)", () => {
    const link = linkDaFicha({ ticker: "SAPR11", tradeDate: "2026-10-14" });
    assert.equal(link, "/papel/SAPR11?foco=2026-10-14");
    assert.ok(!link.includes("data="));
  });
});
