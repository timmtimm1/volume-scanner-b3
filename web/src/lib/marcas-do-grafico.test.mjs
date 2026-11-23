// O que o grafico da moeda guarda sobre as marcas escondidas. `npm test`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { lerMarcas, SEM_SETAS, TUDO_LIGADO } from "./marcas-do-grafico.ts";

describe("lerMarcas", () => {
  it("sem nada guardado, mostra tudo", () => {
    assert.deepEqual(lerMarcas(null), TUDO_LIGADO);
    assert.deepEqual(lerMarcas(""), TUDO_LIGADO);
  });

  it("le o que foi guardado", () => {
    assert.deepEqual(lerMarcas('{"eventos":false,"setups":true}'), { eventos: false, setups: true });
    assert.deepEqual(lerMarcas('{"eventos":true,"setups":false}'), { eventos: true, setups: false });
  });

  it("campo ausente ou de outro tipo fica ligado, sem apagar o outro", () => {
    assert.deepEqual(lerMarcas('{"eventos":false}'), { eventos: false, setups: true });
    assert.deepEqual(lerMarcas('{"eventos":"nao","setups":false}'), { eventos: true, setups: false });
  });

  it("texto que nao e o objeto esperado mostra tudo", () => {
    assert.deepEqual(lerMarcas("{quebrado"), TUDO_LIGADO);
    assert.deepEqual(lerMarcas("[false,false]"), TUDO_LIGADO);
    assert.deepEqual(lerMarcas("false"), TUDO_LIGADO);
  });
});

describe("lerMarcas com padrao", () => {
  it("sem escolha guardada vale o padrao", () => {
    assert.deepEqual(lerMarcas(null, SEM_SETAS), SEM_SETAS);
    assert.deepEqual(lerMarcas("nao e json", SEM_SETAS), SEM_SETAS);
  });

  it("a escolha guardada vence o padrao", () => {
    assert.deepEqual(lerMarcas('{"eventos":true,"setups":true}', SEM_SETAS), TUDO_LIGADO);
  });

  it("campo ausente fica no padrao", () => {
    assert.deepEqual(lerMarcas('{"eventos":false}', SEM_SETAS), { eventos: false, setups: false });
  });
});
