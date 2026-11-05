// A pagina Backtest: formatacao e leitura da selecao.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  fmtIntervalo,
  fmtPct,
  fmtR,
  fmtVolume,
  GRUPOS,
  lerSelecao,
  linkDaSelecao,
  linkDoTrade,
  NIVEIS,
  ORDEM_DOS_SETUPS,
  SAIDAS,
  SETUPS,
  volumeAlto,
} from "./backtest-tela.ts";

const MENOS = "−";

const escolha = (setup, saida, grupo) => ({ setup, nivel: "fraco", saida, grupo });

describe("fmtR", () => {
  it("sinal explicito, virgula e duas casas", () => {
    assert.equal(fmtR(0.31), "+0,31 R");
    assert.equal(fmtR(-0.05), `${MENOS}0,05 R`);
    assert.equal(fmtR(1.234), "+1,23 R");
  });
  it("zero exato nao leva sinal", () => {
    assert.equal(fmtR(0), "0,00 R");
  });
  it("ausente vira travessao", () => {
    assert.equal(fmtR(null), "—");
    assert.equal(fmtR(undefined), "—");
    assert.equal(fmtR(Number.NaN), "—");
  });
});

describe("fmtIntervalo", () => {
  it("dois lados com sinal", () => {
    assert.equal(fmtIntervalo(0.09, 0.54), "[+0,09; +0,54]");
    assert.equal(fmtIntervalo(-0.2, 0.1), `[${MENOS}0,20; +0,10]`);
  });
  it("sem um lado, travessao", () => {
    assert.equal(fmtIntervalo(null, 0.5), "—");
    assert.equal(fmtIntervalo(0.1, Number.NaN), "—");
  });
});

describe("fmtPct e volume", () => {
  it("fracao vira percentual inteiro", () => {
    assert.equal(fmtPct(0.38), "38%");
    assert.equal(fmtPct(null), "—");
  });
  it("volume alto a partir de 1,5", () => {
    assert.equal(volumeAlto(1.5), true);
    assert.equal(volumeAlto(1.49), false);
    assert.equal(volumeAlto(null), false);
    assert.equal(fmtVolume(2.1), "vol 2,1×");
  });
});

describe("lerSelecao", () => {
  const escolhas = [escolha("forca", "mme9", "alta"), escolha("suporte", "alvo3", "alta")];

  it("sem nada: primeiro setup e mme9/todos quando nao ha escolha", () => {
    assert.deepEqual(lerSelecao({}, escolhas), { setup: "9.1", saida: "mme9", grupo: "todos" });
  });
  it("setup sem saida e grupo usa a escolha dele", () => {
    assert.deepEqual(lerSelecao({ setup: "suporte" }, escolhas), {
      setup: "suporte",
      saida: "alvo3",
      grupo: "alta",
    });
  });
  it("saida e grupo da URL valem sobre a escolha", () => {
    assert.deepEqual(lerSelecao({ setup: "forca", saida: "alvo1", grupo: "contra" }, escolhas), {
      setup: "forca",
      saida: "alvo1",
      grupo: "contra",
    });
  });
  it("valores invalidos caem nos padroes", () => {
    assert.deepEqual(lerSelecao({ setup: "xyz", saida: "nada", grupo: "?" }, escolhas), {
      setup: "9.1",
      saida: "mme9",
      grupo: "todos",
    });
    assert.deepEqual(lerSelecao({ setup: "forca", saida: "nada", grupo: "?" }, escolhas), {
      setup: "forca",
      saida: "mme9",
      grupo: "alta",
    });
  });
  it("parametro repetido usa o primeiro", () => {
    assert.equal(lerSelecao({ setup: ["pfr", "123"] }, escolhas).setup, "pfr");
  });
  it("escolha sem saida (nenhuma combinacao com 100 trades) cai em mme9/todos", () => {
    const sem = [escolha("pfr", null, null)];
    assert.deepEqual(lerSelecao({ setup: "pfr" }, sem), { setup: "pfr", saida: "mme9", grupo: "todos" });
  });
});

describe("tabelas de rotulos", () => {
  it("a ordem cobre todos os setups, sem repetir", () => {
    assert.deepEqual([...ORDEM_DOS_SETUPS].sort(), Object.keys(SETUPS).sort());
    assert.equal(new Set(ORDEM_DOS_SETUPS).size, ORDEM_DOS_SETUPS.length);
  });
  it("todo setup tem nome e regra", () => {
    for (const s of Object.values(SETUPS)) {
      assert.ok(s.nome.length > 0 && s.regra.length > 0);
    }
  });
  it("rotulos das saidas, grupos e niveis", () => {
    assert.equal(Object.keys(SAIDAS).length, 5);
    assert.equal(Object.keys(GRUPOS).length, 3);
    assert.deepEqual(Object.keys(NIVEIS), ["firme", "fraco", "falhou"]);
  });
});

describe("links", () => {
  it("link da selecao preserva setup, saida e grupo", () => {
    assert.equal(
      linkDaSelecao({ setup: "9.4", saida: "mme9", grupo: "alta" }),
      "/setups/backtest?setup=9.4&saida=mme9&grupo=alta",
    );
  });
  it("link do trade centra a ficha no dia do sinal", () => {
    assert.equal(linkDoTrade({ ticker: "PETR4", dataSinal: "2026-10-20" }), "/papel/PETR4?foco=2026-10-20");
  });
});
