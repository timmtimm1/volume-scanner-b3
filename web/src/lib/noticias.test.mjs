// O filtro de noticias da ficha: RSS, identidade do papel, motivo de descarte,
// agrupamento por historia e o resultado final que a aba Noticias mostra.
//
// As manchetes usadas aqui sao reais, da amostra colhida em 24/09/2026.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  agrupar,
  buscasDoGoogle,
  filtrarNoticias,
  lerRss,
  motivoDoDescarte,
  tempoRelativo,
} from "./noticias.ts";
import { EMPRESAS, identidadeDoPapel } from "./nomes-na-imprensa.ts";

/** Uma noticia pronta para os testes de descarte, sem passar pelo RSS. */
function noticia(titulo, fonte, dominio, publicadaEm = "2026-09-24T12:00:00.000Z") {
  return {
    titulo,
    fonte,
    dominio,
    link: `https://${dominio}/${encodeURIComponent(titulo)}`,
    publicadaEm,
  };
}

describe("lerRss", () => {
  it("le titulo (sem o sufixo da fonte), fonte, dominio, link e data", () => {
    const xml = `<?xml version="1.0"?>
<rss><channel>
  <item>
    <title>Vale &amp; Petrobras avaliam parceria, diz &quot;fonte&quot; - InfoMoney</title>
    <link>https://news.google.com/rss/articles/abc?oc=5</link>
    <pubDate>Thu, 24 Sep 2026 10:00:00 GMT</pubDate>
    <source url="https://www.infomoney.com.br">InfoMoney</source>
  </item>
  <item>
    <title>Azul anuncia nova rota - g1.globo.com</title>
    <link>https://news.google.com/rss/articles/def?oc=5</link>
    <pubDate>Thu, 24 Sep 2026 09:00:00 GMT</pubDate>
    <source url="https://g1.globo.com">g1.globo.com</source>
  </item>
</channel></rss>`;

    const noticias = lerRss(xml);
    assert.equal(noticias.length, 2);

    assert.equal(noticias[0].titulo, 'Vale & Petrobras avaliam parceria, diz "fonte"');
    assert.equal(noticias[0].fonte, "InfoMoney");
    assert.equal(noticias[0].dominio, "infomoney.com.br");
    assert.equal(noticias[0].link, "https://news.google.com/rss/articles/abc?oc=5");
    assert.equal(noticias[0].publicadaEm, new Date("Thu, 24 Sep 2026 10:00:00 GMT").toISOString());

    assert.equal(noticias[1].titulo, "Azul anuncia nova rota");
    assert.equal(noticias[1].dominio, "g1.globo.com");
  });
});

describe("identidadeDoPapel", () => {
  it("usa o nome que a imprensa usa e todas as classes", () => {
    const id = identidadeDoPapel("PETR4");
    assert.deepEqual(id.nomes, ["Petrobras"]);
    assert.deepEqual(id.tickers, ["PETR3", "PETR4"]);
    assert.equal(id.ambiguo, false);
  });

  it("nome atual, nao o da CVM", () => {
    assert.deepEqual(identidadeDoPapel("PRIO3").nomes, ["Prio", "PetroRio"]);
    assert.ok(identidadeDoPapel("COGN3").nomes.includes("Cogna"));
  });

  it("ticker fora da tabela busca so por ele mesmo", () => {
    assert.deepEqual(identidadeDoPapel("XPTO3"), {
      tickers: ["XPTO3"],
      nomes: [],
      ambiguo: false,
      naoEAEmpresa: [],
    });
  });
});

describe("tabela de nomes", () => {
  it("as 321 empresas do banco de 24/09/2026", () => {
    assert.equal(EMPRESAS.length, 321);
  });

  it("nenhum ticker em duas empresas, nenhum erro de digitacao", () => {
    // Mais largo que o TICKER do site: a B3 tem codigo com digito no emissor (B3SA3, B1003).
    const formato = /^[A-Z0-9]{4}\d{1,2}[A-Z]?$/;
    const vistos = new Set();
    for (const e of EMPRESAS) {
      for (const t of e.tickers) {
        assert.ok(!vistos.has(t), `${t} repetido`);
        assert.ok(formato.test(t), `${t} fora do formato`);
        vistos.add(t);
      }
    }
  });
});

