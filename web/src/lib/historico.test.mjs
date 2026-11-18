// O payload da Tela 3: arredondamento que nao muda nada na tela. `npm test`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { agruparPorPapel, casas, linhaDoHistorico } from "./historico.ts";

/** Um evento como `lerEventos` o devolve, com os campos que a Tela 3 usa. */
const evento = (extra = {}) => ({
  ticker: "SEQL3",
  empresa: "SEQUOIA LOGÍSTICA E TRANSPORTES S.A.",
  tradeDate: "2026-09-14",
  zLog: 4.2713,
  zJanela: 30,
  zByWindow: { 30: 4.2713 },
  zRobust: 12.5,
  rvol: 30.1173,
  close: 1.23,
  volumeFinancial: 932975,
  tradesCount: 1635,
  tradesCensored: false,
  retDay: 0.03412345678901234,
  clv: 0.5,
  gap: 0.01,
  rangeNorm: 0.07,
  pos252: 0.4,
  retPrior20: -0.1,
  avgTicket: 570.6269113149847,
  ticketZ: 1.2,
  mktVolZ: 0.3,
  zExcess: 4.348801362190244,
  notificado: false,
  ...extra,
});

describe("casas", () => {
  it("arredonda para o numero de casas pedido", () => {
    assert.equal(casas(4.348801362190244, 4), 4.3488);
    assert.equal(casas(0.03412345678901234, 4), 0.0341);
  });

  it("preserva o nulo: campo ausente nunca vira zero", () => {
    // Papel recem-listado nao tem contexto; mostrar 0 ali seria mentira.
    assert.equal(casas(null, 4), null);
  });

  it("deixa passar o que nao e numero finito", () => {
    assert.ok(Number.isNaN(casas(NaN, 2)));
    assert.equal(casas(Infinity, 2), Infinity);
  });
});

describe("linhaDoHistorico", () => {
  it("leva so os campos que a tabela usa", () => {
    assert.deepEqual(Object.keys(linhaDoHistorico(evento())).sort(), [
      "avgTicket",
      "empresa",
      "retDay",
      "rvol",
      "ticker",
      "tradeDate",
      "volumeFinancial",
      "zExcess",
      "zLog",
    ]);
  });

  it("corta a precisao dos campos que vem do JSONB de contexto", () => {
    const l = linhaDoHistorico(evento());
    assert.equal(l.zExcess, 4.3488);
    assert.equal(l.retDay, 0.0341);
    assert.equal(l.avgTicket, 571);
  });

  it("nao toca no que ja vem quantizado do banco", () => {
    // `zLog`, `rvol` e `volumeFinancial` sao colunas NUMERIC: arredondar nao
    // economizaria um byte e `zLog` ainda e comparado com o limiar de 6 sigma.
    const l = linhaDoHistorico(evento());
    assert.equal(l.zLog, 4.2713);
    assert.equal(l.rvol, 30.1173);
    assert.equal(l.volumeFinancial, 932975);
  });

  it("nao empurra um evento abaixo do limiar para cima dele", () => {
    // O 5,9962 e a razao de `zLog` ficar intacto: com 2 casas ele viraria 6,00
    // e a tabela o contaria como "acima de 6 sigma" sem que o alerta tivesse
    // saido no Telegram.
    assert.equal(linhaDoHistorico(evento({ zLog: 5.9962 })).zLog, 5.9962);
  });

  it("mantem o nulo de papel sem contexto", () => {
    const l = linhaDoHistorico(evento({ retDay: null, zExcess: null, avgTicket: null }));
    assert.equal(l.retDay, null);
    assert.equal(l.zExcess, null);
    assert.equal(l.avgTicket, null);
  });

  it("o arredondamento nao muda o que a tela escreve", () => {
    // A garantia do modulo inteiro, escrita como teste: mesma string antes e
    // depois, com os formatadores de verdade.
    const cru = evento();
    const l = linhaDoHistorico(cru);
    const doisDigitos = (v) => v.toFixed(2);
    const umDigito = (v) => v.toFixed(1);
    assert.equal(doisDigitos(l.zExcess), doisDigitos(cru.zExcess));
    assert.equal(umDigito(l.retDay * 100), umDigito(cru.retDay * 100));
    assert.equal(l.avgTicket.toFixed(0), cru.avgTicket.toFixed(0));
  });
});

describe("agruparPorPapel", () => {
  /** Uma linha da tabela, so com o que o agrupamento le. */
  const linha = (ticker, tradeDate, zLog = 4) => ({ ticker, tradeDate, zLog, empresa: null });

  it("deixa cada papel uma vez so, com o evento mais recente e a contagem", () => {
    const papeis = agruparPorPapel([
      linha("PETR4", "2026-11-14", 3.5),
      linha("VALE3", "2026-11-14", 6.2),
      linha("PETR4", "2026-11-10", 7.1),
      linha("PETR4", "2026-11-03", 4.0),
    ]);
    assert.deepEqual(
      papeis.map((p) => [p.ticker, p.tradeDate, p.zLog, p.eventos]),
      [
        ["PETR4", "2026-11-14", 3.5, 3],
        ["VALE3", "2026-11-14", 6.2, 1],
      ],
    );
  });

  it("ordena pelo evento mais recente, mesmo que cheguem fora de ordem", () => {
    const papeis = agruparPorPapel([
      linha("ITUB4", "2026-10-01"),
      linha("BBAS3", "2026-11-12"),
      linha("ITUB4", "2026-11-13"),
    ]);
    assert.deepEqual(
      papeis.map((p) => [p.ticker, p.tradeDate, p.eventos]),
      [
        ["ITUB4", "2026-11-13", 2],
        ["BBAS3", "2026-11-12", 1],
      ],
    );
  });

  it("no mesmo pregao mantem a ordem do banco (maior z primeiro)", () => {
    const papeis = agruparPorPapel([
      linha("AAAA3", "2026-11-14", 9),
      linha("BBBB3", "2026-11-14", 5),
      linha("CCCC3", "2026-11-14", 3),
    ]);
    assert.deepEqual(papeis.map((p) => p.ticker), ["AAAA3", "BBBB3", "CCCC3"]);
  });

  it("lista vazia continua vazia", () => {
    assert.deepEqual(agruparPorPapel([]), []);
  });
});
