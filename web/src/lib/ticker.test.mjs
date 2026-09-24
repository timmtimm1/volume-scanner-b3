// O formato de ticker que o site aceita na URL da ficha e nas rotas de API.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { TICKER } from "./ticker.ts";

describe("TICKER", () => {
  it("aceita papel da B3, inclusive com digito no emissor", () => {
    for (const t of ["PETR4", "BPAC11", "VALE3", "TAEE11B", "B3SA3", "B1003"]) {
      assert.ok(TICKER.test(t), t);
    }
  });

  it("recusa o que mudaria o caminho de uma URL", () => {
    for (const t of ["../../etc/passwd", "PETR4/../ITUB4", "", "petr4", "3B3SA3", "B3S/3", "PETR4?x=1"]) {
      assert.ok(!TICKER.test(t), t);
    }
  });
});