describe("buscasDoGoogle", () => {
  it("nome comum: uma busca com todas as classes e os nomes", () => {
    assert.deepEqual(buscasDoGoogle(identidadeDoPapel("PETR4"), 7), [
      '("PETR3" OR "PETR4" OR "Petrobras") when:7d',
    ]);
  });

  it("sem nome (B3, de proposito), so o ticker", () => {
    assert.deepEqual(buscasDoGoogle(identidadeDoPapel("B3SA3"), 30), ['"B3SA3" when:30d']);
  });

  it("nome ambiguo: tickers numa busca, o nome so na manchete da imprensa financeira", () => {
    const [tickers, nome, ...resto] = buscasDoGoogle(identidadeDoPapel("RAIL3"), 7);
    assert.equal(tickers, '"RAIL3" when:7d');
    assert.match(nome, /^intitle:"Rumo" site:infomoney\.com\.br OR .* when:7d$/);
    assert.equal(resto.length, 0);
  });
});

describe("motivoDoDescarte", () => {
  const vale = identidadeDoPapel("VALE3");
  const azul = identidadeDoPapel("AZUL4");
  const magalu = identidadeDoPapel("MGLU3");
  const itau = identidadeDoPapel("ITUB4");
  const tim = identidadeDoPapel("TIMS3");
  const petrobras = identidadeDoPapel("PETR4");

  it("VALE3 aceita noticia real sobre a empresa", () => {
    assert.equal(
      motivoDoDescarte(
        noticia("Vale (VALE3) mira cobre enquanto minério perde força", "InfoMoney", "infomoney.com.br"),
        vale,
      ),
      null,
    );
    assert.equal(
      motivoDoDescarte(
        noticia(
          "Vale compra 30% de mineradora por R$ 975 milhões",
          "Valor",
          "valor.globo.com",
        ),
        vale,
      ),
      null,
    );
    assert.equal(
      motivoDoDescarte(
        noticia(
          "Projeto com Vale no Pará pode quase dobrar operação da Ero Copper",
          "Valor",
          "valor.globo.com",
        ),
        vale,
      ),
      null,
    );
  });

  it("nome ambiguo sem ticker so conta na imprensa financeira", () => {
    // A mesma mina no Valor e no InfoMoney entra; no Estadao, nao.
    assert.equal(
      motivoDoDescarte(
        noticia(
          "Vale recebe aval da Justiça para retomar mina suspensa após vazamento em MG",
          "Estadão",
          "estadao.com.br",
        ),
        vale,
      ),
      "fora-da-imprensa-financeira",
    );
    const estrela = identidadeDoPapel("ESTR4");
    assert.equal(
      motivoDoDescarte(noticia("Brinquedos Estrela fecha fábrica em Minas", "g1", "g1.globo.com"), estrela),
      "fora-da-imprensa-financeira",
    );
    assert.equal(
      motivoDoDescarte(noticia("Estrela (ESTR4) dispara 20% na bolsa", "g1", "g1.globo.com"), estrela),
      null,
    );
    // Petrobras nao e ambiguo: imprensa geral vale.
    assert.equal(
      motivoDoDescarte(
        noticia("Petrobras vai perfurar 3 novos poços na Foz do Amazonas", "g1", "g1.globo.com"),
        petrobras,
      ),
      null,
    );
  });

  it("VALE3 descarta nao-e-a-empresa quando 'Vale' e outra coisa", () => {
    const casos = [
      noticia(
        "Treze postos de combustíveis têm inscrição cassada no Vale do Paraíba",
        "g1",
        "g1.globo.com",
      ),
      noticia(
        "O que ainda vale a pena na carteira? UBS destaca apenas dois grupos de ativos",
        "Estadão",
        "estadao.com.br",
      ),
      noticia("Vale do Silício cria sua própria escola", "O Globo", "oglobo.globo.com"),
      noticia("Comparecimento às urnas vale como Prova de Vida", "g1", "g1.globo.com"),
    ];
    for (const c of casos) {
      assert.equal(motivoDoDescarte(c, vale), "nao-e-a-empresa", c.titulo);
    }
  });

  it("AZUL4 aceita noticia real e descarta nao-e-a-empresa e promocao", () => {
    assert.equal(
      motivoDoDescarte(
        noticia(
          "Azul diz que falha em GPS da Embraer cancelou 80 voos e afeta 8 mil passageiros",
          "InfoMoney",
          "infomoney.com.br",
        ),
        azul,
      ),
      null,
    );
    assert.equal(
      motivoDoDescarte(
        noticia("Área Azul deixa de ser cobrada na Avenida Dom Pedro I", "g1", "g1.globo.com"),
        azul,
      ),
      "nao-e-a-empresa",
    );
    assert.equal(
      motivoDoDescarte(
        noticia(
          "Câmara de BH ilumina fachada de azul em apoio à comunidade surda",
          "g1",
          "g1.globo.com",
        ),
        azul,
      ),
      "nao-e-a-empresa",
    );
    // Fonte financeira, para provar que quem barra e a promocao.
    assert.equal(
      motivoDoDescarte(
        noticia(
          "Azul tem passagens nacionais a partir de R$ 71 ou de 5 mil pontos + taxas",
          "InfoMoney",
          "infomoney.com.br",
        ),
        azul,
      ),
      "promocao",
    );
    assert.equal(
      motivoDoDescarte(
        noticia("Azul Fidelidade: até 110% de bônus", "g1", "g1.globo.com"),
        azul,
      ),
      "nao-e-a-empresa",
    );
  });

  it("MGLU3 descarta promocao e aceita noticia real", () => {
    assert.equal(
      motivoDoDescarte(
        noticia(
          "Ofertas para resfriar seu notebook: confira bases coolers com desconto no Magazine Luiza",
          "Estadão",
          "estadao.com.br",
        ),
        magalu,
      ),
      "promocao",
    );
    assert.equal(
      motivoDoDescarte(
        noticia("Magalu (MGLU3) dispara 32% em setembro", "InfoMoney", "infomoney.com.br"),
        magalu,
      ),
      null,
    );
  });

  it("ITUB4 aceita 'Itaú' com acento e descarta boletins que nao sao noticia", () => {
    assert.equal(
      motivoDoDescarte(
        noticia("Itaú vai recomprar R$ 11 bilhões em títulos de dívida", "Estadão", "estadao.com.br"),
        itau,
      ),
      null,
    );
    assert.equal(
      motivoDoDescarte(
        noticia(
          "ITUB3: cotação hoje, dividendos e indicadores da Itaú Unibanco",
          "Visnoinvest",
          "visnoinvest.com.br",
        ),
        itau,
      ),
      "nao-e-noticia",
    );
    assert.equal(
      motivoDoDescarte(
        noticia("(ITUB4) - ATENCAO PARA O CALL - PRECO R$ 24,63", "ADVFN", "br.advfn.com"),
        itau,
      ),
      "nao-e-noticia",
    );
  });

  it("Itaú BBA falando de outra empresa nao e noticia do Itaú", () => {
    assert.equal(
      motivoDoDescarte(
        noticia("O Itaú BBA identificou onde estão os próximos bilhões da Petrobras", "NeoFeed", "neofeed.com.br"),
        itau,
      ),
      "nao-e-a-empresa",
    );
  });

  it("titulo curto e pagina de cotacao nao sao noticia", () => {
    const alpargatas = identidadeDoPapel("ALPA4");
    for (const [titulo, dominio] of [
      ["Alpargatas (ALPA4)", "trademap.com.br"],
      ["ALPA4 - Alpargatas: cotação, dividendos e indicadores", "visnoinvest.com.br"],
      ["ALPA4 Fórum | Ações Alpargatas PN", "br.investing.com"],
    ]) {
      assert.equal(motivoDoDescarte(noticia(titulo, "x", dominio), alpargatas), "nao-e-noticia", titulo);
    }
  });

  it("fonte desconhecida so passa com ticker explicito e dominio .br", () => {
    assert.equal(
      motivoDoDescarte(
        noticia("Petrobras assina memorando com estatal de Moçambique", "TAG&D Law", "tagdlaw.com.br"),
        petrobras,
      ),
      "fonte-desconhecida",
    );
    assert.equal(
      motivoDoDescarte(
        noticia("Petrobras (PETR4) sobe após anúncio", "Blog Qualquer", "blogqualquer.com.br"),
        petrobras,
      ),
      null,
    );
    assert.equal(
      motivoDoDescarte(
        noticia(
          "AÇÕES, COMPRA OU VENDA? 25-08 ITUB4 - MGLU3",
          "Unisba",
          "media.unisba.ac.id",
        ),
        itau,
      ),
      "fonte-desconhecida",
    );
  });

  it("sigla: TIM aceita maiuscula, rejeita 'Tim' de nome de pessoa", () => {
    assert.equal(
      motivoDoDescarte(
        noticia("TIM anuncia R$ 1 bilhão em dividendos", "InfoMoney", "infomoney.com.br"),
        tim,
      ),
      null,
    );
    assert.equal(
      motivoDoDescarte(
        noticia("Tim Cook visita o Brasil", "g1", "g1.globo.com"),
        tim,
      ),
      "nao-e-a-empresa",
    );
  });
});

