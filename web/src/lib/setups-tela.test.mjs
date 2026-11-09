// A aba Setups: secoes, resumo do historico e situacao do alerta.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  agruparPorCategoria,
  alvoDoSetup,
  categoriaDaChave,
  chaveDoBacktest,
  contraOMercado,
  desdeAEntrada,
  etiquetasDoSetup,
  gatilho,
  linhasDoSetup,
  nomeDosPadroes,
  NOME_DO_SETUP,
  resumoDoHistorico,
  nomeDaMedia,
  resultadoEmR,
  rotuloDoEstado,
  separar,
  situacaoDoAlerta,
  stopDoSetup,
  textoAoVivo,
} from "./setups-tela.ts";

function setup(campos) {
  return {
    id: 1,
    ticker: "SAPR11",
    tradeDate: "2026-10-20",
    categoria: "reversao",
    padroes: ["martelo"],
    toques: 3,
    virou: false,
    furou: false,
    rvol: 2.3,
    destaque: false,
    contexto: [],
    fechamento: 40,
    maxima: 40,
    minima: 38.46,
    suporte: 38.5,
    suporteTipo: "nivel",
    resistencia: 45.13,
    espacoR: 3.3,
    riscoPct: 3.85,
    aoVivo: true,
    estado: "armado",
    confirmadoEm: null,
    entrada: null,
    encerradoEm: null,
    saida: null,
    r: { 5: null, 10: null, 20: null },
    m: { 5: null, 10: null, 20: null },
    rc: { 5: null, 10: null, 20: null },
    alta: null,
    saidaRegra: null,
    alerta: null,
    ultimoFechamento: 40,
    ultimoPregao: "2026-10-20",
    pregoesDesde: null,
    ...campos,
  };
}

describe("separar", () => {
  const lista = [
    setup({ id: 1, estado: "armado", rvol: 1.6 }),
    setup({ id: 2, estado: "armado", rvol: 3.1 }),
    setup({ id: 3, estado: "confirmado", confirmadoEm: "2026-10-15" }),
    setup({ id: 4, categoria: "forca", padroes: ["forca"], estado: "armado" }),
    setup({ id: 5, estado: "stop", tradeDate: "2026-10-01", aoVivo: true }),
    setup({ id: 6, estado: "prazo", tradeDate: "2026-09-01", aoVivo: false }),
  ];

  it("armados por volume, so candle de reversao", () => {
    assert.deepEqual(separar(lista, false).armados.map((s) => s.id), [2, 1]);
  });

  it("forca vai a parte, mesmo armada", () => {
    const s = separar(lista, false);
    assert.deepEqual(s.forca.map((x) => x.id), [4]);
    assert.ok(!s.armados.some((x) => x.categoria === "forca"));
  });

  it("historico so com os ao vivo, a menos que se peca os retroativos", () => {
    assert.deepEqual(separar(lista, false).historico.map((s) => s.id), [5]);
    assert.deepEqual(separar(lista, true).historico.map((s) => s.id), [5, 6]);
  });

  it("em andamento e o confirmado", () => {
    assert.deepEqual(separar(lista, false).emAndamento.map((s) => s.id), [3]);
  });
});

describe("resumoDoHistorico", () => {
  it("media contra o mercado so de quem tem 20 pregoes, so reversao", () => {
    const r = resumoDoHistorico([
      setup({ estado: "stop", confirmadoEm: "2026-10-02", r: { 5: 0, 10: 0, 20: 0.05 }, m: { 5: 0, 10: 0, 20: 0.01 } }),
      setup({ estado: "nao_confirmou", r: { 5: 0, 10: 0, 20: -0.02 }, m: { 5: 0, 10: 0, 20: 0.0 } }),
      setup({ estado: "prazo", confirmadoEm: "2026-09-02" }),
      setup({ categoria: "forca", estado: "stop", r: { 5: 0, 10: 0, 20: 0.5 }, m: { 5: 0, 10: 0, 20: 0 } }),
    ]);
    assert.equal(r.setups, 3);
    assert.equal(r.confirmaram, 2);
    assert.equal(r.comResultado, 2);
    assert.ok(Math.abs(r.media20 - 0.01) < 1e-12);
  });

  it("sem resultado ainda, media nula", () => {
    assert.equal(resumoDoHistorico([setup({})]).media20, null);
  });
});

