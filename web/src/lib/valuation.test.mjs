// Valuation simples: Graham, Bazin e fluxo de caixa descontado.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  avaliar,
  bazin,
  crescimentoDoLucro,
  dcf,
  graham,
  premissasPadrao,
  proventoMedioAnual,
  resumir,
  sinalDoPreco,
  textoDaDiferenca,
} from "./valuation.ts";

const perto = (a, b, tolerancia = 1e-9) => assert.ok(Math.abs(a - b) < tolerancia, `${a} != ${b}`);

describe("Graham", () => {
  it("raiz de 22,5 x lucro por acao x valor patrimonial por acao", () => {
    // LPA 4 e VPA 10 -> raiz(22,5 * 40) = raiz(900) = 30
    perto(graham(4, 10), 30);
  });

  it("no teto de Graham (P/L 15 e P/VP 1,5) o preco justo e o proprio preco", () => {
    const lpa = 2;
    const vpa = 20;
    const preco = 15 * lpa; // = 1,5 * vpa = 30
    perto(graham(lpa, vpa), preco);
  });

  it("prejuizo ou patrimonio negativo nao tem valor de Graham", () => {
    assert.equal(graham(-1, 10), null);
    assert.equal(graham(0, 10), null);
    assert.equal(graham(2, -5), null);
    assert.equal(graham(null, 10), null);
  });
});

describe("Bazin", () => {
  const proventos = [
    { dataCom: "2023-10-20", tipo: "DIVIDENDO", valor: 9.99 }, // fora: mais de 3 anos
    { dataCom: "2024-03-10", tipo: "DIVIDENDO", valor: 1.0 },
    { dataCom: "2024-09-10", tipo: "JRS CAP PROPRIO", valor: 0.5 },
    { dataCom: "2025-06-01", tipo: "DIVIDENDO", valor: 1.5 },
    { dataCom: "2026-05-15", tipo: "DIVIDENDO", valor: 3.0 },
    { dataCom: "2026-12-01", tipo: "DIVIDENDO", valor: 7.0 }, // fora: depois da data
  ];

  it("media anual dos 3 anos ate a data, pela data com", () => {
    perto(proventoMedioAnual(proventos, "2026-11-13"), (1.0 + 0.5 + 1.5 + 3.0) / 3);
  });

  it("ano sem provento conta como zero na media", () => {
    const umSo = [{ dataCom: "2026-05-15", tipo: "DIVIDENDO", valor: 3.0 }];
    perto(proventoMedioAnual(umSo, "2026-11-13"), 1.0);
  });

  it("sem provento nenhum no banco e 'nao sei', nao zero", () => {
    assert.equal(proventoMedioAnual([], "2026-11-13"), null);
  });

  it("provento anterior a um desdobramento entra na escala das acoes de hoje", () => {
    // 1 para 3 em 2025-01-01: o que foi pago antes vale um terco por acao de hoje
    const ajuste = (dataCom) => (dataCom < "2025-01-01" ? 1 / 3 : 1);
    perto(
      proventoMedioAnual(proventos, "2026-11-13", 3, ajuste),
      ((1.0 + 0.5) / 3 + 1.5 + 3.0) / 3,
    );
  });

  it("preco teto: o preco em que o provento medio rende 6%", () => {
    perto(bazin(1.8), 30);
    assert.equal(bazin(0), null);
    assert.equal(bazin(null), null);
  });
});

describe("fluxo de caixa descontado", () => {
  const p = { crescimento: 0.05, desconto: 0.15, perpetuidade: 0.04, anos: 5 };

  it("bate com a conta feita a mao", () => {
    // lucros de 1,05 ... 1,2763, descontados a 15%, mais a perpetuidade
    let total = 0;
    let lucro = 1;
    for (let ano = 1; ano <= 5; ano++) {
      lucro *= 1.05;
      total += lucro / 1.15 ** ano;
    }
    total += (lucro * 1.04) / (0.15 - 0.04) / 1.15 ** 5;
    perto(dcf(1, p), total);
    // e proporcional ao lucro: o dobro do lucro, o dobro do valor
    perto(dcf(2, p), 2 * total);
  });

  it("sem crescimento nenhum vira a perpetuidade simples: lucro / desconto", () => {
    perto(dcf(3, { crescimento: 0, desconto: 0.15, perpetuidade: 0, anos: 5 }), 3 / 0.15, 1e-9);
  });

  it("mais crescimento vale mais; mais desconto vale menos", () => {
    assert.ok(dcf(1, { ...p, crescimento: 0.1 }) > dcf(1, p));
    assert.ok(dcf(1, { ...p, desconto: 0.2 }) < dcf(1, p));
  });

  it("prejuizo nao e projetado", () => {
    assert.equal(dcf(-1, p), null);
    assert.equal(dcf(null, p), null);
  });

  it("desconto colado na perpetuidade nao da numero (o valor explodiria)", () => {
    assert.equal(dcf(1, { ...p, desconto: 0.05 }), null);
    assert.equal(dcf(1, { ...p, desconto: 0.04 }), null);
    assert.notEqual(dcf(1, { ...p, desconto: 0.07 }), null);
  });
});

