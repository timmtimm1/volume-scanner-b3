// A logica pura da aba Semana: periodo, hora de Brasilia, vizinhas, agenda, bp.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  agruparAgenda,
  descartesEmTexto,
  detalheDoAjuste,
  diaComSemana,
  diaEmBrasilia,
  ehErro,
  instanteEmBrasilia,
  mesDeReferencia,
  periodoDaSemana,
  pontosBase,
  prazoDoTreasury,
  sextaValida,
  soQuemCaiu,
  soQuemSubiu,
  tickersDasAcoes,
  vizinhas,
} from "./semana.ts";

const acao = (extra = {}) => ({
  ticker: "BBDC4",
  variacao: -0.041,
  variacao_bruta: -0.058,
  preco_inicio: 21.61,
  preco_fim: 20.36,
  data_inicio: "2026-10-09",
  data_fim: "2026-10-16",
  ajustado: true,
  multiplicador: 1,
  proventos_por_acao: 0.356,
  conferido: true,
  eventos_sem_ajuste: null,
  ...extra,
});

describe("sextaValida", () => {
  it("aceita data real e recusa formato errado ou data inexistente", () => {
    assert.equal(sextaValida("2026-10-16"), true);
    assert.equal(sextaValida("2026-10-1"), false);
    assert.equal(sextaValida("16-10-2026"), false);
    assert.equal(sextaValida("2026-02-30"), false);
    assert.equal(sextaValida("2026-13-01"), false);
    assert.equal(sextaValida("../etc"), false);
  });
});

describe("ehErro", () => {
  it("reconhece o bloco que falhou", () => {
    assert.equal(ehErro({ erro: "CoinGecko fora do ar" }), true);
    assert.equal(ehErro({ btc: null }), false);
  });
});

describe("periodoDaSemana", () => {
  it("mesmo mes: primeiro dia so com o numero", () => {
    assert.equal(
      periodoDaSemana(["2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"], "2026-10-16"),
      "13 a 16/10/2026",
    );
  });
  it("virada de mes e de ano", () => {
    assert.equal(periodoDaSemana(["2026-09-28", "2026-10-02"], "2026-10-02"), "28/09 a 02/10/2026");
    assert.equal(
      periodoDaSemana(["2025-12-29", "2026-01-02"], "2026-01-02"),
      "29/12/2025 a 02/01/2026",
    );
  });
  it("um pregao so, ou nenhum", () => {
    assert.equal(periodoDaSemana(["2026-04-02"], "2026-04-03"), "02/04/2026");
    assert.equal(periodoDaSemana([], "2026-04-03"), "03/04/2026");
  });
});

describe("hora de Brasilia", () => {
  it("21:27 UTC de sabado ainda e sabado, 18:27", () => {
    assert.equal(instanteEmBrasilia("2026-10-17T21:27:43.969185+00:00"), "sáb 17/10 às 18:27");
  });
  it("02:00 UTC cai no dia anterior em Brasilia", () => {
    assert.equal(diaEmBrasilia("2026-10-17T02:00:00+00:00"), "2026-10-16");
    assert.equal(instanteEmBrasilia("2026-10-17T11:31:00+00:00"), "sáb 17/10 às 08:31");
  });
  it("dia da semana de uma data ISO", () => {
    assert.equal(diaComSemana("2026-10-22"), "qui 22/10");
  });
});

describe("vizinhas", () => {
  const edicoes = [
    { sexta: "2026-10-16", inicio: "2026-10-09", fim: "2026-10-16" },
    { sexta: "2026-10-09", inicio: "2026-10-02", fim: "2026-10-09" },
    { sexta: "2026-10-02", inicio: "2026-09-25", fim: "2026-10-02" },
  ];
  it("no meio tem as duas", () => {
    assert.deepEqual(vizinhas(edicoes, "2026-10-09"), {
      anterior: "2026-10-02",
      seguinte: "2026-10-16",
    });
  });
  it("nas pontas falta uma", () => {
    assert.deepEqual(vizinhas(edicoes, "2026-10-16"), { anterior: "2026-10-09", seguinte: null });
    assert.deepEqual(vizinhas(edicoes, "2026-10-02"), { anterior: null, seguinte: "2026-10-09" });
  });
  it("edicao fora da lista nao tem vizinha", () => {
    assert.deepEqual(vizinhas(edicoes, "2026-01-02"), { anterior: null, seguinte: null });
    assert.deepEqual(vizinhas([], "2026-10-16"), { anterior: null, seguinte: null });
  });
});