describe("contas", () => {
  it("contra o mercado e desde a entrada", () => {
    const s = setup({ r: { 5: 0.04, 10: null, 20: null }, m: { 5: 0.01, 10: null, 20: null }, entrada: 40, ultimoFechamento: 42 });
    assert.ok(Math.abs(contraOMercado(s, 5) - 0.03) < 1e-12);
    assert.equal(contraOMercado(s, 10), null);
    assert.ok(Math.abs(desdeAEntrada(s) - 0.05) < 1e-12);
  });

  it("nome dos padroes", () => {
    assert.equal(nomeDosPadroes({ padroes: ["martelo", "engolfo"] }), "Martelo + Engolfo de alta");
  });
});

describe("situacaoDoAlerta", () => {
  const alerta = { preco: 40.01, disparadoEm: null, precoDisparo: null, expiraEm: "2026-10-21" };

  it("vigiando ate o pregao da confirmacao", () => {
    assert.equal(situacaoDoAlerta(setup({ alerta }), "2026-10-21"), "alerta vigiando até 21/10");
  });

  it("vencido depois dele", () => {
    assert.equal(situacaoDoAlerta(setup({ alerta }), "2026-10-22"), "alerta venceu sem romper");
  });

  it("disparado mostra a hora de Sao Paulo e o preco", () => {
    const s = setup({ alerta: { ...alerta, disparadoEm: "2026-10-21T13:42:00Z", precoDisparo: 40.05 } });
    assert.equal(situacaoDoAlerta(s, "2026-10-21"), "alerta rompeu às 10:42 a R$ 40,05");
  });

  it("sem alerta, nada", () => {
    assert.equal(situacaoDoAlerta(setup({}), "2026-10-21"), null);
  });
});

describe("na media", () => {
  it("secao propria, fora dos armados e da conferencia da regra principal", () => {
    const lista = [
      setup({ id: 1, estado: "armado" }),
      setup({ id: 2, categoria: "media", suporteTipo: "mme9", estado: "armado" }),
      setup({ id: 3, categoria: "media", suporteTipo: "mma20", estado: "confirmado", confirmadoEm: "2026-10-10" }),
    ];
    const s = separar(lista, false);
    assert.deepEqual(s.armados.map((x) => x.id), [1]);
    assert.deepEqual(s.media.map((x) => x.id), [2, 3]); // armado antes do em andamento
    assert.deepEqual(s.emAndamento, []);
  });

  it("resumo por categoria, sem misturar", () => {
    const fim = { estado: "stop", confirmadoEm: "2026-10-02", r: { 5: 0, 10: 0, 20: 0.02 }, m: { 5: 0, 10: 0, 20: 0 } };
    const lista = [setup({ ...fim }), setup({ ...fim, categoria: "media", r: { 5: 0, 10: 0, 20: -0.04 } })];
    assert.ok(Math.abs(resumoDoHistorico(lista).media20 - 0.02) < 1e-12);
    assert.ok(Math.abs(resumoDoHistorico(lista, "media").media20 + 0.04) < 1e-12);
  });

  it("nome da media", () => {
    assert.equal(nomeDaMedia("nivel"), null);
    assert.equal(nomeDaMedia("mme9"), "MME 9");
    assert.equal(nomeDaMedia("mme9,mma20"), "MME 9 e MMA 20");
  });
});

const PADRAO = {
  reversao: { alerta: true, saida: "alvo3" },
  media: { alerta: false, saida: "alvo3" },
  forca: { alerta: true, saida: "mme9" },
  "9.1": { alerta: false, saida: "mme9" },
  "9.2": { alerta: false, saida: "mme9" },
  "9.3": { alerta: false, saida: "mme9" },
  "9.4": { alerta: true, saida: "mme9" },
  "123": { alerta: false, saida: "alvo3" },
  pfr: { alerta: false, saida: "alvo3" },
  "123_suporte": { alerta: false, saida: "alvo3" },
  pfr_suporte: { alerta: false, saida: "alvo3" },
  mma20: { alerta: false, saida: "alvo3" },
  pullback: { alerta: false, saida: "mme9" },
};

describe("estados novos", () => {
  it("rotulos dos fins das saidas novas", () => {
    assert.equal(rotuloDoEstado("alvo"), "Alvo");
    assert.equal(rotuloDoEstado("movel"), "Stop móvel");
    assert.equal(rotuloDoEstado("mme9"), "MME 9 virou");
  });

  it("linha antiga mantem os rotulos de sempre", () => {
    assert.equal(rotuloDoEstado("stop"), "fechou abaixo da mínima");
    assert.equal(rotuloDoEstado("prazo"), "completou 20 pregões");
    assert.equal(rotuloDoEstado("stop", null), "fechou abaixo da mínima");
  });

  it("com saida escolhida, stop e prazo falam do stop de 1 centavo e do teto", () => {
    assert.equal(rotuloDoEstado("stop", "alvo2"), "Stop");
    assert.equal(rotuloDoEstado("prazo", "mme9"), "Teto de 60 pregões");
  });
});