describe("premissas padrao do fluxo de caixa", () => {
  const tri = (lucro12m) => ({ lucro12m });
  // 9 trimestres: o de hoje e o de 8 trimestres (2 anos) atras
  const serie = (antigo, atual) => [tri(antigo), ...Array(7).fill(tri(1)), tri(atual)];

  it("crescimento do lucro de 12 meses em taxa composta de 2 anos", () => {
    perto(crescimentoDoLucro(serie(100, 121)), 0.1);
    perto(crescimentoDoLucro(serie(100, 81)), -0.1);
  });

  it("serie curta ou saindo de prejuizo nao tem crescimento medido", () => {
    assert.equal(crescimentoDoLucro([tri(100), tri(121)]), null);
    assert.equal(crescimentoDoLucro(serie(-50, 121)), null);
    assert.equal(crescimentoDoLucro(serie(100, -5)), null);
  });

  it("o crescimento fica entre 0% e 15%", () => {
    assert.equal(premissasPadrao(0.4, 0.1287).crescimento, 0.15);
    assert.equal(premissasPadrao(-0.2, 0.1287).crescimento, 0);
    assert.equal(premissasPadrao(0.08, 0.1287).crescimento, 0.08);
    assert.equal(premissasPadrao(null, 0.1287).crescimento, 0.04);
  });

  it("o desconto e o juro longo mais 5 pontos; sem juro no banco, 12% + 5", () => {
    perto(premissasPadrao(0.05, 0.1287).desconto, 0.1787);
    perto(premissasPadrao(0.05, null).desconto, 0.17);
    assert.equal(premissasPadrao(0.05, 0.1287).anos, 5);
    assert.equal(premissasPadrao(0.05, 0.1287).perpetuidade, 0.04);
  });
});

describe("o sinal e o resumo", () => {
  it("a menos de 10% do justo e 'perto'", () => {
    assert.equal(sinalDoPreco(82, 100), "abaixo");
    assert.equal(sinalDoPreco(91, 100), "perto");
    assert.equal(sinalDoPreco(109, 100), "perto");
    assert.equal(sinalDoPreco(115, 100), "acima");
  });

  it("a diferenca em palavras", () => {
    assert.equal(textoDaDiferenca(-0.18), "18% abaixo");
    assert.equal(textoDaDiferenca(0.151), "15% acima");
    assert.equal(textoDaDiferenca(0.002), "no preço");
    assert.equal(textoDaDiferenca(null), "—");
  });

  const premissas = { crescimento: 0.05, desconto: 0.17, perpetuidade: 0.04, anos: 5 };
  const papel = {
    preco: 34.5,
    lucroPorAcao: 4,
    valorPatrimonialPorAcao: 19.7,
    proventoMedio: 1.8,
    acoesConfiaveis: true,
  };

  it("os tres metodos de um papel, cada um com o seu sinal", () => {
    const [g, b, d] = avaliar(papel, premissas);
    perto(g.precoJusto, Math.sqrt(22.5 * 4 * 19.7));
    assert.equal(g.sinal, "abaixo"); // 34,50 contra 42,10
    perto(b.precoJusto, 30);
    assert.equal(b.sinal, "acima"); // 34,50 contra 30,00
    assert.equal(d.metodo, "dcf");
    assert.ok(d.precoJusto > 0);
    perto(g.diferenca, 34.5 / g.precoJusto - 1);
  });

  it("o resumo conta quantos concordam, sem tirar media", () => {
    const r = resumir([
      { metodo: "graham", sinal: "abaixo" },
      { metodo: "bazin", sinal: "acima" },
      { metodo: "dcf", sinal: "abaixo" },
    ]);
    assert.equal(r.texto, "2 de 3 métodos: abaixo do preço justo");
    assert.equal(
      resumir([{ sinal: "acima" }, { sinal: "acima" }, { sinal: null }]).texto,
      "2 de 2 métodos: acima do preço justo",
    );
    assert.equal(resumir([{ sinal: "perto" }, { sinal: "perto" }]).texto, "Os 2 métodos ficaram perto do preço justo");
    assert.equal(resumir([{ sinal: null }]).texto, "Nenhum método se aplica a esta empresa");
  });

  it("prejuizo: Graham e fluxo de caixa dizem por que nao calcularam; Bazin continua valendo", () => {
    const [g, b, d] = avaliar({ ...papel, lucroPorAcao: -2 }, premissas);
    assert.equal(g.precoJusto, null);
    assert.match(g.motivo, /prejuízo/);
    assert.equal(d.precoJusto, null);
    assert.match(d.motivo, /prejuízo/);
    assert.equal(b.sinal, "acima");
  });

  it("contagem de acoes nao confiavel derruba o que e por acao, e so isso", () => {
    const [g, b, d] = avaliar({ ...papel, acoesConfiaveis: false }, premissas);
    assert.match(g.motivo, /contagem de ações/);
    assert.match(d.motivo, /contagem de ações/);
    perto(b.precoJusto, 30); // o provento ja vem por acao, da B3
  });

  it("provento fora de escala para o preco nao vira preco teto", () => {
    // R$ 12 por ano num papel de R$ 34,50 (35%): extraordinario ou desdobramento antigo
    const [, b] = avaliar({ ...papel, proventoMedio: 12 }, premissas);
    assert.equal(b.precoJusto, null);
    assert.match(b.motivo, /fora de escala/);
    // 20% ao ano e alto, mas existe: continua valendo
    perto(avaliar({ ...papel, proventoMedio: 6.9 }, premissas)[1].precoJusto, 115);
  });

  it("papel sem provento: 'nao pagou' e 'nao sei' sao motivos diferentes", () => {
    assert.match(avaliar({ ...papel, proventoMedio: 0 }, premissas)[1].motivo, /não pagou/);
    assert.match(avaliar({ ...papel, proventoMedio: null }, premissas)[1].motivo, /não há proventos/);
  });
});