describe("agruparAgenda", () => {
  const e = (data, hora, evento, pais = "BR") => ({
    data,
    hora,
    pais,
    evento,
    detalhe: null,
    consenso: null,
    fonte: "x",
  });
  it("agrupa por dia, hora crescente, sem hora por ultimo", () => {
    const grupos = agruparAgenda([
      e("2026-10-22", null, "Sem hora"),
      e("2026-10-21", "15:30", "B", "EUA"),
      e("2026-10-22", "09:00", "A"),
      e("2026-10-21", "09:00", "C"),
    ]);
    assert.deepEqual(
      grupos.map((g) => [g.data, g.eventos.map((x) => x.evento)]),
      [
        ["2026-10-21", ["C", "B"]],
        ["2026-10-22", ["A", "Sem hora"]],
      ],
    );
  });
  it("agenda vazia nao tem grupo", () => {
    assert.deepEqual(agruparAgenda([]), []);
  });
});

describe("pontosBase", () => {
  it("sinal explicito, menos tipografico e virgula", () => {
    assert.equal(pontosBase(34.42000000000007), "+34,4 bp");
    assert.equal(pontosBase(-15.000000000000036), "−15,0 bp");
  });
  it("ruido de ponto flutuante nao vira sinal", () => {
    assert.equal(pontosBase(0.04), "0,0 bp");
    assert.equal(pontosBase(-0.04), "0,0 bp");
  });
  it("ausente vira travessao", () => {
    assert.equal(pontosBase(null), "—");
  });
});

describe("prazoDoTreasury e mesDeReferencia", () => {
  it("traduz o texto do Tesouro dos EUA", () => {
    assert.equal(prazoDoTreasury("3 Mo"), "3 meses");
    assert.equal(prazoDoTreasury("2 Yr"), "2 anos");
    assert.equal(prazoDoTreasury("1 Yr"), "1 ano");
    assert.equal(prazoDoTreasury("20 Yr"), "20 anos");
    assert.equal(prazoDoTreasury("?"), "?");
  });
  it("mes de referencia", () => {
    assert.equal(mesDeReferencia("2026-09"), "set/2026");
  });
});

describe("detalheDoAjuste", () => {
  it("JCP: preco bruto e provento", () => {
    assert.equal(detalheDoAjuste(acao()), "variação de preço −5,8%; proventos de R$ 0,356");
  });
  it("desdobramento", () => {
    assert.equal(
      detalheDoAjuste(
        acao({ variacao_bruta: -0.5, proventos_por_acao: 0, multiplicador: 2 }),
      ),
      "variação de preço −50,0%; ações ×2",
    );
  });
  it("sem ajuste, sem detalhe", () => {
    assert.equal(detalheDoAjuste(acao({ ajustado: false })), null);
  });
});

describe("descartesEmTexto", () => {
  it("soma e ordena do maior para o menor", () => {
    const r = descartesEmTexto({
      nao_e_noticia: 3,
      boletim_diario: 99,
      fora_da_semana: 11,
      fora_da_imprensa: 278,
    });
    assert.equal(r.total, 391);
    assert.deepEqual(r.partes, [
      "278 de sites fora da imprensa",
      "99 boletins diários",
      "11 fora da semana",
      "3 não eram notícia",
    ]);
  });
  it("motivo novo nao some: aparece com o nome tecnico", () => {
    assert.deepEqual(descartesEmTexto({ outro: 2, zero: 0 }).partes, ["2 (outro)"]);
  });
});

describe("tickersDasAcoes", () => {
  it("junta as tres listas sem repetir", () => {
    const a = (t) => acao({ ticker: t });
    assert.deepEqual(
      tickersDasAcoes({ altas: [a("A1"), a("B1")], quedas: [a("B1")], fora_do_ranking: [a("C1")] }),
      ["A1", "B1", "C1"],
    );
  });
});

describe("soQuemSubiu e soQuemCaiu", () => {
  // As altas de cripto da edicao de 16/10/2026, como foram gravadas.
  const ALTAS_GRAVADAS = [
    { simbolo: "XMR", variacao_7d: 0.092 },
    { simbolo: "LEO", variacao_7d: 0.014 },
    { simbolo: "TRX", variacao_7d: 0.005 },
    { simbolo: "WBT", variacao_7d: -0.031 },
    { simbolo: "BCH", variacao_7d: -0.032 },
  ];

  it("a edicao de 16/10 mostra so as tres que subiram nas altas", () => {
    const altas = soQuemSubiu(ALTAS_GRAVADAS, (m) => m.variacao_7d).map((m) => m.simbolo);
    assert.deepEqual(altas, ["XMR", "LEO", "TRX"]);
  });

  it("zero e sem variacao nao sao alta nem queda", () => {
    const itens = [{ v: 0 }, { v: null }, { v: undefined }, { v: -0.01 }, { v: 0.01 }];
    assert.deepEqual(soQuemSubiu(itens, (i) => i.v), [{ v: 0.01 }]);
    assert.deepEqual(soQuemCaiu(itens, (i) => i.v), [{ v: -0.01 }]);
  });
});