describe("gatilho, stop e alvo", () => {
  const s = setup({ maxima: 40, minima: 38.5, saidaRegra: "alvo3" });

  it("gatilho um centavo acima da maxima, stop um abaixo da minima", () => {
    assert.equal(gatilho(s), 40.01);
    assert.equal(stopDoSetup(s), 38.49);
  });

  it("sem entrada, o alvo parte do gatilho", () => {
    // 40,01 + 3 x (40,01 - 38,49) = 44,57
    assert.equal(alvoDoSetup(s), 44.57);
  });

  it("com entrada, parte da entrada", () => {
    // 41 + 2 x (41 - 38,49) = 46,02
    assert.equal(alvoDoSetup({ ...s, saidaRegra: "alvo2", entrada: 41 }), 46.02);
    assert.equal(alvoDoSetup({ ...s, saidaRegra: "alvo1", entrada: 41 }), 43.51);
  });

  it("saida que nao e de alvo, ou linha antiga: sem alvo", () => {
    assert.equal(alvoDoSetup({ ...s, saidaRegra: "mme9" }), null);
    assert.equal(alvoDoSetup({ ...s, saidaRegra: "minimas" }), null);
    assert.equal(alvoDoSetup({ ...s, saidaRegra: null }), null);
  });
});

describe("resultadoEmR", () => {
  // entrada 40, stop 38,49: risco 1,51
  const base = { saidaRegra: "mme9", entrada: 40, minima: 38.5 };

  it("encerrado: a saida contra a entrada, em multiplos do risco", () => {
    const r = resultadoEmR(setup({ ...base, estado: "alvo", saida: 44.53 }));
    assert.ok(Math.abs(r - 3) < 1e-9);
    const perda = resultadoEmR(setup({ ...base, estado: "stop", saida: 38.49 }));
    assert.ok(Math.abs(perda + 1) < 1e-9);
  });

  it("em andamento: o ultimo fechamento faz de saida", () => {
    const r = resultadoEmR(setup({ ...base, estado: "confirmado", ultimoFechamento: 41.51 }));
    assert.ok(Math.abs(r - 1) < 1e-9);
  });

  it("linha antiga, armado e sem entrada nao tem R", () => {
    assert.equal(resultadoEmR(setup({ ...base, saidaRegra: null, estado: "stop", saida: 38.49 })), null);
    assert.equal(resultadoEmR(setup({ ...base, estado: "armado", entrada: null })), null);
    assert.equal(resultadoEmR(setup({ ...base, estado: "armado" })), null);
    assert.equal(resultadoEmR(setup({ ...base, estado: "mme9", saida: null })), null);
  });

  it("risco nao positivo nao vira conta", () => {
    assert.equal(resultadoEmR(setup({ ...base, estado: "mme9", saida: 41, entrada: 38.49 })), null);
  });
});

describe("nomes e chaves", () => {
  it("nome de cada setup", () => {
    assert.equal(NOME_DO_SETUP.reversao, "Suporte");
    assert.equal(NOME_DO_SETUP.media, "Na média");
    assert.equal(NOME_DO_SETUP.forca, "Força");
    assert.equal(NOME_DO_SETUP["123"], "1-2-3");
    assert.equal(NOME_DO_SETUP.pfr, "PFR");
    assert.equal(NOME_DO_SETUP.mma20, "MMA 20");
    assert.equal(NOME_DO_SETUP.pullback, "Pullback");
    assert.equal(NOME_DO_SETUP["9.4"], "9.4");
  });

  it("reversao e suporte no backtest; as outras sao iguais", () => {
    assert.equal(chaveDoBacktest("reversao"), "suporte");
    assert.equal(chaveDoBacktest("9.1"), "9.1");
    assert.equal(chaveDoBacktest("media"), "media");
    assert.equal(categoriaDaChave("suporte"), "reversao");
    assert.equal(categoriaDaChave("pfr"), "pfr");
    assert.equal(categoriaDaChave("nada"), null);
  });
});

