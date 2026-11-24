// A analise contra o Bitcoin: tabela, filtro, ordem, sazonalidade e cores.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  corDaCelula,
  filtrarLinhas,
  mapaMensal,
  montarTabela,
  nivelDeCor,
  ordenarLinhas,
  pctCurto,
  sazonalidade,
} from "./analise.ts";

const moeda = (m, extra = {}) => ({
  moeda: m,
  fonte: "binance",
  negociando: true,
  primeiroDia: "2017-08-17",
  ultimoDia: "2026-11-23",
  volume12m: 1000,
  noTop: false,
  ...extra,
});

const anual = (m, ano, relativo, extra = {}) => ({
  moeda: m,
  ano,
  inicio: `${ano || 2020}-01-01`,
  fim: `${ano || 2026}-12-31`,
  parcial: false,
  retorno: relativo,
  retornoBtc: 0.1,
  relativo,
  beta: null,
  correlacao: null,
  dias: 365,
  ...extra,
});

const mensal = (mes, valor, parcial = false) => ({
  moeda: "ETH",
  mes,
  inicio: mes,
  fim: mes,
  parcial,
  retorno: valor,
  retornoBtc: 0,
  relativo: valor,
});

describe("montarTabela", () => {
  const moedas = [moeda("BTC", { volume12m: 5000 }), moeda("ETH"), moeda("XYZ", { negociando: false })];
  const anuais = [
    anual("BTC", 2024, 0),
    anual("BTC", 2025, 0),
    anual("ETH", 2023, 0.123456),
    anual("ETH", 2025, -0.2),
    anual("ETH", 0, 1.23456, { beta: 1.23456, correlacao: 0.87654 }),
    anual("SUMIDA", 2025, 1),
  ];
  const { anos, linhas } = montarTabela(moedas, anuais);

  it("anos do mais novo para o mais antigo, sem o 0", () => {
    assert.deepEqual(anos, [2025, 2024, 2023]);
  });

  it("uma linha por moeda, na ordem recebida, e ignora anual sem moeda", () => {
    assert.deepEqual(
      linhas.map((l) => l.moeda),
      ["BTC", "ETH", "XYZ"],
    );
  });

  it("separa o periodo todo em total e arredonda para 4 algarismos", () => {
    const eth = linhas[1];
    assert.equal(eth.porAno[2023].relativo, 0.1235);
    assert.equal(eth.porAno[2025].relativo, -0.2);
    assert.equal(eth.porAno[0], undefined);
    assert.equal(eth.total.relativo, 1.235);
    assert.equal(eth.total.beta, 1.235);
    assert.equal(eth.total.correlacao, 0.8765);
    assert.equal(eth.porAno[2023].beta, undefined);
  });

  it("moeda sem periodo todo fica com total nulo; nulo continua nulo", () => {
    assert.equal(linhas[2].total, null);
    assert.equal(linhas[2].negociando, false);
    const { linhas: l } = montarTabela([moeda("A", { volume12m: null })], [anual("A", 2024, null)]);
    assert.equal(l[0].volume12m, null);
    assert.equal(l[0].porAno[2024].relativo, null);
  });
});

describe("filtrarLinhas", () => {
  const { linhas } = montarTabela(
    [
      moeda("BTC"),
      moeda("ETH", { noTop: true }),
      moeda("SOL", { noTop: true }),
      moeda("LUNA", { negociando: false }),
      moeda("DOGE"),
    ],
    [],
  );
  const nomes = (l) => l.map((x) => x.moeda);

  it("todas sem busca devolve tudo", () => {
    assert.equal(filtrarLinhas(linhas, { busca: "", grupo: "todas" }).length, 5);
  });

  it("negociando tira as paradas", () => {
    assert.deepEqual(nomes(filtrarLinhas(linhas, { busca: "", grupo: "negociando" })), [
      "BTC",
      "ETH",
      "SOL",
      "DOGE",
    ]);
  });

  it("top50 deixa so as da aba Cripto, e o BTC fica", () => {
    assert.deepEqual(nomes(filtrarLinhas(linhas, { busca: "", grupo: "top50" })), ["BTC", "ETH", "SOL"]);
  });

  it("busca ignora maiuscula e acha pedaco, mas nunca tira o BTC", () => {
    assert.deepEqual(nomes(filtrarLinhas(linhas, { busca: "  so", grupo: "todas" })), ["BTC", "SOL"]);
    assert.deepEqual(nomes(filtrarLinhas(linhas, { busca: "zzz", grupo: "todas" })), ["BTC"]);
    assert.deepEqual(nomes(filtrarLinhas(linhas, { busca: "luna", grupo: "negociando" })), ["BTC"]);
  });
});

