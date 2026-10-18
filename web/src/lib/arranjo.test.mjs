// A logica pura do Organizar: plano em CSS, arrasto, largura, teclado, validacao.

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import vm from "node:vm";

import {
  alternarLargura,
  CHAVE_DOS_ARRANJOS,
  COLUNAS_DA_PAGINA,
  iguais,
  moverComSeta,
  normalizar,
  paginaDoCaminho,
  PAGINAS,
  planejar,
  posicoes,
  rotuloDaLargura,
  SCRIPT_DO_ARRANJO,
  soltar,
  validarItens,
} from "./arranjo.ts";
import { arranjoPadrao, PAGINAS_DE_CAIXAS } from "./paginas-arrumaveis.ts";

const c = (id, coluna, largura = 1) => ({ id, coluna, largura });
const ids = (arranjo) => arranjo.map((i) => i.id);
const SEMANA = arranjoPadrao(PAGINAS_DE_CAIXAS.semana);

/** Todas as caixas que o plano desenha, na ordem em que aparecem. */
function caixasDoPlano(no) {
  if (!no) return [];
  if (no.tipo === "caixa") return [no.id];
  if (no.tipo === "pilha") return [...no.ids];
  if (no.tipo === "lado") return no.partes.flatMap((p) => caixasDoPlano(p.no));
  return no.faixas.flatMap(caixasDoPlano);
}

describe("planejar", () => {
  it("Semana padrao: duas caixas inteiras e duas colunas que empilham sem buraco", () => {
    assert.deepEqual(planejar(SEMANA, 2), {
      tipo: "faixas",
      faixas: [
        { tipo: "caixa", id: "abertura" },
        { tipo: "caixa", id: "acoes" },
        {
          tipo: "lado",
          partes: [
            { inicio: 0, largura: 1, no: { tipo: "pilha", ids: ["noticias", "juros", "semana-que-vem"] } },
            { inicio: 1, largura: 1, no: { tipo: "pilha", ids: ["cripto", "eua", "balancos"] } },
          ],
        },
      ],
    });
  });

  it("tres colunas de uma caixa cada viram tres pilhas independentes", () => {
    const ficha = [c("id", 0), c("grafico", 1), c("desvio", 0), c("abas", 2), c("alerta", 2)];
    assert.deepEqual(planejar(ficha, 3), {
      tipo: "lado",
      partes: [
        { inicio: 0, largura: 1, no: { tipo: "pilha", ids: ["id", "desvio"] } },
        { inicio: 1, largura: 1, no: { tipo: "pilha", ids: ["grafico"] } },
        { inicio: 2, largura: 1, no: { tipo: "pilha", ids: ["abas", "alerta"] } },
      ],
    });
  });

  it("caixa inteira no meio da ordem fica abaixo de tudo o que veio antes", () => {
    const arranjo = [c("a", 0), c("b", 1), c("inteira", 0, 2), c("d", 1)];
    assert.deepEqual(planejar(arranjo, 2), {
      tipo: "faixas",
      faixas: [
        {
          tipo: "lado",
          partes: [
            { inicio: 0, largura: 1, no: { tipo: "pilha", ids: ["a"] } },
            { inicio: 1, largura: 1, no: { tipo: "pilha", ids: ["b"] } },
          ],
        },
        { tipo: "caixa", id: "inteira" },
        { tipo: "lado", partes: [{ inicio: 1, largura: 1, no: { tipo: "pilha", ids: ["d"] } }] },
      ],
    });
  });

  it("caixa de duas colunas em tres: a coluna livre segue sozinha", () => {
    const arranjo = [c("id", 0), c("grafico", 1, 2), c("desvio", 0), c("abas", 2)];
    assert.deepEqual(planejar(arranjo, 3), {
      tipo: "lado",
      partes: [
        { inicio: 0, largura: 1, no: { tipo: "pilha", ids: ["id", "desvio"] } },
        {
          inicio: 1,
          largura: 2,
          no: {
            tipo: "faixas",
            faixas: [
              { tipo: "caixa", id: "grafico" },
              { tipo: "lado", partes: [{ inicio: 2, largura: 1, no: { tipo: "pilha", ids: ["abas"] } }] },
            ],
          },
        },
      ],
    });
  });

  it("sem divisa livre nem caixa inteira, corta no maior comeco que ainda tem divisa", () => {
    const arranjo = [c("a", 0, 2), c("b", 1, 2), c("c", 0)];
    assert.deepEqual(planejar(arranjo, 3), {
      tipo: "faixas",
      faixas: [
        { tipo: "lado", partes: [{ inicio: 0, largura: 2, no: { tipo: "caixa", id: "a" } }] },
        {
          tipo: "lado",
          partes: [
            { inicio: 0, largura: 1, no: { tipo: "pilha", ids: ["c"] } },
            { inicio: 1, largura: 2, no: { tipo: "caixa", id: "b" } },
          ],
        },
      ],
    });
  });

  it("qualquer arranjo valido desenha cada caixa exatamente uma vez", () => {
    let semente = 7;
    const sorteio = (n) => {
      semente = (semente * 1103515245 + 12345) % 2147483648;
      return semente % n;
    };
    for (const colunas of [1, 2, 3]) {
      for (let rodada = 0; rodada < 400; rodada++) {
        const arranjo = Array.from({ length: 1 + sorteio(9) }, (_, i) => {
          const largura = 1 + sorteio(colunas);
          return c(`c${i}`, sorteio(colunas - largura + 1), largura);
        });
        const desenhadas = caixasDoPlano(planejar(arranjo, colunas));
        assert.deepEqual([...desenhadas].sort(), ids(arranjo).sort(), JSON.stringify(arranjo));
      }
    }
  });

  it("arranjo vazio nao desenha nada", () => {
    assert.equal(planejar([], 2), null);
  });
});