describe("etiquetas", () => {
  it("tendencia so quando conhecida", () => {
    assert.deepEqual(etiquetasDoSetup(setup({ alta: null, rvol: 1.2 })), []);
    assert.deepEqual(etiquetasDoSetup(setup({ alta: true, rvol: 1.2 })).map((e) => e.texto), ["em alta"]);
    assert.deepEqual(etiquetasDoSetup(setup({ alta: false, rvol: 1.2 })).map((e) => e.texto), [
      "contra a tendência",
    ]);
  });

  it("volume a partir de 1,5x, com a estrela quando marcado", () => {
    assert.deepEqual(etiquetasDoSetup(setup({ rvol: 2.1 })).map((e) => e.texto), ["vol 2,1×"]);
    assert.deepEqual(etiquetasDoSetup(setup({ rvol: 1.5 })).map((e) => e.texto), ["vol 1,5×"]);
    assert.deepEqual(etiquetasDoSetup(setup({ rvol: 2.1, destaque: true })).map((e) => e.texto), [
      "★ vol 2,1×",
    ]);
    assert.deepEqual(etiquetasDoSetup(setup({ rvol: 1.4 })), []);
  });
});

describe("agruparPorCategoria", () => {
  const lista = [
    setup({ id: 1, categoria: "9.4", estado: "armado", rvol: 1.6, saidaRegra: "mme9" }),
    setup({ id: 2, categoria: "9.4", estado: "armado", rvol: 3.1, saidaRegra: "mme9" }),
    setup({ id: 3, categoria: "9.4", estado: "confirmado", confirmadoEm: "2026-10-15" }),
    setup({ id: 4, categoria: "pfr", estado: "armado" }),
    setup({ id: 5, categoria: "reversao", estado: "stop", encerradoEm: "2026-10-10" }),
  ];

  it("separa ligados e outros pelas preferencias, na ordem fixa", () => {
    const { ligados, outros } = agruparPorCategoria(lista, PADRAO);
    assert.deepEqual(ligados.map((b) => b.categoria), ["9.4", "reversao", "forca"]);
    assert.deepEqual(outros.map((b) => b.categoria), [
      "9.1",
      "9.2",
      "9.3",
      "123",
      "pfr",
      "123_suporte",
      "pfr_suporte",
      "mma20",
      "pullback",
      "media",
    ]);
  });

  it("ligar o alerta move o bloco de lugar", () => {
    const prefs = { ...PADRAO, pfr: { alerta: true, saida: "alvo1" } };
    const { ligados, outros } = agruparPorCategoria(lista, prefs);
    assert.ok(ligados.some((b) => b.categoria === "pfr"));
    assert.ok(!outros.some((b) => b.categoria === "pfr"));
    const desligado = agruparPorCategoria(lista, { ...PADRAO, "9.4": { alerta: false, saida: "mme9" } });
    assert.ok(desligado.outros.some((b) => b.categoria === "9.4"));
  });

  it("armados por volume, em andamento e encerrados no bloco do setup", () => {
    const b = agruparPorCategoria(lista, PADRAO).ligados.find((x) => x.categoria === "9.4");
    assert.deepEqual(b.armados.map((s) => s.id), [2, 1]);
    assert.deepEqual(b.emAndamento.map((s) => s.id), [3]);
    assert.deepEqual(b.encerrados, []);
    assert.equal(b.saida, "mme9");
    const r = agruparPorCategoria(lista, PADRAO).ligados.find((x) => x.categoria === "reversao");
    assert.deepEqual(r.encerrados.map((s) => s.id), [5]);
  });

  it("no maximo 10 encerrados, os mais recentes primeiro", () => {
    const muitos = Array.from({ length: 14 }, (_, i) =>
      setup({
        id: 100 + i,
        categoria: "9.1",
        estado: "mme9",
        encerradoEm: `2026-10-${String(i + 1).padStart(2, "0")}`,
      }),
    );
    const b = agruparPorCategoria(muitos, PADRAO).outros.find((x) => x.categoria === "9.1");
    assert.equal(b.encerrados.length, 10);
    assert.equal(b.encerrados[0].id, 113);
  });

  it("bloco sem setup existe, vazio", () => {
    const b = agruparPorCategoria([], PADRAO).outros.find((x) => x.categoria === "123");
    assert.deepEqual([b.armados, b.emAndamento, b.encerrados], [[], [], []]);
  });
});

