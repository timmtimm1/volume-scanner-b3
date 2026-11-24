// A analise contra o Bitcoin: tabela, filtro, ordem, sazonalidade e cores.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  ANOS_DA_CONFERENCIA,
  ANOS_DA_ESCOLHA,
  MESES_CURTOS,
  MINIMO_DE_ANOS,
  alturaDaBarra,
  anosDaJanela,
  escolhidaDoLado,
  explicacaoDoVeredito,
  melhorEPiorMes,
  perfilDaCesta,
  primeirasDoLado,
  rotuloDaJanela,
  tetoDasBarras,
  corDaCelula,
  filtrarLinhas,
  mapaMensal,
  montarSazonalidade,
  montarTabela,
  nivelDeCor,
  ordenarLinhas,
  ordenarSazonalidade,
  pctCurto,
  rankear,
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

describe("filtrarLinhas genérico", () => {
  it("funciona com linhas de sazonalidade e mantém o BTC", () => {
    const linhas = montarSazonalidade(
      [moeda("BTC"), moeda("ETH"), moeda("XYZ", { negociando: false })],
      [],
    );
    const r = filtrarLinhas(linhas, { busca: "xy", grupo: "todas" });
    assert.deepEqual(r.map((l) => l.moeda), ["BTC", "XYZ"]);
    const so = filtrarLinhas(linhas, { busca: "", grupo: "negociando" });
    assert.deepEqual(so.map((l) => l.moeda), ["BTC", "ETH"]);
  });
});

const mes = (m, n, retorno, relativo, anos, extra = {}) => ({
  moeda: m,
  mes: n,
  retorno,
  relativo,
  subiu: Math.floor(anos / 2),
  ganhou: Math.floor(anos / 3),
  anos,
  ...extra,
});

describe("montarSazonalidade", () => {
  it("junta os meses por moeda e arredonda", () => {
    const linhas = montarSazonalidade(
      [moeda("BTC"), moeda("ETH", { volume12m: 123456.789 })],
      [mes("ETH", 3, 0.123456789, -0.0123456, 5), mes("ETH", 13, 1, 1, 5), mes("ZZZ", 1, 1, 1, 5)],
    );
    assert.equal(linhas.length, 2);
    const eth = linhas[1];
    assert.equal(eth.volume12m, 123500);
    assert.equal(eth.porMes[3].retorno, 0.1235);
    assert.equal(eth.porMes[3].relativo, -0.01235);
    assert.equal(eth.porMes[3].anos, 5);
    assert.equal(eth.porMes[13], undefined);
    assert.deepEqual(linhas[0].porMes, {});
  });
});

describe("ordenarSazonalidade", () => {
  const linhas = montarSazonalidade(
    [
      moeda("BTC", { volume12m: 1 }),
      moeda("AAA", { volume12m: 50 }),
      moeda("BBB", { volume12m: 90 }),
      moeda("CCC", { volume12m: 70 }),
      moeda("DDD", { volume12m: 10 }),
    ],
    [
      mes("BTC", 1, -0.5, null, 8),
      mes("AAA", 1, 0.1, 0.3, 5),
      mes("BBB", 1, 0.2, -0.2, 4),
      mes("CCC", 1, 0.9, 0.9, MINIMO_DE_ANOS - 1),
      // DDD nao tem janeiro
    ],
  );
  const nomes = (l) => l.map((x) => x.moeda);

  it("por mes, no modo escolhido, com BTC primeiro", () => {
    assert.deepEqual(nomes(ordenarSazonalidade(linhas, 1, "retorno", "desc")), [
      "BTC",
      "BBB",
      "AAA",
      "CCC",
      "DDD",
    ]);
    assert.deepEqual(nomes(ordenarSazonalidade(linhas, 1, "relativo", "desc")).slice(0, 3), [
      "BTC",
      "AAA",
      "BBB",
    ]);
  });

  it("poucos anos e sem dado ficam por ultimo nos dois sentidos", () => {
    const asc = nomes(ordenarSazonalidade(linhas, 1, "retorno", "asc"));
    assert.deepEqual(asc.slice(0, 3), ["BTC", "AAA", "BBB"]);
    assert.deepEqual(asc.slice(3).sort(), ["CCC", "DDD"]);
    const desc = nomes(ordenarSazonalidade(linhas, 1, "retorno", "desc"));
    assert.deepEqual(desc.slice(3).sort(), ["CCC", "DDD"]);
  });

  it("por volume", () => {
    assert.deepEqual(nomes(ordenarSazonalidade(linhas, "volume", "retorno", "desc")), [
      "BTC",
      "BBB",
      "CCC",
      "AAA",
      "DDD",
    ]);
  });

  it("nao mexe na lista original", () => {
    const antes = nomes(linhas);
    ordenarSazonalidade(linhas, 1, "retorno", "asc");
    assert.deepEqual(nomes(linhas), antes);
  });
});