describe("posicoes", () => {
  // Duas colunas de 600px com vao de 16, como a Semana numa tela de 1232px.
  const DUAS = { colunas: [{ x: 0, w: 600 }, { x: 616, w: 600 }], vao: 16 };
  const TRES = { colunas: [{ x: 0, w: 300 }, { x: 316, w: 500 }, { x: 832, w: 360 }], vao: 16 };
  const ALTURAS = { abertura: 200, acoes: 400, noticias: 300, cripto: 100, juros: 500, eua: 150, "semana-que-vem": 200, balancos: 50 };

  it("Semana padrao: inteiras uma embaixo da outra, colunas empilhando cada uma a sua", () => {
    const p = posicoes(SEMANA, ALTURAS, DUAS);
    assert.deepEqual(p.abertura, { x: 0, y: 0, w: 1216, h: 200 });
    assert.deepEqual(p.acoes, { x: 0, y: 216, w: 1216, h: 400 });
    assert.deepEqual(p.noticias, { x: 0, y: 632, w: 600, h: 300 });
    assert.deepEqual(p.cripto, { x: 616, y: 632, w: 600, h: 100 });
    assert.deepEqual(p.juros, { x: 0, y: 948, w: 600, h: 500 });
    assert.deepEqual(p.eua, { x: 616, y: 748, w: 600, h: 150 });
    assert.equal(p["semana-que-vem"].y, 1464);
    assert.equal(p.balancos.y, 914);
  });

  it("caixa inteira no meio fica abaixo da coluna mais alta", () => {
    const arranjo = [c("a", 0), c("b", 1), c("inteira", 0, 2), c("d", 1)];
    const p = posicoes(arranjo, { a: 100, b: 300, inteira: 50, d: 10 }, DUAS);
    assert.deepEqual(p.inteira, { x: 0, y: 316, w: 1216, h: 50 });
    assert.deepEqual(p.d, { x: 616, y: 382, w: 600, h: 10 });
  });

  it("caixa escondida numa pilha nao ocupa lugar nem abre vao", () => {
    const p = posicoes([c("a", 0), c("sumida", 0), c("b", 0)], { a: 100, b: 50 }, DUAS);
    assert.equal(p.sumida, undefined);
    assert.equal(p.b.y, 116);
  });

  it("caixa inteira escondida entre faixas vira linha vazia, com vao dos dois lados (como o CSS)", () => {
    const arranjo = [c("a", 0), c("sumida", 0, 2), c("b", 1)];
    const p = posicoes(arranjo, { a: 100, b: 40 }, DUAS);
    assert.equal(p.b.y, 100 + 16 + 0 + 16);
  });

  it("tres colunas: caixa de duas e a coluna livre ao lado", () => {
    const arranjo = [c("id", 0), c("grafico", 1, 2), c("desvio", 0), c("abas", 2)];
    const p = posicoes(arranjo, { id: 100, grafico: 600, desvio: 200, abas: 300 }, TRES);
    assert.deepEqual(p.grafico, { x: 316, y: 0, w: 876, h: 600 });
    assert.deepEqual(p.abas, { x: 832, y: 616, w: 360, h: 300 });
    assert.deepEqual(p.desvio, { x: 0, y: 116, w: 300, h: 200 });
  });

  it("em qualquer arranjo, nenhuma caixa encosta em outra e todas ficam nas suas colunas", () => {
    let semente = 11;
    const sorteio = (n) => {
      semente = (semente * 1103515245 + 12345) % 2147483648;
      return semente % n;
    };
    for (const geo of [DUAS, TRES]) {
      const n = geo.colunas.length;
      for (let rodada = 0; rodada < 600; rodada++) {
        const arranjo = Array.from({ length: 1 + sorteio(9) }, (_, i) => {
          const largura = 1 + sorteio(n);
          return c(`c${i}`, sorteio(n - largura + 1), largura);
        });
        const alturas = Object.fromEntries(
          arranjo.filter(() => sorteio(6) > 0).map((i) => [i.id, 1 + sorteio(500)]),
        );
        const p = posicoes(arranjo, alturas, geo);
        assert.deepEqual(Object.keys(p).sort(), Object.keys(alturas).sort());
        const lista = Object.entries(p);
        for (const [id, r] of lista) {
          const item = arranjo.find((i) => i.id === id);
          assert.equal(r.x, geo.colunas[item.coluna].x, id);
          const ultima = geo.colunas[item.coluna + item.largura - 1];
          assert.equal(r.x + r.w, ultima.x + ultima.w, id);
        }
        for (let i = 0; i < lista.length; i++) {
          for (let j = i + 1; j < lista.length; j++) {
            const [, a] = lista[i];
            const [, b] = lista[j];
            const separadas =
              a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h + geo.vao <= b.y + 0.001 || b.y + b.h + geo.vao <= a.y + 0.001;
            assert.ok(separadas, JSON.stringify({ arranjo, alturas, a: lista[i], b: lista[j] }));
          }
        }
      }
    }
  });
});

