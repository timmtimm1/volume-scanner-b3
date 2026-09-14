// Medias moveis: calculo e a lista guardada. `npm test`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { mediaMovelAritmetica, mediaMovelExponencial } from "./indicadores.ts";
import {
  CORES_DAS_MEDIAS,
  MEDIAS_PADRAO,
  comMedia,
  lerMedias,
  proximaCor,
  rotuloDaMedia,
  semMedia,
} from "./medias.ts";

const barras = (fechamentos) =>
  fechamentos.map((close, i) => ({
    tradeDate: `2026-09-${String(i + 1).padStart(2, "0")}`,
    open: close,
    high: close,
    low: close,
    close,
    volumeFinancial: 1,
  }));

const perto = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);

describe("mediaMovelAritmetica", () => {
  it("e a media simples dos ultimos N fechamentos, a partir do N-esimo dia", () => {
    const pontos = mediaMovelAritmetica(barras([1, 2, 3, 4, 5]), 3);
    assert.deepEqual(
      pontos.map((p) => p.tradeDate),
      ["2026-09-03", "2026-09-04", "2026-09-05"],
    );
    perto(pontos[0].valor, 2);
    perto(pontos[1].valor, 3);
    perto(pontos[2].valor, 4);
  });

  it("sem fechamentos suficientes nao ha ponto", () => {
    assert.deepEqual(mediaMovelAritmetica(barras([1, 2]), 3), []);
  });

  it("recusa periodo menor que 2", () => {
    assert.throws(() => mediaMovelAritmetica(barras([1, 2, 3]), 1));
  });
});

describe("mediaMovelExponencial", () => {
  it("comeca na MMA dos N primeiros e aplica o fator 2/(N+1)", () => {
    // N=3: semente (1+2+3)/3 = 2; k = 0,5.
    const pontos = mediaMovelExponencial(barras([1, 2, 3, 4, 5]), 3);
    assert.equal(pontos[0].tradeDate, "2026-09-03");
    perto(pontos[0].valor, 2);
    perto(pontos[1].valor, 4 * 0.5 + 2 * 0.5); // 3
    perto(pontos[2].valor, 5 * 0.5 + 3 * 0.5); // 4
  });

  it("reage mais rapido que a MMA de mesmo periodo a um salto", () => {
    const serie = barras([10, 10, 10, 10, 10, 10, 20]);
    const mma = mediaMovelAritmetica(serie, 5).at(-1).valor;
    const mme = mediaMovelExponencial(serie, 5).at(-1).valor;
    assert.ok(mme > mma, `MME ${mme} deveria passar da MMA ${mma}`);
  });
});

describe("lista de medias", () => {
  it("padrao: MMA 20 amarela e MME 9 rosa", () => {
    assert.deepEqual(
      MEDIAS_PADRAO.map((m) => [rotuloDaMedia(m), m.cor]),
      [
        ["MMA 20", "#EAB308"],
        ["MME 9", "#EC4899"],
      ],
    );
  });

  it("sem nada guardado, vale o padrao; lista vazia guardada continua vazia", () => {
    assert.equal(lerMedias(null).length, 2);
    assert.deepEqual(lerMedias("[]"), []);
  });

  it("texto corrompido volta ao padrao; item invalido e repetido saem", () => {
    assert.equal(lerMedias("{isto nao e json").length, 2);
    const lidas = lerMedias(
      JSON.stringify([
        { tipo: "MME", periodo: 21, cor: "#0EA5E9" },
        { tipo: "MME", periodo: 21, cor: "#A855F7" },
        { tipo: "WMA", periodo: 10, cor: "#0EA5E9" },
        { tipo: "MMA", periodo: 1, cor: "#0EA5E9" },
        { tipo: "MMA", periodo: 50, cor: "vermelho" },
      ]),
    );
    assert.deepEqual(lidas, [{ id: "MME-21", tipo: "MME", periodo: 21, cor: "#0EA5E9" }]);
  });

  it("acrescentar a mesma media nao duplica; remover tira so ela", () => {
    const base = [...MEDIAS_PADRAO];
    const com = comMedia(base, { tipo: "MMA", periodo: 50, cor: "#0EA5E9" });
    assert.equal(com.length, 3);
    assert.equal(comMedia(com, { tipo: "MMA", periodo: 50, cor: "#A855F7" }).length, 3);
    assert.deepEqual(
      semMedia(com, "MMA-20").map((m) => m.id),
      ["MME-9", "MMA-50"],
    );
  });

  it("a proxima cor e a primeira livre da paleta", () => {
    assert.equal(proximaCor([...MEDIAS_PADRAO]), CORES_DAS_MEDIAS[2]);
  });
});