describe("agrupar", () => {
  it("mesma historia em fontes diferentes vira 1 grupo, com a financeira na frente", () => {
    const estadao = noticia(
      "Azul diz que falha no GPS da Embraer cancelou mais de 80 voos",
      "Estadão",
      "estadao.com.br",
      "2026-09-24T10:00:00.000Z",
    );
    const g1 = noticia(
      "Azul diz que falha em GPS da Embraer cancelou 80 voos e afeta 8 mil passageiros",
      "g1",
      "g1.globo.com",
      "2026-09-24T09:00:00.000Z",
    );
    const infomoney = noticia(
      "Azul diz que falha no GPS da Embraer cancelou mais de 80 voos e afeta 8 mil passageiros",
      "InfoMoney",
      "infomoney.com.br",
      "2026-09-24T11:00:00.000Z",
    );
    const outraHistoria = noticia(
      "Azul recebe terceira aeronave do ano",
      "Money Times",
      "moneytimes.com.br",
      "2026-09-24T08:00:00.000Z",
    );

    const grupos = agrupar([estadao, g1, infomoney, outraHistoria]);
    assert.equal(grupos.length, 2);

    const doGps = grupos.find((g) => g.titulo.includes("GPS"));
    assert.equal(doGps.fonte, "InfoMoney");
    assert.equal(doGps.outrasFontes.length, 2);
    assert.equal(doGps.publicadaEm, "2026-09-24T11:00:00.000Z");
  });
});