describe("normalizar", () => {
  it("sem arranjo salvo vale o padrao", () => {
    assert.deepEqual(normalizar(null, SEMANA, 2), SEMANA);
  });

  it("caixa que saiu do codigo some, e repetida conta uma vez", () => {
    const salvo = [c("juros", 0, 2), c("sumiu", 0), c("juros", 1), ...SEMANA.filter((i) => i.id !== "juros")];
    const r = normalizar(salvo, SEMANA, 2);
    assert.deepEqual(r[0], c("juros", 0, 2));
    assert.equal(r.length, SEMANA.length);
    assert.ok(!ids(r).includes("sumiu"));
  });

  it("caixa nova entra logo depois da que a precede no padrao", () => {
    const salvo = [c("juros", 0, 2), c("abertura", 0, 2), c("eua", 1)];
    const padrao = [c("abertura", 0, 2), c("nova", 1), c("juros", 0), c("eua", 1), c("primeira-nova", 0)];
    assert.deepEqual(ids(normalizar(salvo, padrao, 2)), ["juros", "abertura", "nova", "eua", "primeira-nova"]);
    assert.deepEqual(ids(normalizar([c("eua", 1)], [c("antes", 0), c("eua", 1)], 2)), ["antes", "eua"]);
  });

  it("largura e coluna que nao cabem mais sao encaixadas", () => {
    const r = normalizar([c("a", 2, 3), c("b", 2)], [c("a", 0), c("b", 1)], 2);
    assert.deepEqual(r, [c("a", 0, 2), c("b", 1)]);
  });
});

describe("validarItens", () => {
  it("aceita o padrao de toda pagina ligada", () => {
    for (const [pagina, definicao] of Object.entries(PAGINAS_DE_CAIXAS)) {
      assert.deepEqual(validarItens(arranjoPadrao(definicao), COLUNAS_DA_PAGINA[pagina]), arranjoPadrao(definicao));
    }
  });

  for (const [caso, dados] of [
    ["nao lista", { a: 1 }],
    ["lista vazia", []],
    ["id fora do formato", [c("Juros", 0)]],
    ["id repetido", [c("a", 0), c("a", 1)]],
    ["coluna quebrada", [{ id: "a", coluna: 0.5, largura: 1 }]],
    ["largura zero", [c("a", 0, 0)]],
    ["passa da ultima coluna", [c("a", 1, 2)]],
    ["coluna negativa", [c("a", -1)]],
    ["item nulo", [null]],
    ["caixas demais", Array.from({ length: 41 }, (_, i) => c(`c${i}`, 0))],
  ]) {
    it(`recusa ${caso}`, () => assert.equal(validarItens(dados, 2), null));
  }
});