describe("ordenarLinhas", () => {
  const { linhas } = montarTabela(
    [
      moeda("A", { volume12m: 10 }),
      moeda("BTC", { volume12m: 1 }),
      moeda("B", { volume12m: null }),
      moeda("C", { volume12m: 30 }),
      moeda("D", { volume12m: 20 }),
    ],
    [
      anual("A", 2025, 0.5),
      anual("C", 2025, -0.4),
      anual("D", 2024, 0.1),
      anual("A", 0, 2, { beta: 1.5, correlacao: 0.5 }),
      anual("C", 0, -0.5, { beta: 0.8, correlacao: 0.9 }),
    ],
  );
  const nomes = (l) => l.map((x) => x.moeda);

  it("volume: BTC primeiro, maior ao menor, sem volume por ultimo", () => {
    assert.deepEqual(nomes(ordenarLinhas(linhas, "volume", "desc")), ["BTC", "C", "D", "A", "B"]);
  });

  it("sem dado fica por ultimo tambem no sentido crescente", () => {
    assert.deepEqual(nomes(ordenarLinhas(linhas, "volume", "asc")), ["BTC", "A", "D", "C", "B"]);
  });

  it("ano ordena pelo relativo daquele ano; quem nao tem o ano vai ao fim", () => {
    assert.deepEqual(nomes(ordenarLinhas(linhas, 2025, "desc")), ["BTC", "A", "C", "B", "D"]);
    assert.deepEqual(nomes(ordenarLinhas(linhas, 2025, "asc")), ["BTC", "C", "A", "B", "D"]);
  });

  it("total, beta e correlacao olham o periodo todo", () => {
    assert.deepEqual(nomes(ordenarLinhas(linhas, "total", "desc")).slice(0, 3), ["BTC", "A", "C"]);
    assert.deepEqual(nomes(ordenarLinhas(linhas, "beta", "asc")).slice(0, 3), ["BTC", "C", "A"]);
    assert.deepEqual(nomes(ordenarLinhas(linhas, "correlacao", "desc")).slice(0, 3), ["BTC", "C", "A"]);
  });

  it("nao mexe na lista original", () => {
    const antes = nomes(linhas);
    ordenarLinhas(linhas, "volume", "desc");
    assert.deepEqual(nomes(linhas), antes);
  });
});

describe("sazonalidade", () => {
  it("devolve 12 meses, vazios quando nao ha dado", () => {
    const s = sazonalidade([], "relativo");
    assert.equal(s.length, 12);
    assert.deepEqual(s[0], { mes: 1, mediana: null, positivos: 0, meses: 0 });
    assert.equal(s[11].mes, 12);
  });

  it("mediana de quantidade impar e o do meio, nao a media", () => {
    const s = sazonalidade(
      [mensal("2021-03-01", 0.1), mensal("2022-03-01", 0.2), mensal("2023-03-01", 9.0)],
      "relativo",
    );
    assert.equal(s[2].mediana, 0.2);
    assert.equal(s[2].meses, 3);
    assert.equal(s[2].positivos, 3);
  });

  it("mediana de quantidade par e a media dos dois do meio", () => {
    const s = sazonalidade(
      [mensal("2021-05-01", -0.1), mensal("2022-05-01", 0.3), mensal("2023-05-01", 0.1), mensal("2024-05-01", 5)],
      "relativo",
    );
    assert.equal(s[4].mediana, 0.2);
    assert.equal(s[4].positivos, 3);
    assert.equal(s[4].meses, 4);
  });

  it("mes incompleto e nulo ficam fora", () => {
    const s = sazonalidade(
      [mensal("2021-07-01", 0.1), mensal("2022-07-01", 9, true), mensal("2023-07-01", null)],
      "relativo",
    );
    assert.equal(s[6].meses, 1);
    assert.equal(s[6].mediana, 0.1);
  });

  it("campo retorno usa o retorno em dolar", () => {
    const m = { ...mensal("2021-01-01", 0.5), retorno: -0.1 };
    const s = sazonalidade([m], "retorno");
    assert.equal(s[0].mediana, -0.1);
    assert.equal(s[0].positivos, 0);
  });
});

