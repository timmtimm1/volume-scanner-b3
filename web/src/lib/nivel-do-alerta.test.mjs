// O nivel do alerta criado ou arrastado no grafico. `npm test`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { direcaoDoNivel, lerNivelDigitado, nivelEmCentavos } from "./nivel-do-alerta.ts";

describe("nivelEmCentavos", () => {
  it("arredonda ao centavo", () => {
    assert.equal(nivelEmCentavos(32.4949), 32.49);
    assert.equal(nivelEmCentavos(32.495), 32.5);
    assert.equal(nivelEmCentavos(7), 7);
  });
});

describe("direcaoDoNivel", () => {
  it("acima do preco de agora vigia a subida", () => {
    assert.equal(direcaoDoNivel(35, 32.1), "acima");
  });

  it("abaixo do preco de agora vigia a queda", () => {
    assert.equal(direcaoDoNivel(30, 32.1), "abaixo");
  });

  it("igual ao preco conta como acima, como no clique do celular", () => {
    assert.equal(direcaoDoNivel(32.1, 32.1), "acima");
  });

  it("arrastar um 'subir ate' para baixo do preco o vira 'cair ate'", () => {
    assert.equal(direcaoDoNivel(29.5, 32.1, "acima"), "abaixo");
  });

  it("sem preco de referencia, mantem a direcao que o alerta tinha", () => {
    assert.equal(direcaoDoNivel(29.5, null, "acima"), "acima");
    assert.equal(direcaoDoNivel(40, null, "abaixo"), "abaixo");
    assert.equal(direcaoDoNivel(40, null), "acima");
  });
});

describe("lerNivelDigitado", () => {
  it("aceita virgula e ponto", () => {
    assert.equal(lerNivelDigitado("32,50"), 32.5);
    assert.equal(lerNivelDigitado("32.50"), 32.5);
    assert.equal(lerNivelDigitado("32"), 32);
  });

  it("ignora R$ e espacos", () => {
    assert.equal(lerNivelDigitado("R$ 32,50"), 32.5);
    assert.equal(lerNivelDigitado("  32,5 "), 32.5);
  });

  it("arredonda ao centavo", () => {
    assert.equal(lerNivelDigitado("32,456"), 32.46);
  });

  it("recusa o que nao e preco", () => {
    assert.equal(lerNivelDigitado(""), null);
    assert.equal(lerNivelDigitado("abc"), null);
    assert.equal(lerNivelDigitado("0"), null);
    assert.equal(lerNivelDigitado("0,00"), null);
    assert.equal(lerNivelDigitado("-3"), null);
    assert.equal(lerNivelDigitado("1.234,50"), null);
  });
});