describe("rankear", () => {
  const cand = (m, b90, c90, extra = {}) => ({
    moeda: m,
    beta90: b90,
    correlacao90: c90,
    dias90: 90,
    betaAno: b90 === null ? null : b90 + 1,
    correlacaoAno: c90 === null ? null : c90 + 0.1,
    diasAno: 300,
    betaTotal: null,
    correlacaoTotal: null,
    diasTotal: 2000,
    desde: "2018-01-01",
    ...extra,
  });
  const todos = [
    cand("AAA", 1.5, 0.8),
    cand("BTC", 1, 1),
    cand("CCC", 2.5, -0.2),
    cand("BBB", 2.5, 0.1),
    cand("DDD", null, 0.05),
    cand("EEE", 0.5, null),
  ];

  it("beta: do maior para o menor, empate pelo nome, sem BTC nem nulos", () => {
    const r = rankear(todos, "90d", "beta");
    assert.deepEqual(r.map((x) => x.moeda), ["BBB", "CCC", "AAA", "EEE"]);
    assert.equal(r[0].valor, 2.5);
    assert.equal(r[0].outro, 0.1);
    assert.equal(r[0].dias, 90);
    assert.equal(r[3].outro, null);
  });

  it("correlacao: do menor para o maior, negativas primeiro", () => {
    const r = rankear(todos, "90d", "correlacao");
    assert.deepEqual(r.map((x) => x.moeda), ["CCC", "DDD", "BBB", "AAA"]);
    assert.equal(r[0].valor, -0.2);
    assert.equal(r[1].outro, null);
  });

  it("usa o periodo pedido", () => {
    const r = rankear(todos, "ano", "beta");
    assert.equal(r[0].valor, 3.5);
    assert.equal(r[0].dias, 300);
    assert.deepEqual(rankear(todos, "total", "beta"), []);
  });

  it("respeita n", () => {
    assert.equal(rankear(todos, "90d", "beta", 2).length, 2);
    assert.equal(rankear(todos, "90d", "beta", 0).length, 0);
    const muitos = Array.from({ length: 40 }, (_, i) => cand(`M${String(i).padStart(2, "0")}`, i, 0.5));
    assert.equal(rankear(muitos, "90d", "beta").length, 15);
  });
});

// ---------------------------------------------------------------------------
// Estudo sazonal
// ---------------------------------------------------------------------------

const janela = (lado, inicioMes, meses, posicao, extra = {}) => ({
  lado,
  inicioMes,
  meses,
  posicao,
  veredito: "em parte",
  escolhaMedia: 2.73,
  escolhaMediana: 0.5,
  escolhaPositivos: 2,
  escolhaAnos: 4,
  escolhaControle: 0.76,
  conferenciaMedia: -0.005,
  conferenciaMediana: -0.1,
  conferenciaPositivos: 1,
  conferenciaAnos: 4,
  conferenciaControle: -0.094,
  todosMedia: 0,
  todosMediana: 0,
  todosPositivos: 0,
  todosAnos: 8,
  ...extra,
});

