// O nome da empresa na tela: quando mostrar, quando deixar so o ticker.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { nomeDaEmpresa } from "./formato.ts";

describe("nomeDaEmpresa", () => {
  it("nome curto passa, e e o caso da maioria", () => {
    // Mediana da base: 17 caracteres.
    assert.equal(nomeDaEmpresa("PETROBRAS"), "PETROBRAS");
    assert.equal(nomeDaEmpresa("BANRISUL S/A"), "BANRISUL S/A");
    assert.equal(nomeDaEmpresa("DEXXOS PARTICIPAÇÕES S.A."), "DEXXOS PARTICIPAÇÕES S.A.");
  });

  it("razao social longa vira null: o ticker sozinho diz o mesmo", () => {
    // 63 caracteres, o maior da base. Ocupava duas linhas na ficha.
    assert.equal(
      nomeDaEmpresa("MERCANTIL FINANCEIRA S.A. CRÉDITO, FINANCIAMENTO E INVESTIMENTO"),
      null,
    );
    assert.equal(
      nomeDaEmpresa("VAMOS LOCAÇÃO DE CAMINHÕES, MÁQUINAS E EQUIPAMENTOS S.A."),
      null,
    );
  });

  it("o corte e em 34, e e exato", () => {
    assert.equal(nomeDaEmpresa("A".repeat(34)), "A".repeat(34));
    assert.equal(nomeDaEmpresa("A".repeat(35)), null);
  });

  it("espaco em volta nao conta para o limite", () => {
    assert.equal(nomeDaEmpresa(`  ${"A".repeat(34)}  `), "A".repeat(34));
  });

  it("papel sem empresa ligada nao tem nome", () => {
    assert.equal(nomeDaEmpresa(null), null);
    assert.equal(nomeDaEmpresa(undefined), null);
    assert.equal(nomeDaEmpresa(""), null);
    assert.equal(nomeDaEmpresa("   "), null);
  });
});
