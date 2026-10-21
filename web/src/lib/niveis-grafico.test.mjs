// Linhas de suporte e resistencia da ficha.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { trechosDosNiveis } from "./niveis-grafico.ts";

const DATAS = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"];

function nivel(campos) {
  return {
    lado: "suporte",
    preco: 10,
    de: "2026-10-01",
    ate: "2026-10-08",
    valeDesde: "2026-10-05",
    rompidoEm: null,
    virou: false,
    ativo: true,
    ...campos,
  };
}

describe("trechosDosNiveis", () => {
  it("pontilhado ate o 3o toque, cheio e grosso depois", () => {
    const t = trechosDosNiveis([nivel({})], DATAS);
    assert.deepEqual(
      t.map((x) => [x.de, x.ate, x.estilo, x.largura]),
      [
        ["2026-10-01", "2026-10-05", "pontilhado", 1],
        ["2026-10-05", "2026-10-08", "cheio", 2],
      ],
    );
  });

  it("rompido fica fino", () => {
    const t = trechosDosNiveis([nivel({ ativo: false, ate: "2026-10-07", rompidoEm: "2026-10-07" })], DATAS);
    assert.equal(t.at(-1).largura, 1);
    assert.equal(t.at(-1).ate, "2026-10-07");
  });

  it("nivel que trocou de papel e tracejado de ponta a ponta", () => {
    const t = trechosDosNiveis([nivel({ virou: true, valeDesde: null })], DATAS);
    assert.deepEqual(t.map((x) => x.estilo), ["tracejado"]);
  });

  it("sem o 3o toque, todo pontilhado", () => {
    const t = trechosDosNiveis([nivel({ valeDesde: null })], DATAS);
    assert.deepEqual(t.map((x) => [x.estilo, x.largura]), [["pontilhado", 1]]);
  });

  it("recorta ao trecho do grafico e ignora o que fica fora", () => {
    const t = trechosDosNiveis(
      [nivel({ de: "2026-09-01", valeDesde: "2026-09-10" }), nivel({ de: "2026-08-01", ate: "2026-09-30" })],
      DATAS,
    );
    assert.equal(t.length, 1);
    assert.deepEqual([t[0].de, t[0].ate, t[0].estilo], ["2026-10-01", "2026-10-08", "cheio"]);
  });

  it("dia sem pregao no grafico encosta no pregao vizinho", () => {
    const t = trechosDosNiveis([nivel({ de: "2026-10-03", valeDesde: "2026-10-04", ate: "2026-10-09" })], DATAS);
    assert.deepEqual([t[0].de, t[0].ate], ["2026-10-05", "2026-10-08"]);
  });
});