describe("rotuloDaJanela", () => {
  it("um mes, varios meses e a virada do ano", () => {
    assert.equal(rotuloDaJanela(4, 1), "abr");
    assert.equal(rotuloDaJanela(5, 6), "mai a out");
    assert.equal(rotuloDaJanela(11, 6), "nov a abr");
    assert.equal(rotuloDaJanela(12, 2), "dez a jan");
    assert.equal(rotuloDaJanela(1, 12), "jan a dez");
    assert.equal(MESES_CURTOS.length, 12);
  });
});

describe("escolhida e primeiras", () => {
  const js = [
    janela("compra", 3, 2, 3),
    janela("compra", 11, 6, 1),
    janela("venda", 6, 6, 1),
    janela("compra", 1, 1, null),
    janela("compra", 7, 3, 2),
    janela("compra", 2, 4, 7),
  ];

  it("escolhida: a posicao 1 do lado, ou null", () => {
    assert.equal(escolhidaDoLado(js, "compra").inicioMes, 11);
    assert.equal(escolhidaDoLado(js, "venda").inicioMes, 6);
    assert.equal(escolhidaDoLado([janela("compra", 1, 1, null)], "compra"), null);
    assert.equal(escolhidaDoLado([], "venda"), null);
  });

  it("primeiras: ordenadas, sem nulos nem alem de n", () => {
    assert.deepEqual(primeirasDoLado(js, "compra").map((j) => j.posicao), [1, 2, 3]);
    assert.deepEqual(primeirasDoLado(js, "compra", 2).map((j) => j.posicao), [1, 2]);
    assert.deepEqual(primeirasDoLado(js, "venda").map((j) => j.posicao), [1]);
  });
});

describe("anosDaJanela", () => {
  it("so a janela pedida, do ano mais antigo ao mais novo", () => {
    const a = (lado, ano, resultado, inicioMes = 11, meses = 6) => ({
      lado,
      inicioMes,
      meses,
      ano,
      periodo: ano <= 2021 ? "escolha" : "conferencia",
      resultado,
    });
    const r = anosDaJanela(
      [a("compra", 2019, 1), a("compra", 2017, 2), a("venda", 2018, 3), a("compra", 2018, 4, 5), a("compra", 2018, 5)],
      "compra",
      11,
      6,
    );
    assert.deepEqual(r.map((x) => x.ano), [2017, 2018, 2019]);
  });
});

