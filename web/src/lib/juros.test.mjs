// A logica pura do grafico de juros: series, filtro por edicao, lacunas, cores, escolha.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  compactar,
  coresDasSeries,
  lerEscolha,
  ligadasAoAbrir,
  misturar,
  SERIES,
  trechos,
  valoresNaSemana,
} from "./juros.ts";

const linha = (semana, serie, taxa) => ({ semana, serie, taxa });

const LINHAS = [
  linha("2016-10-21", "pre_1a", 11.5),
  linha("2016-10-14", "pre_1a", 11.97),
  linha("2016-10-14", "selic", 14.25),
  linha("2016-10-21", "selic", 14.0),
  linha("2016-10-14", "pre_10a", 11.4),
  linha("2016-10-14", "ipca_10a", 5.4),
  linha("2016-10-14", "serie_desconhecida", 1),
];

describe("compactar", () => {
  const h = compactar(LINHAS);

  it("lista as semanas sem repetir, em ordem", () => {
    assert.deepEqual(h.semanas, ["2016-10-14", "2016-10-21"]);
  });

  it("alinha cada serie com as semanas, com null nos buracos", () => {
    assert.deepEqual(h.taxas.pre_1a, [11.97, 11.5]);
    assert.deepEqual(h.taxas.selic, [14.25, 14.0]);
    assert.deepEqual(h.taxas.pre_10a, [11.4, null]);
    assert.deepEqual(h.taxas.pre_2a, [null, null]);
    for (const v of Object.values(h.taxas)) assert.equal(v.length, h.semanas.length);
  });

  it("arredonda a 2 casas", () => {
    const r = compactar([linha("2016-10-14", "pre_1a", 11.97456), linha("2016-10-21", "pre_1a", 11.994)]);
    assert.deepEqual(r.taxas.pre_1a, [11.97, 11.99]);
  });

  it("ignora serie desconhecida e taxa que nao e numero, e tem as sete series", () => {
    const r = compactar([...LINHAS, linha("2016-10-28", "pre_1a", NaN)]);
    assert.deepEqual(r.semanas, ["2016-10-14", "2016-10-21"]);
    assert.equal(Object.keys(r.taxas).length, 7);
    assert.ok(!("serie_desconhecida" in r.taxas));
  });

  it("historico vazio nao tem semana nem ponto", () => {
    const r = compactar([]);
    assert.deepEqual(r.semanas, []);
    assert.deepEqual(r.taxas.selic, []);
  });
});

describe("trechos", () => {
  it("divide a serie em trechos onde faltam semanas, sem ligar o que ha antes e depois", () => {
    const h = {
      semanas: ["a", "b", "c", "d", "e", "f"],
      taxas: { ...compactar([]).taxas, pre_1a: [1, 2, null, null, 5, null] },
    };
    assert.deepEqual(trechos(h, "pre_1a"), [
      [
        { time: "a", value: 1 },
        { time: "b", value: 2 },
      ],
      [{ time: "e", value: 5 }],
    ]);
    assert.deepEqual(trechos(h, "pre_2a"), []);
    assert.equal(trechos({ semanas: ["a", "b"], taxas: { ...h.taxas, pre_1a: [1, 2] } }, "pre_1a").length, 1);
  });
});

describe("valoresNaSemana", () => {
  it("devolve o valor de cada serie e null onde nao ha", () => {
    const v = valoresNaSemana(compactar(LINHAS), "2016-10-21");
    assert.equal(v.selic, 14.0);
    assert.equal(v.pre_1a, 11.5);
    assert.equal(v.pre_10a, null);
  });

  it("semana fora do historico: tudo null", () => {
    const v = valoresNaSemana(compactar(LINHAS), "2000-01-07");
    assert.ok(Object.values(v).every((x) => x === null));
  });
});

describe("series ligadas ao abrir", () => {
  it("sao Selic, Pre 1a, Pre 10a e IPCA+ 10a", () => {
    assert.deepEqual([...ligadasAoAbrir()].sort(), ["ipca_10a", "pre_10a", "pre_1a", "selic"]);
  });

  it("a legenda tem as sete series, a Selic primeiro", () => {
    assert.equal(SERIES.length, 7);
    assert.equal(SERIES[0].id, "selic");
  });
});

describe("lerEscolha", () => {
  it("sem nada guardado ou com lixo, volta ao padrao", () => {
    for (const bruto of [null, "{", "42", "[]", '["x"]']) {
      assert.deepEqual([...lerEscolha(bruto)].sort(), [...ligadasAoAbrir()].sort());
    }
  });

  it("le a escolha guardada e descarta o que nao e serie", () => {
    assert.deepEqual([...lerEscolha('["pre_2a","selic","x"]')].sort(), ["pre_2a", "selic"]);
  });
});

describe("cores", () => {
  it("misturar clareia com t positivo e escurece com t negativo", () => {
    assert.equal(misturar("#000000", 1), "#ffffff");
    assert.equal(misturar("#ffffff", -1), "#000000");
    assert.equal(misturar("#4f46e5", 0), "#4f46e5");
    assert.equal(misturar("nao-e-cor", 0.5), "nao-e-cor");
  });

  it("os prefixados vao do mais claro (1a) ao mais escuro (10a) e a Selic e neutra", () => {
    const c = coresDasSeries("#4f46e5", "#4a4d6a");
    const luz = (hex) => {
      const n = parseInt(hex.slice(1), 16);
      return ((n >> 16) & 255) * 0.3 + ((n >> 8) & 255) * 0.59 + (n & 255) * 0.11;
    };
    assert.ok(luz(c.pre_1a) > luz(c.pre_2a));
    assert.ok(luz(c.pre_2a) > luz(c.pre_5a));
    assert.ok(luz(c.pre_5a) > luz(c.pre_10a));
    assert.ok(luz(c.ipca_5a) > luz(c.ipca_10a));
    assert.equal(c.selic, "#4a4d6a");
    assert.equal(c.pre_5a, "#4f46e5");
  });

  it("sete cores distintas", () => {
    const c = coresDasSeries("#8e87ff", "#b3b4cf");
    assert.equal(new Set(Object.values(c)).size, 7);
  });
});