describe("agrupar, encadeado", () => {
  it("entra no grupo se bate com qualquer manchete ja la, nao so com a primeira", () => {
    const guia = noticia(
      "Cosan, Rumo e Comgás negam notificação em investigação do MP-SP sobre corrupção",
      "Guia do Investidor",
      "guiadoinvestidor.com.br",
    );
    const bpmoney = noticia(
      "Cosan (CSAN3), Rumo (RAIL3) e Comgás dizem não ter sido notificadas sobre investigação do MP-SP",
      "BPMoney",
      "bpmoney.com.br",
    );
    const infomoney = noticia(
      "Cosan, Rumo e Comgás dizem não ter sido notificadas sobre investigação do MP-SP",
      "InfoMoney",
      "infomoney.com.br",
    );
    const grupos = agrupar([guia, bpmoney, infomoney]);
    assert.equal(grupos.length, 1);
    // A primeira de fonte financeira representa o grupo.
    assert.equal(grupos[0].fonte, "BPMoney");
    assert.deepEqual(
      grupos[0].outrasFontes.map((o) => o.fonte),
      ["Guia do Investidor", "InfoMoney"],
    );
  });
});

describe("filtrarNoticias", () => {
  it("conta descartes por motivo e o total", () => {
    const azul = identidadeDoPapel("AZUL4");
    const noticias = [
      noticia("Azul diz que falha no GPS da Embraer cancelou voos", "Valor", "valor.globo.com"),
      noticia("Azul cancela 80 voos e passageiros fazem fila em Recife", "g1", "g1.globo.com"),
      noticia("Área Azul deixa de ser cobrada na Avenida Dom Pedro I", "g1", "g1.globo.com"),
      noticia(
        "Azul tem passagens nacionais a partir de R$ 71",
        "Money Times",
        "moneytimes.com.br",
        "2026-09-24T09:00:00.000Z",
      ),
      noticia("Azul (AZUL4) sobe após balanço", "Blog Qualquer", "blogqualquer.com.br"),
    ];

    const velha = noticia("Azul (AZUL4) anuncia rota nova", "Valor", "valor.globo.com", "2026-09-10T12:00:00.000Z");
    const resultado = filtrarNoticias([...noticias, velha], azul, 7, new Date("2026-09-24T13:00:00.000Z"));
    // A de 10/09 fica fora da janela de 7 dias: nem conta no total.
    assert.equal(resultado.total, 5);
    assert.equal(resultado.dias, 7);
    assert.equal(resultado.descartes["nao-e-a-empresa"], 1);
    assert.equal(resultado.descartes["fora-da-imprensa-financeira"], 1);
    assert.equal(resultado.descartes["promocao"], 1);
    assert.equal(resultado.grupos.length, 2);
  });
});

describe("tempoRelativo", () => {
  const agora = new Date("2026-09-24T12:00:00.000Z");

  it("minutos", () => {
    assert.equal(tempoRelativo("2026-09-24T11:55:00.000Z", agora), "há 5 min");
  });

  it("horas", () => {
    assert.equal(tempoRelativo("2026-09-24T09:00:00.000Z", agora), "há 3 h");
  });

  it("dias", () => {
    assert.equal(tempoRelativo("2026-09-21T12:00:00.000Z", agora), "há 3 dias");
  });
});