describe("perfilDaCesta", () => {
  const cesta = [
    { mes: "2018-04-01", retorno: 0.2, retornoBtc: 0.1, moedas: 7 },
    { mes: "2019-04-01", retorno: -0.1, retornoBtc: null, moedas: 20 },
    { mes: "2020-04-01", retorno: 0.4, retornoBtc: 0.3, moedas: 50 },
    { mes: "2018-06-01", retorno: -0.3, retornoBtc: -0.2, moedas: 7 },
  ];

  it("sempre 12 meses; media, mediana, subiu e anos", () => {
    const p = perfilDaCesta(cesta);
    assert.equal(p.length, 12);
    assert.deepEqual(p.map((x) => x.mes), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
    const abril = p[3];
    assert.ok(Math.abs(abril.media - 0.5 / 3) < 1e-12);
    assert.equal(abril.mediana, 0.2);
    assert.equal(abril.subiu, 2);
    assert.equal(abril.anos, 3);
    assert.ok(Math.abs(abril.mediaBtc - 0.2) < 1e-12);
  });

  it("mes sem dado fica vazio", () => {
    const janeiro = perfilDaCesta(cesta)[0];
    assert.equal(janeiro.media, null);
    assert.equal(janeiro.mediana, null);
    assert.equal(janeiro.mediaBtc, null);
    assert.equal(janeiro.anos, 0);
  });

  it("mediana de quantidade par e o meio dos dois", () => {
    const p = perfilDaCesta([
      { mes: "2018-02-01", retorno: 0.1, retornoBtc: null, moedas: 5 },
      { mes: "2019-02-01", retorno: 0.3, retornoBtc: null, moedas: 5 },
    ]);
    assert.ok(Math.abs(p[1].mediana - 0.2) < 1e-12);
  });
});

describe("melhorEPiorMes", () => {
  const item = (mes, mediana, subiu = 0, anos = 0) => ({ mes, media: mediana, mediana, subiu, anos, mediaBtc: null });

  it("pela mediana, empate no mes mais cedo", () => {
    const r = melhorEPiorMes([item(3, 0.1), item(4, 0.14), item(5, 0.14), item(6, -0.21), item(7, -0.21)]);
    assert.equal(r.melhor.mes, 4);
    assert.equal(r.pior.mes, 6);
  });

  it("ignora quem nao tem mediana; sem dado, null", () => {
    const r = melhorEPiorMes([item(1, null), item(2, 0.05)]);
    assert.equal(r.melhor.mes, 2);
    assert.equal(r.pior.mes, 2);
    assert.equal(melhorEPiorMes([item(1, null)]), null);
    assert.equal(melhorEPiorMes([]), null);
  });
});

describe("explicacaoDoVeredito", () => {
  it("repetiu", () => {
    const t = explicacaoDoVeredito(janela("compra", 4, 1, 1, { veredito: "repetiu" }));
    assert.match(t, /voltou a dar lucro e a ganhar de uma janela qualquer/);
    assert.ok(t.includes(ANOS_DA_ESCOLHA) && t.includes(ANOS_DA_CONFERENCIA));
  });

  it("em parte diz qual das duas aconteceu", () => {
    const ganhouSemLucro = explicacaoDoVeredito(janela("compra", 4, 1, 1)); // -0,5% contra -9,4%
    assert.match(ganhouSemLucro, /ganhou de uma janela qualquer, mas não deu lucro/);
    const lucroSemGanhar = explicacaoDoVeredito(
      janela("compra", 4, 1, 1, { conferenciaMedia: 0.1, conferenciaControle: 0.3 }),
    );
    assert.match(lucroSemGanhar, /deu lucro, mas não ganhou de uma janela qualquer/);
  });

  it("nao repetiu e sem conferencia", () => {
    assert.match(
      explicacaoDoVeredito(janela("venda", 6, 6, 1, { veredito: "nao repetiu" })),
      /não deu lucro nem ganhou de uma janela qualquer/,
    );
    assert.equal(
      explicacaoDoVeredito(janela("venda", 6, 6, 1, { veredito: "sem conferencia" })),
      "Ainda não há anos de conferência.",
    );
  });
});

describe("barras dos anos", () => {
  it("teto: 1,2 vez o segundo maior, sem passar do maior", () => {
    assert.ok(Math.abs(tetoDasBarras([5, -0.5, 0.25]) - 0.6) < 1e-12);
    assert.equal(tetoDasBarras([1, -0.9]), 1);
    assert.equal(tetoDasBarras([0.4]), 0.4);
    assert.equal(tetoDasBarras([]), 1);
    assert.equal(tetoDasBarras([0, 0]), 1);
    assert.equal(tetoDasBarras([3, 0]), 3);
  });

  it("altura: fracao do teto e marca de corte", () => {
    const teto = tetoDasBarras([5, -0.5, 0.25]);
    assert.deepEqual(alturaDaBarra(5, teto), { fracao: 1, cortada: true });
    assert.equal(alturaDaBarra(-0.3, teto).fracao, 0.5);
    assert.equal(alturaDaBarra(-0.3, teto).cortada, false);
    assert.equal(alturaDaBarra(0, teto).fracao, 0);
  });
});
