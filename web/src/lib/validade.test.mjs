// Validade do alerta criado pelo setup: vale ate o pregao seguinte ao candle.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { alertaVencido, hojeNaB3 } from "./validade.ts";

describe("alertaVencido", () => {
  it("alerta manual nunca vence", () => {
    assert.equal(alertaVencido(null, "2026-10-22"), false);
  });

  it("vale ate o fim do dia da validade", () => {
    assert.equal(alertaVencido("2026-10-22", "2026-10-22"), false);
    assert.equal(alertaVencido("2026-10-22", "2026-10-21"), false);
  });

  it("vence no dia seguinte", () => {
    assert.equal(alertaVencido("2026-10-22", "2026-10-23"), true);
  });
});

describe("hojeNaB3", () => {
  it("usa o dia de Sao Paulo, nao o UTC", () => {
    // 01:30 UTC de 22/10 ainda e 21/10 em Sao Paulo (UTC-3)
    assert.equal(hojeNaB3(new Date("2026-10-22T01:30:00Z")), "2026-10-21");
  });
});