describe("soltar", () => {
  const base = [c("a", 0), c("b", 1), c("x", 0), c("d", 1)];

  it("antes e depois de uma caixa, na coluna sob o ponteiro", () => {
    assert.deepEqual(soltar(base, "x", { referencia: "b", lado: "antes", coluna: 1 }, 2), [
      c("a", 0),
      c("x", 1),
      c("b", 1),
      c("d", 1),
    ]);
    assert.deepEqual(soltar(base, "a", { referencia: "d", lado: "depois", coluna: 1 }, 2), [
      c("b", 1),
      c("x", 0),
      c("d", 1),
      c("a", 1),
    ]);
  });

  it("caixa larga e encaixada para caber, e no fim vai para o fim", () => {
    const larga = [c("a", 0, 2), c("b", 0)];
    assert.deepEqual(soltar(larga, "a", { referencia: null, lado: "depois", coluna: 1 }, 2), [
      c("b", 0),
      c("a", 0, 2),
    ]);
  });

  it("solta sobre si mesma: fica no lugar, so muda de coluna", () => {
    assert.deepEqual(soltar(base, "x", { referencia: "x", lado: "antes", coluna: 1 }, 2), [
      c("a", 0),
      c("b", 1),
      c("x", 1),
      c("d", 1),
    ]);
  });

  it("caixa desconhecida nao muda nada", () => {
    assert.equal(soltar(base, "z", { referencia: "a", lado: "antes", coluna: 0 }, 2), base);
  });
});

describe("largura", () => {
  it("duas colunas: meia largura e largura toda", () => {
    const r = alternarLargura([c("a", 1)], "a", 2);
    assert.deepEqual(r, [c("a", 0, 2)]);
    assert.deepEqual(alternarLargura(r, "a", 2), [c("a", 0, 1)]);
  });

  it("tres colunas: 1 -> 2 -> 3 -> 1, puxando para a esquerda quando nao cabe", () => {
    let r = [c("a", 2)];
    r = alternarLargura(r, "a", 3);
    assert.deepEqual(r, [c("a", 1, 2)]);
    r = alternarLargura(r, "a", 3);
    assert.deepEqual(r, [c("a", 0, 3)]);
    assert.deepEqual(alternarLargura(r, "a", 3), [c("a", 0, 1)]);
  });

  it("rotulos", () => {
    assert.equal(rotuloDaLargura(1, 2), "Meia largura");
    assert.equal(rotuloDaLargura(2, 2), "Largura toda");
    assert.equal(rotuloDaLargura(1, 3), "1 coluna");
    assert.equal(rotuloDaLargura(2, 3), "2 colunas");
    assert.equal(rotuloDaLargura(3, 3), "Largura toda");
  });
});

describe("moverComSeta", () => {
  const base = [c("a", 0), c("b", 1), c("x", 0), c("inteira", 0, 2), c("d", 1)];

  it("cima e baixo trocam com a vizinha que divide coluna", () => {
    assert.deepEqual(ids(moverComSeta(base, "x", "cima", 2)), ["x", "a", "b", "inteira", "d"]);
    assert.deepEqual(ids(moverComSeta(base, "x", "baixo", 2)), ["a", "b", "inteira", "x", "d"]);
    assert.deepEqual(ids(moverComSeta(base, "b", "baixo", 2)), ["a", "x", "inteira", "b", "d"]);
  });

  it("no topo ou no fim, a seta nao faz nada", () => {
    assert.equal(moverComSeta(base, "a", "cima", 2), base);
    assert.equal(moverComSeta(base, "d", "baixo", 2), base);
  });

  it("esquerda e direita andam uma coluna, sem sair da pagina", () => {
    assert.deepEqual(moverComSeta(base, "x", "direita", 2)[2], c("x", 1));
    assert.equal(moverComSeta(base, "x", "esquerda", 2), base);
    assert.equal(moverComSeta(base, "inteira", "direita", 2), base);
  });
});

describe("iguais", () => {
  it("compara ordem, coluna e largura", () => {
    assert.ok(iguais(SEMANA, arranjoPadrao(PAGINAS_DE_CAIXAS.semana)));
    assert.ok(!iguais(SEMANA, alternarLargura(SEMANA, "juros", 2)));
    assert.ok(!iguais(SEMANA, SEMANA.slice(1)));
  });
});