describe("linhasDoSetup (ficha)", () => {
  const aberto = (campos) =>
    setup({ categoria: "9.4", saidaRegra: "alvo3", maxima: 40, minima: 38.5, ...campos });

  it("armado: gatilho, stop e alvo a partir do gatilho", () => {
    const l = linhasDoSetup([aberto({ estado: "armado" })], PADRAO);
    assert.deepEqual(l, [
      { preco: 40.01, titulo: "entrada", tipo: "entrada" },
      { preco: 38.49, titulo: "stop", tipo: "stop" },
      { preco: 44.57, titulo: "alvo 3R", tipo: "alvo" },
    ]);
  });

  it("em andamento: a entrada de verdade", () => {
    const l = linhasDoSetup([aberto({ estado: "confirmado", entrada: 41, saidaRegra: "alvo1" })], PADRAO);
    assert.equal(l[0].preco, 41);
    assert.equal(l[2].titulo, "alvo 1R");
    assert.equal(l[2].preco, 43.51);
  });

  it("saida que nao e de alvo: so entrada e stop", () => {
    const l = linhasDoSetup([aberto({ estado: "armado", saidaRegra: "mme9" })], PADRAO);
    assert.deepEqual(l.map((x) => x.tipo), ["entrada", "stop"]);
  });

  it("so o mais recente, e so de setup com alerta ligado", () => {
    const l = linhasDoSetup(
      [
        aberto({ id: 1, estado: "armado", tradeDate: "2026-10-19", maxima: 30, minima: 29 }),
        aberto({ id: 2, estado: "confirmado", tradeDate: "2026-10-20", entrada: 41 }),
        aberto({ id: 3, categoria: "pfr", estado: "armado", tradeDate: "2026-10-21" }),
      ],
      PADRAO,
    );
    assert.equal(l[0].preco, 41);
  });

  it("encerrado ou sem alerta: nada", () => {
    assert.deepEqual(linhasDoSetup([aberto({ estado: "stop" })], PADRAO), []);
    assert.deepEqual(linhasDoSetup([aberto({ categoria: "pfr", estado: "armado" })], PADRAO), []);
  });
});

describe("linhas antigas, sem saidaRegra", () => {
  it("continuam como eram: sem R, sem alvo, com o resumo de sempre", () => {
    const s = setup({ estado: "confirmado", entrada: 40, ultimoFechamento: 42, confirmadoEm: "2026-10-15" });
    assert.equal(resultadoEmR(s), null);
    assert.equal(alvoDoSetup(s), null);
    assert.ok(Math.abs(desdeAEntrada(s) - 0.05) < 1e-12);
    assert.deepEqual(separar([s], false).emAndamento.map((x) => x.id), [1]);
  });
});


describe("conferencia ao vivo", () => {
  it("sem encerrado ainda, diz isso", () => {
    assert.match(textoAoVivo(null), /nenhum encerrado ainda/);
    assert.match(textoAoVivo({ n: 0, mediaR: null, acerto: null }), /nenhum encerrado ainda/);
  });
  it("com encerrados, conta, media em R e acerto", () => {
    assert.equal(
      textoAoVivo({ n: 12, mediaR: 0.084, acerto: 0.4167 }),
      "Ao vivo: 12 encerrados · média +0,08 R · acertou 42%",
    );
    assert.equal(
      textoAoVivo({ n: 1, mediaR: -1.02, acerto: 0 }),
      "Ao vivo: 1 encerrado · média \u22121,02 R · acertou 0%",
    );
  });
});


describe("resultado em R do pipeline", () => {
  it("vale sobre a conta com os precos da linha (grupamento no meio do trade)", () => {
    // ENJU3, 09/10/2026: minima 0,72 na escala do candle, entrada 8,30 na do dia seguinte
    const s = {
      saidaRegra: "mme9",
      estado: "confirmado",
      entrada: 8.3,
      saida: null,
      ultimoFechamento: 8.24,
      minima: 0.72,
      resultadoR: -0.07,
    };
    assert.equal(resultadoEmR(s), -0.07);
    assert.ok(Math.abs(resultadoEmR({ ...s, resultadoR: null }) - (8.24 - 8.3) / (8.3 - 0.71)) < 1e-9);
  });
  it("armado e nao confirmado nao tem resultado", () => {
    const base = { saidaRegra: "alvo2", entrada: null, saida: null, ultimoFechamento: 10, minima: 9, resultadoR: null };
    assert.equal(resultadoEmR({ ...base, estado: "armado" }), null);
    assert.equal(resultadoEmR({ ...base, estado: "nao_confirmou" }), null);
  });
});
