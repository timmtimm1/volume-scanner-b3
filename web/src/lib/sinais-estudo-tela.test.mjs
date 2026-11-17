// Os setups do estudo de cripto na tela: prazos e a explicacao da nota.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { aberturaDaEntrada, explicacaoDaNota, fimDoPrazo, SETUPS_DO_ESTUDO } from "./sinais-estudo-tela.ts";

describe("setups do estudo", () => {
  it("a entrada e a abertura do candle seguinte ao sinal", () => {
    assert.equal(aberturaDaEntrada("2026-11-16T00:00:00.000Z", "1d"), "2026-11-17T00:00:00.000Z");
    assert.equal(aberturaDaEntrada("2026-11-17T08:00:00.000Z", "4h"), "2026-11-17T12:00:00.000Z");
  });

  it("o prazo termina na abertura depois do ultimo candle permitido", () => {
    // diario: entra no dia 17, pode ficar 20 candles alem dele, sai na abertura do 22o
    assert.equal(fimDoPrazo("2026-11-16T00:00:00.000Z", "1d", 20), "2026-12-08T00:00:00.000Z");
    // 4h: 42 candles alem da entrada = 7 dias
    assert.equal(fimDoPrazo("2026-11-17T08:00:00.000Z", "4h", 42), "2026-11-24T16:00:00.000Z");
  });

  it("a nota diz de onde vem e com que folga", () => {
    assert.equal(
      explicacaoDaNota(SETUPS_DO_ESTUDO.rsi_reversao),
      "no estudo, +0,12 R por trade em 2022–2026 (intervalo de −0,10 a +0,36; 1.622 trades)",
    );
    assert.equal(SETUPS_DO_ESTUDO.compressao_venda.cor, "verde");
    assert.equal(SETUPS_DO_ESTUDO.compressao_venda.lado, "venda");
  });
});