describe("paginas", () => {
  it("cada caminho cai na sua pagina", () => {
    assert.equal(paginaDoCaminho("/"), "inicio");
    assert.equal(paginaDoCaminho("/semana/"), "semana");
    assert.equal(paginaDoCaminho("/semana/2026-10-16/"), "semana");
    assert.equal(paginaDoCaminho("/papel/PETR4/"), "ficha");
    assert.equal(paginaDoCaminho("/historico/"), "historico");
    assert.equal(paginaDoCaminho("/trades/"), "trades");
    assert.equal(paginaDoCaminho("/trades/12/"), "trade");
    assert.equal(paginaDoCaminho("/alertas/"), null);
    assert.equal(paginaDoCaminho("/papeis/"), null);
    assert.equal(paginaDoCaminho("/semanal/"), null);
  });

  it("Inicio e ficha padrao: as tres colunas de hoje, cada uma empilhando a sua", () => {
    const pilhas = (pagina) =>
      planejar(arranjoPadrao(PAGINAS_DE_CAIXAS[pagina]), 3).partes.map((p) => [p.inicio, p.no.ids]);
    assert.deepEqual(pilhas("inicio"), [
      [0, ["resumo", "distribuicao", "leitura"]],
      [1, ["eventos"]],
      [2, ["previa"]],
    ]);
    assert.deepEqual(pilhas("ficha"), [
      [0, ["identidade", "desvio", "numeros"]],
      [1, ["grafico"]],
      [2, ["abas", "trade", "alerta"]],
    ]);
  });

  it("toda pagina arrumavel tem caixas definidas", () => {
    assert.deepEqual(Object.keys(PAGINAS_DE_CAIXAS).sort(), [...PAGINAS].sort());
  });

  it("Historico padrao: tabela e previa lado a lado; trades e trade numa coluna so", () => {
    assert.deepEqual(planejar(arranjoPadrao(PAGINAS_DE_CAIXAS.historico), 2), {
      tipo: "lado",
      partes: [
        { inicio: 0, largura: 1, no: { tipo: "pilha", ids: ["tabela"] } },
        { inicio: 1, largura: 1, no: { tipo: "pilha", ids: ["previa"] } },
      ],
    });
    assert.deepEqual(planejar(arranjoPadrao(PAGINAS_DE_CAIXAS.trade), 1), {
      tipo: "pilha",
      ids: ["resultado", "pregoes", "operacoes"],
    });
  });

  it("caixa que acompanha a rolagem comeca como a ultima da sua coluna", () => {
    for (const definicao of Object.values(PAGINAS_DE_CAIXAS)) {
      for (const caixa of definicao.caixas.filter((c) => c.fixa)) {
        const depois = definicao.caixas.slice(definicao.caixas.indexOf(caixa) + 1);
        assert.ok(!depois.some((c) => c.coluna === caixa.coluna), caixa.id);
      }
    }
  });

  it("as colunas de cada pagina ligada batem com as trilhas", () => {
    for (const [pagina, definicao] of Object.entries(PAGINAS_DE_CAIXAS)) {
      assert.ok(PAGINAS.includes(pagina));
      assert.equal(definicao.trilhas.length, COLUNAS_DA_PAGINA[pagina], pagina);
    }
  });
});

describe("SCRIPT_DO_ARRANJO", () => {
  function rodar({ caminho, computador = true, guardado }) {
    const atributos = {};
    const contexto = {
      matchMedia: () => ({ matches: computador }),
      localStorage: { getItem: (k) => (k === CHAVE_DOS_ARRANJOS ? guardado : null) },
      location: { pathname: caminho },
      document: { documentElement: { setAttribute: (k, v) => (atributos[k] = v) } },
    };
    vm.runInNewContext(SCRIPT_DO_ARRANJO, contexto);
    return atributos["data-arranjo"];
  }
  const guardado = JSON.stringify({ semana: SEMANA });

  it("esconde as caixas so na pagina com arranjo guardado, no computador", () => {
    assert.equal(rodar({ caminho: "/semana/2026-10-16/", guardado }), "pendente");
    assert.equal(rodar({ caminho: "/papel/PETR4/", guardado }), undefined);
    assert.equal(rodar({ caminho: "/semana/", guardado, computador: false }), undefined);
    assert.equal(rodar({ caminho: "/semana/", guardado: null }), undefined);
  });

  it("copia corrompida nao quebra a pagina", () => {
    assert.equal(rodar({ caminho: "/semana/", guardado: "{nao e json" }), undefined);
  });
});
