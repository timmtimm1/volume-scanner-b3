// Entradas de hoje: a nota do semaforo, as contas do cartao e a ordem da lista.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  contarPorCor,
  corDaNota,
  desenharCandles,
  grupoDoPapel,
  montarEntrada,
  notaDaLinha,
  ordenarEntradas,
  separarPeloBolso,
  textoDaDuracao,
} from "./entradas.ts";

const linha = (extra = {}) => ({
  setup: "forca",
  saida: "mme9",
  grupo: "alta",
  periodo: "2016-2026",
  n: 400,
  acerto: 0.39,
  ganhoMedio: 1.7,
  diasMedio: 10.3,
  expectativa: 0.31,
  icBaixo: 0.09,
  diferenca: 0.3,
  piorSequencia: 8,
  piorRecuo: -20.5,
  ...extra,
});

const setup = (extra = {}) => ({ ticker: "PETR4", alta: true, rvol: 1, ...extra });

const lote = (quantidade, porAcao) => ({
  quantidade,
  perdaMaxima: quantidade * porAcao,
  valorPosicao: 0,
  pctDoCapital: 0,
  limitadoPeloCapital: false,
});

const base = (extra = {}) => ({
  setup: setup(),
  chave: "forca",
  gatilho: 40,
  stop: 39,
  saida: "mme9",
  lote: lote(10, 1),
  ...extra,
});

describe("nota do semaforo", () => {
  it("segue os tres niveis do backtest", () => {
    assert.equal(notaDaLinha(linha()), "firme");
    assert.equal(notaDaLinha(linha({ icBaixo: -0.05 })), "fraco");
    assert.equal(notaDaLinha(linha({ expectativa: -0.01 })), "falhou");
  });

  it("lucro que perde do controle e falhou", () => {
    assert.equal(notaDaLinha(linha({ diferenca: -0.02 })), "falhou");
  });

  it("sem linha ou sem trade nao tem nota", () => {
    assert.equal(notaDaLinha(undefined), null);
    assert.equal(notaDaLinha(linha({ n: 0 })), null);
    assert.equal(corDaNota(null), "cinza");
  });

  it("cada nota tem a sua cor", () => {
    assert.deepEqual(["firme", "fraco", "falhou"].map(corDaNota), ["verde", "amarelo", "vermelho"]);
  });

  it("a tendencia do papel escolhe o grupo", () => {
    assert.deepEqual([true, false, null].map(grupoDoPapel), ["alta", "contra", "todos"]);
  });
});

describe("montarEntrada", () => {
  const linhas = [linha(), linha({ periodo: "tudo", expectativa: 0.2 })];

  it("saida sem alvo: so o ganho medio historico", () => {
    const e = montarEntrada(base(), linhas);
    assert.equal(e.riscoPct, 0.025);
    assert.equal(e.alvo, null);
    assert.equal(e.alvoPct, null);
    // 1,7 R x 2,5% de risco
    assert.ok(Math.abs(e.ganhoMedioPct - 0.0425) < 1e-12);
    assert.equal(e.perdaEmReais, 10);
    assert.equal(e.ganhoMedioEmReais, 17);
    assert.equal(e.cor, "verde");
    assert.equal(e.piorSequencia, 8);
    assert.equal(e.piorRecuoEmReais, -205);
  });

  it("alvo de 3R: preco, percentual e reais", () => {
    const e = montarEntrada(base({ saida: "alvo3" }), [
      linha({ saida: "alvo3" }),
      linha({ saida: "alvo3", periodo: "tudo" }),
    ]);
    assert.equal(e.multiplo, 3);
    assert.equal(e.alvo, 43);
    assert.ok(Math.abs(e.alvoPct - 0.075) < 1e-12);
    assert.equal(e.alvoEmReais, 30);
  });

  it("a nota e a do grupo do papel, nao a do setup", () => {
    const contra = base({ setup: setup({ alta: false }) });
    // so ha linha de "alta": contra a tendencia fica sem historico
    assert.equal(montarEntrada(contra, linhas).cor, "cinza");
    const comLinha = [...linhas, linha({ grupo: "contra", expectativa: -0.1 })];
    assert.equal(montarEntrada(contra, comLinha).cor, "vermelho");
  });

  it("sem capital informado: sem reais, mas cabe", () => {
    const e = montarEntrada(base({ lote: null }), linhas);
    assert.equal(e.perdaEmReais, null);
    assert.equal(e.piorRecuoEmReais, null);
    assert.equal(e.cabe, true);
  });

  it("lote zero nao cabe no bolso", () => {
    const e = montarEntrada(base({ lote: lote(0, 1) }), linhas);
    assert.equal(e.cabe, false);
    assert.equal(e.perdaEmReais, null);
    const { cabem, naoCabem } = separarPeloBolso([e, montarEntrada(base(), linhas)]);
    assert.equal(cabem.length, 1);
    assert.equal(naoCabem.length, 1);
  });

  it("rodada antiga, sem pior fase: os campos ficam nulos", () => {
    const antigas = linhas.map((l) => ({ ...l, piorSequencia: null, piorRecuo: null }));
    const e = montarEntrada(base(), antigas);
    assert.equal(e.piorSequencia, null);
    assert.equal(e.piorRecuoEmReais, null);
  });
});

describe("ordem da lista", () => {
  it("verde, amarelo, vermelho, sem historico; depois o volume", () => {
    const de = (cor, ticker, rvol) => ({ cor, setup: setup({ ticker, rvol }) });
    const lista = ordenarEntradas([
      de("vermelho", "A", 9),
      de("cinza", "B", 9),
      de("verde", "C", 1),
      de("amarelo", "D", 1),
      de("verde", "E", 3),
    ]);
    assert.deepEqual(lista.map((e) => e.setup.ticker), ["E", "C", "D", "A", "B"]);
    assert.deepEqual(contarPorCor(lista), [
      { cor: "verde", n: 2 },
      { cor: "amarelo", n: 1 },
      { cor: "vermelho", n: 1 },
      { cor: "cinza", n: 1 },
    ]);
  });
});

describe("textos e desenho", () => {
  it("duracao arredonda e nunca diz zero", () => {
    assert.equal(textoDaDuracao(10.3), "dura ~10 pregões");
    assert.equal(textoDaDuracao(0.4), "dura ~1 pregão");
    assert.equal(textoDaDuracao(null), null);
  });

  it("a escala do mini grafico inclui os precos marcados", () => {
    const candles = [
      { dia: "2026-11-09", abre: 10, maxima: 11, minima: 9, fecha: 10.5 },
      { dia: "2026-11-10", abre: 10.5, maxima: 10.6, minima: 10, fecha: 10.1 },
    ];
    const d = desenharCandles(candles, [13, 8], 100, 50);
    assert.equal(d.y(13), 0);
    assert.equal(d.y(8), 50);
    assert.equal(d.candles.length, 2);
    assert.equal(d.candles[0].subiu, true);
    assert.equal(d.candles[1].subiu, false);
    assert.ok(d.candles[0].pavioDe < d.candles[0].corpoDe);
  });

  it("sem candles nao quebra", () => {
    const d = desenharCandles([], [], 100, 50);
    assert.deepEqual(d.candles, []);
  });
});