describe("mapaMensal", () => {
  const mapa = mapaMensal([mensal("2023-02-01", 0.1), mensal("2025-11-01", 0.2), mensal("2025-01-01", 0.3)]);
  it("anos do mais novo para o mais antigo", () => {
    assert.deepEqual(mapa.anos, [2025, 2023]);
  });
  it("acha a celula por ano e mes, e devolve undefined quando nao ha", () => {
    assert.equal(mapa.celula(2025, 11).relativo, 0.2);
    assert.equal(mapa.celula(2023, 2).relativo, 0.1);
    assert.equal(mapa.celula(2024, 6), undefined);
  });
});

describe("nivelDeCor", () => {
  it("escala do ano, nos limites", () => {
    assert.equal(nivelDeCor(0.0499, "ano"), 0);
    assert.equal(nivelDeCor(0.05, "ano"), 1);
    assert.equal(nivelDeCor(0.1499, "ano"), 1);
    assert.equal(nivelDeCor(0.15, "ano"), 2);
    assert.equal(nivelDeCor(0.35, "ano"), 3);
    assert.equal(nivelDeCor(0.75, "ano"), 4);
    assert.equal(nivelDeCor(50, "ano"), 4);
  });

  it("escala do mes, nos limites", () => {
    assert.equal(nivelDeCor(0.0199, "mes"), 0);
    assert.equal(nivelDeCor(0.02, "mes"), 1);
    assert.equal(nivelDeCor(0.05, "mes"), 2);
    assert.equal(nivelDeCor(0.1, "mes"), 3);
    assert.equal(nivelDeCor(0.2, "mes"), 4);
  });

  it("olha o tamanho, nao o sinal; nulo e nivel 0", () => {
    assert.equal(nivelDeCor(-0.4, "ano"), 3);
    assert.equal(nivelDeCor(null, "ano"), 0);
  });
});

describe("corDaCelula", () => {
  it("transparente abaixo do primeiro limite e para nulo", () => {
    assert.equal(corDaCelula(0.01, "ano"), "transparent");
    assert.equal(corDaCelula(null, "mes"), "transparent");
  });

  it("verde para quem ganhou, vermelho para quem perdeu, mais forte com o tamanho", () => {
    assert.equal(corDaCelula(0.05, "ano"), "color-mix(in srgb, var(--alta) 14%, transparent)");
    assert.equal(corDaCelula(0.2, "ano"), "color-mix(in srgb, var(--alta) 26%, transparent)");
    assert.equal(corDaCelula(-0.5, "ano"), "color-mix(in srgb, var(--baixa) 40%, transparent)");
    assert.equal(corDaCelula(-0.8, "ano"), "color-mix(in srgb, var(--baixa) 56%, transparent)");
    assert.equal(corDaCelula(0.2, "mes"), "color-mix(in srgb, var(--alta) 56%, transparent)");
  });
});

describe("pctCurto", () => {
  it("uma casa abaixo de 10%, nenhuma de 10% para cima", () => {
    assert.equal(pctCurto(0.042), "+4,2%");
    assert.equal(pctCurto(-0.0449), "−4,5%");
    assert.equal(pctCurto(0.1), "+10%");
    assert.equal(pctCurto(-0.45), "−45%");
    assert.equal(pctCurto(0.456), "+46%");
  });

  it("milhar com ponto", () => {
    assert.equal(pctCurto(107.5), "+10.750%");
  });

  it("so a perda total mostra −100%; perto dela ganha casas", () => {
    assert.equal(pctCurto(-1), "−100%");
    assert.equal(pctCurto(-0.9962), "−99,62%");
    assert.equal(pctCurto(-0.9999999), "−99,99%");
    assert.equal(pctCurto(-0.994), "−99%");
  });

  it("nulo vira travessao; o que arredonda para zero fica sem sinal", () => {
    assert.equal(pctCurto(null), "—");
    assert.equal(pctCurto(undefined), "—");
    assert.equal(pctCurto(Number.NaN), "—");
    assert.equal(pctCurto(0), "0,0%");
    assert.equal(pctCurto(-0.00001), "0,0%");
  });
});
