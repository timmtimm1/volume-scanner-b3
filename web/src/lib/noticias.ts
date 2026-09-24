/**
 * Filtro de noticias da ficha do papel.
 *
 * A fonte e o RSS gratuito do Google Noticias (`buscasDoGoogle` monta as buscas,
 * `noticias-do-google.ts` faz o fetch). Sem chave, sem contrato -- e por isso
 * o ruido nao vem so de "assunto errado", vem de tres camadas diferentes que
 * `motivoDoDescarte` aplica em ordem:
 *
 *   1. nao-e-a-empresa -- a manchete nem cita o ticker nem o nome da empresa.
 *      O caso dificil aqui e nome de empresa que tambem e palavra comum
 *      ("Vale", "Azul", "Gol"): dai a tabela de `nomes-na-imprensa.ts` e as
 *      regras `naoE` por empresa.
 *   1b. fora-da-imprensa-financeira -- nome ambiguo (Light, Rumo, Tenda) sem o
 *      ticker na manchete so conta quando a fonte e imprensa financeira.
 *   2. nao-e-noticia -- pagina de cotacao ou boletim de analise grafica que o
 *      Google indexa como se fosse noticia.
 *   3. promocao -- passagem, cashback, milhas: cita o nome da empresa mas nao
 *      e sobre ela.
 *   4. fonte-desconhecida -- o dominio nao e nem imprensa financeira nem
 *      imprensa geral conhecida (prefeitura, tribunal, universidade, blog de
 *      milhas, spam estrangeiro).
 *
 * De proposito NAO existe um filtro de fonte geral por vocabulario de
 * economia ("ações", "mercado", "bolsa" no titulo). Medido em 24/09/2026
 * contra 400 manchetes reais, esse filtro jogava fora noticia de verdade sem
 * nenhum jargao financeiro: "Petrobras vai perfurar 3 novos poços" (g1) e
 * "Vale recebe aval da Justiça para retomar mina" (Estadão). O ruido real
 * desta fonte é nome que também é palavra comum, promoção e fonte que não é
 * imprensa -- as quatro camadas acima cobrem isso sem precisar adivinhar
 * vocabulario.
 */

export type Noticia = {
  /** Manchete, sem o " - Fonte" que o Google Noticias sempre agrega ao final. */
  titulo: string;
  /** Nome da fonte, como o proprio <source> do RSS escreve. */
  fonte: string;
  /** Host do link da fonte, sem "www.". */
  dominio: string;
  link: string;
  /** ISO. */
  publicadaEm: string;
};

export type GrupoDeNoticias = Noticia & {
  outrasFontes: { fonte: string; link: string }[];
};

export type MotivoDeDescarte =
  | "nao-e-a-empresa"
  | "fora-da-imprensa-financeira"
  | "nao-e-noticia"
  | "promocao"
  | "fonte-desconhecida";

export type ResultadoDasNoticias = {
  /** No maximo 15, mais recente primeiro. */
  grupos: GrupoDeNoticias[];
  /** Quantas manchetes distintas vieram do Google dentro da janela, antes do filtro. */
  total: number;
  descartes: Record<MotivoDeDescarte, number>;
  /** A janela da busca: 7 dias, ou 30 quando 7 trouxe pouco. */
  dias: number;
};

export type Identidade = {
  /** Todas as classes da empresa (PETR3, PETR4). */
  tickers: string[];
  /** Nomes que a imprensa usa para a empresa. Vazio quando nenhum nome vale a busca. */
  nomes: string[];
  /** Trechos que parecem o nome mas nao sao a empresa -- cortados antes de procurar o nome. */
  naoEAEmpresa: RegExp[];
  /** Nome que tambem e palavra comum ou marca global: sem ticker, so imprensa financeira. */
  ambiguo: boolean;
};

const FONTES_FINANCEIRAS = new Set([
  "valor.globo.com",
  "valorinveste.globo.com",
  "infomoney.com.br",
  "moneytimes.com.br",
  "seudinheiro.com",
  "br.investing.com",
  "suno.com.br",
  "investidor10.com.br",
  "br.advfn.com",
  "exame.com",
  "neofeed.com.br",
  "braziljournal.com",
  "bloomberglinea.com.br",
  "spacemoney.com.br",
  "bpmoney.com.br",
  "acionista.com.br",
  "timesbrasil.com.br",
  "einvestidor.estadao.com.br",
  "forbes.com.br",
  "istoedinheiro.com.br",
  "conteudos.xpi.com.br",
  "eixos.com.br",
  "brasilenergia.com.br",
  "agenciainfra.com",
  "monitormercantil.com.br",
  "kinvo.com.br",
]);

const FONTES_GERAIS = new Set([
  "g1.globo.com",
  "oglobo.globo.com",
  "estadao.com.br",
  "economia.uol.com.br",
  "noticias.uol.com.br",
  "folha.uol.com.br",
  "www1.folha.uol.com.br",
  "cnnbrasil.com.br",
  "poder360.com.br",
  "gazetadopovo.com.br",
  "veja.abril.com.br",
  "correiobraziliense.com.br",
  "metropoles.com",
]);

/**
 * Os sites que entram no `site:` das buscas por nome ambiguo -- os que mais
 * publicam sobre empresa listada. Menos que `FONTES_FINANCEIRAS` porque cada
 * `site:` alonga a busca; o filtro depois aceita a lista inteira.
 */
const SITES_DA_BUSCA = [
  "infomoney.com.br",
  "valor.globo.com",
  "moneytimes.com.br",
  "seudinheiro.com",
  "exame.com",
  "suno.com.br",
  "br.investing.com",
  "investidor10.com.br",
  "braziljournal.com",
  "neofeed.com.br",
  "valorinveste.globo.com",
  "einvestidor.estadao.com.br",
];

/** Paginas de cotacao e boletins de analise grafica que o Google indexa como noticia. */
const NAO_NOTICIA =
  /Resultados, Dividendos, Cotação|cotação, dividendos|cotação hoje|ATEN[CÇ][AÃ]O PARA O CALL|Análise Técnica Semanal|Giro de Gráficos|Fórum \|/i;

/** "Alpargatas (ALPA4)" e titulo de pagina de cotacao, nao manchete. */
const PALAVRAS_MINIMAS = 4;

const PROMOCAO =
  /\b(ofertas?|cupom|desconto|promoç|a partir de R\$|milheiro|pontos \+|b[ôo]nus na transfer|transfer[êe]ncia de pontos)/i;

/**
 * "Oferta" e "desconto" que sao mercado, nao loja. Oferta de acoes (follow-on,
 * OPA) e causa classica de volume anomalo, e a manchete costuma citar a
 * empresa sem o ticker: "Vivara anuncia oferta de ações de R$ 1 bi" caia como
 * promocao antes desta excecao.
 */
const OFERTA_DE_MERCADO =
  /\boferta (pública|publica|de ações|de acoes|subsequente|primária|primaria|secundária|secundaria|de aquisição|de aquisicao|de recompra|restrita)|follow-on|\bOPA\b|com desconto de \d/i;

/**
 * Os `q` das buscas no Google Noticias, que a rota faz em paralelo e junta.
 *
 * Nome comum: uma busca com tickers e nomes. Nome ambiguo: os tickers numa
 * busca, e cada nome numa busca restrita a manchete da imprensa financeira.
 */
export function buscasDoGoogle(id: Identidade, dias: number): string[] {
  const quando = `when:${dias}d`;
  const ou = (termos: string[]) => (termos.length > 1 ? `(${termos.join(" OR ")})` : termos[0]);
  const tickers = id.tickers.map((t) => `"${t}"`);
  if (!id.ambiguo || id.nomes.length === 0) {
    return [`${ou([...tickers, ...id.nomes.map((n) => `"${n}"`)])} ${quando}`];
  }
  // Nome ambiguo nao pode ir solto na busca: o Google devolve no maximo 100
  // itens, e "Rumo" sozinho trazia 100 de "rumo a..." -- a Rumo nem chegava ao
  // filtro. Entao o nome vai numa busca propria, obrigado a estar na manchete
  // e so na imprensa financeira. Parentese dentro de parentese o Google nao
  // aceita (volta vazio), por isso uma busca por nome, sem agrupar.
  const sites = SITES_DA_BUSCA.map((d) => `site:${d}`).join(" OR ");
  return [
    `${ou(tickers)} ${quando}`,
    ...id.nomes.map((n) => `intitle:"${n}" ${sites} ${quando}`),
  ];
}

/** Decodifica as entidades XML que o RSS do Google usa (&amp; &quot; &#39; ...). */
function decodificarEntidades(s: string): string {
  return s
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, cod) => String.fromCharCode(Number(cod)))
    .replace(/&amp;/g, "&");
}

/** Host sem "www.", para comparar com as tabelas de fontes. */
function dominioDoLink(link: string): string {
  try {
    return new URL(link).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

/**
 * Le os <item> do RSS do Google Noticias.
 *
 * Parser por regex, de proposito: o formato e fixo (title, link, pubDate,
 * source) e uma dependencia de XML so para isto seria peso morto.
 */
export function lerRss(xml: string): Noticia[] {
  const noticias: Noticia[] = [];
  const itens = xml.match(/<item>[\s\S]*?<\/item>/g) ?? [];

  for (const item of itens) {
    const titleBruto = item.match(/<title>([\s\S]*?)<\/title>/)?.[1];
    const linkBruto = item.match(/<link>([\s\S]*?)<\/link>/)?.[1];
    const pubDateBruto = item.match(/<pubDate>([\s\S]*?)<\/pubDate>/)?.[1];
    const sourceMatch = item.match(/<source url="([^"]*)">([\s\S]*?)<\/source>/);
    if (!titleBruto || !linkBruto || !pubDateBruto || !sourceMatch) continue;

    const tituloCompleto = decodificarEntidades(titleBruto.trim());
    const fonte = decodificarEntidades(sourceMatch[2].trim());
    const link = decodificarEntidades(linkBruto.trim());
    const publicada = new Date(pubDateBruto.trim());
    if (Number.isNaN(publicada.getTime())) continue;

    // O Google sempre agrega " - Fonte" ao final do titulo, que ja vem em
    // <source> separado -- tirar so o sufixo exato evita cortar um " - " que
    // seja parte de fato da manchete.
    const sufixo = ` - ${fonte}`;
    const titulo = tituloCompleto.endsWith(sufixo)
      ? tituloCompleto.slice(0, -sufixo.length)
      : tituloCompleto;

    noticias.push({
      titulo,
      fonte,
      dominio: dominioDoLink(sourceMatch[1]) || dominioDoLink(link),
      link,
      publicadaEm: publicada.toISOString(),
    });
  }

  return noticias;
}

/**
 * Remove acentos, mantendo o MESMO comprimento -- para os indices do titulo
 * original valerem nas duas versoes. Normaliza caractere a caractere: cada
 * letra acentuada e um so code unit, e decompor+remover a marca devolve outro
 * code unit so, entao o comprimento nunca muda.
 */
function semAcento(s: string): string {
  return s
    .split("")
    .map((c) => c.normalize("NFD").replace(/\p{Diacritic}/gu, ""))
    .join("");
}

/** Fronteira de palavra que entende acento: o `\b` do JS trata "ú" como nao-letra e quebraria "Itaú". */
function comFronteiraDePalavra(termo: string, flags = "gu"): RegExp {
  return new RegExp(`(?<![\\p{L}\\p{N}])${termo}(?![\\p{L}\\p{N}])`, flags);
}

/** true se algum ticker da empresa aparece na manchete, como palavra inteira. */
function temTickerNoTitulo(titulo: string, tickers: string[]): boolean {
  return tickers.some((t) => comFronteiraDePalavra(t, "u").test(titulo));
}

function escapar(termo: string): string {
  return termo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Indices dos trechos do titulo que casam algum `naoEAEmpresa`.
 *
 * Casa contra a versao SEM ACENTO do titulo, e tambem sem acento na propria
 * regra ("Área" vira "Area"). O `\b` das regras da tabela e o `\b` comum do
 * JS, que so reconhece letra ASCII como parte de palavra: contra o titulo
 * ORIGINAL, `\bÁrea` nunca bate, porque nem o espaco antes nem o "Á" contam
 * como letra para o `\b` -- nunca ha a transicao que ele exige. Sem acento
 * dos dois lados, "Area" vira uma palavra ASCII normal e o `\b` funciona.
 * Os indices continuam valendo nas duas versoes do titulo, que tem o mesmo
 * comprimento.
 */
function indicesDeExclusao(tituloSemAcento: string, regras: RegExp[]): [number, number][] {
  const intervalos: [number, number][] = [];
  for (const regra of regras) {
    const fonteSemAcento = semAcento(regra.source);
    const flags = regra.flags.includes("g") ? regra.flags : `${regra.flags}g`;
    const global = new RegExp(fonteSemAcento, flags);
    let m: RegExpExecArray | null;
    while ((m = global.exec(tituloSemAcento))) {
      intervalos.push([m.index, m.index + m[0].length]);
      if (m[0].length === 0) global.lastIndex++;
    }
  }
  return intervalos;
}

/** Troca por espacos os trechos nos intervalos dados -- mantem o comprimento e os indices dos demais trechos. */
function mascarar(s: string, intervalos: [number, number][]): string {
  if (intervalos.length === 0) return s;
  const chars = s.split("");
  for (const [inicio, fim] of intervalos) {
    for (let i = inicio; i < fim; i++) chars[i] = " ";
  }
  return chars.join("");
}

/**
 * true se algum nome da identidade aparece mencionado na manchete, com a
 * caixa certa (sigla exige maiuscula exata; nome comum nao pode estar todo em
 * minusculas -- "vale a pena" nunca conta).
 *
 * A BUSCA ignora caixa (senao "ASSAÍ AMPLIA LOJA" nunca bateria com o nome da
 * tabela "Assaí"); e a CAIXA DE VERDADE da ocorrencia, no titulo original, e
 * conferida so depois, pela regra acima.
 *
 * Os trechos que casam `naoEAEmpresa` sao mascarados ANTES de procurar o nome
 * -- "Vale do Paraíba" nunca chega a competir com "Vale". A busca roda nas
 * duas versoes do titulo (com e sem acento, mesmos indices) porque o nome da
 * tabela pode ter acento ("Itaú") mesmo quando a manchete nao usa.
 */
function temNomeNoTitulo(titulo: string, tituloSemAcento: string, id: Identidade): boolean {
  const intervalos = indicesDeExclusao(tituloSemAcento, id.naoEAEmpresa);
  const mascOriginal = mascarar(titulo, intervalos);
  const mascSemAcento = mascarar(tituloSemAcento, intervalos);

  for (const nome of id.nomes) {
    const ehSigla = nome === nome.toUpperCase();
    const buscas = [
      { regex: comFronteiraDePalavra(escapar(nome), "gui"), fonte: mascOriginal },
      { regex: comFronteiraDePalavra(escapar(semAcento(nome)), "gui"), fonte: mascSemAcento },
    ];
    for (const { regex, fonte } of buscas) {
      let m: RegExpExecArray | null;
      while ((m = regex.exec(fonte))) {
        // A casca sempre confere pelo texto ORIGINAL na mesma posicao -- e o
        // unico que carrega a caixa de verdade da manchete.
        const ocorrencia = mascOriginal.slice(m.index, m.index + m[0].length);
        if (ehSigla) {
          if (ocorrencia === ocorrencia.toUpperCase()) return true;
        } else if (ocorrencia !== ocorrencia.toLowerCase()) {
          return true;
        }
      }
    }
  }
  return false;
}

/** Fonte conhecida (financeira ou geral), null se aceita, "fonte-desconhecida" senao. */
function motivoDaFonte(n: Noticia, temTicker: boolean): MotivoDeDescarte | null {
  const dominio = n.dominio.replace(/^www\./, "");
  if (FONTES_FINANCEIRAS.has(dominio) || FONTES_GERAIS.has(dominio)) return null;
  // Fonte desconhecida so passa se citar o ticker explicitamente E for .br --
  // e a marca de que quem escreveu e imprensa de mercado, e o ".br" barra o
  // spam estrangeiro que lista tickers so para indexar (visto um .ac.id na amostra).
  if (temTicker && dominio.endsWith(".br")) return null;
  return "fonte-desconhecida";
}

/** Por que a noticia foi descartada, ou null se ela deve entrar na ficha. A ordem das camadas importa. */
export function motivoDoDescarte(n: Noticia, id: Identidade): MotivoDeDescarte | null {
  const tituloSemAcento = semAcento(n.titulo);
  const temTicker = temTickerNoTitulo(n.titulo, id.tickers);
  const temNome = temNomeNoTitulo(n.titulo, tituloSemAcento, id);

  if (!temTicker && !temNome) return "nao-e-a-empresa";
  if (id.ambiguo && !temTicker && !FONTES_FINANCEIRAS.has(n.dominio)) {
    return "fora-da-imprensa-financeira";
  }
  if (NAO_NOTICIA.test(n.titulo)) return "nao-e-noticia";
  if (n.titulo.trim().split(/\s+/).length < PALAVRAS_MINIMAS) return "nao-e-noticia";
  if (PROMOCAO.test(n.titulo) && !temTicker && !OFERTA_DE_MERCADO.test(n.titulo)) {
    return "promocao";
  }
  return motivoDaFonte(n, temTicker);
}

/** Palavras de 4+ letras da manchete, sem acento e minusculas -- os tokens que `agrupar` compara. */
function tokens(titulo: string): Set<string> {
  return new Set(
    semAcento(titulo)
      .toLowerCase()
      .match(/[a-z0-9]{4,}/g) ?? [],
  );
}

/** Fracao de sobreposicao de tokens: |A∩B| / min(|A|,|B|). */
function sobreposicao(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let comuns = 0;
  for (const t of a) if (b.has(t)) comuns++;
  return comuns / Math.min(a.size, b.size);
}

const LIMIAR_DE_MESMA_HISTORIA = 0.6;

/**
 * Agrupa noticias que sao a mesma historia contada por fontes diferentes.
 *
 * Guloso na ordem de entrada: cada noticia entra no primeiro grupo em que
 * alguma manchete ja la dentro bate por tokens, senao abre grupo novo.
 * Comparar so com a primeira do grupo falhava: "Cosan, Rumo e Comgas dizem
 * nao ter sido notificadas..." (InfoMoney) ficava de fora do grupo em que a
 * mesma frase, com os tickers, ja estava -- porque quem abrira o grupo era
 * uma terceira manchete, escrita de outro jeito. O
 * representante e a primeira de fonte financeira, se houver alguma no grupo;
 * senao, a primeira que chegou.
 */
export function agrupar(noticias: Noticia[]): GrupoDeNoticias[] {
  type Grupo = { itens: Noticia[]; tokens: Set<string>[] };
  const grupos: Grupo[] = [];

  for (const n of noticias) {
    const t = tokens(n.titulo);
    const grupo = grupos.find((g) =>
      g.tokens.some((outra) => sobreposicao(t, outra) >= LIMIAR_DE_MESMA_HISTORIA),
    );
    if (grupo) {
      grupo.itens.push(n);
      grupo.tokens.push(t);
    } else {
      grupos.push({ itens: [n], tokens: [t] });
    }
  }

  return grupos.map((g) => {
    const financeira = g.itens.find((n) => FONTES_FINANCEIRAS.has(n.dominio));
    const representante = financeira ?? g.itens[0];
    const maisRecente = g.itens.reduce((max, n) => (n.publicadaEm > max ? n.publicadaEm : max), representante.publicadaEm);

    const outrasFontes: { fonte: string; link: string }[] = [];
    const fontesJaVistas = new Set([representante.fonte]);
    for (const n of g.itens) {
      if (n === representante) continue;
      if (fontesJaVistas.has(n.fonte)) continue;
      fontesJaVistas.add(n.fonte);
      outrasFontes.push({ fonte: n.fonte, link: n.link });
    }

    return { ...representante, publicadaEm: maisRecente, outrasFontes };
  });
}

const MINUTO = 60 * 1000;
const HORA = 60 * MINUTO;
const DIA = 24 * HORA;

const MAXIMO_DE_GRUPOS = 15;

/** Aplica o filtro, deduplica, agrupa por historia e corta em 15 -- o que a ficha mostra. */
export function filtrarNoticias(
  noticias: Noticia[],
  id: Identidade,
  dias: number,
  agora: Date = new Date(),
): ResultadoDasNoticias {
  // O `when:` vai na busca, mas nao se garante sozinho quando ela tem varios
  // `site:` -- o corte que vale e este.
  const desde = new Date(agora.getTime() - dias * DIA).toISOString();
  const descartes: Record<MotivoDeDescarte, number> = {
    "nao-e-a-empresa": 0,
    "fora-da-imprensa-financeira": 0,
    "nao-e-noticia": 0,
    promocao: 0,
    "fonte-desconhecida": 0,
  };

  const linksVistos = new Set<string>();
  const aceitas: Noticia[] = [];
  for (const n of noticias) {
    if (linksVistos.has(n.link) || n.publicadaEm < desde) continue;
    linksVistos.add(n.link);

    const motivo = motivoDoDescarte(n, id);
    if (motivo) {
      descartes[motivo]++;
      continue;
    }
    aceitas.push(n);
  }

  const grupos = agrupar(aceitas).sort((a, b) => b.publicadaEm.localeCompare(a.publicadaEm));

  return {
    grupos: grupos.slice(0, MAXIMO_DE_GRUPOS),
    total: linksVistos.size,
    descartes,
    dias,
  };
}

/** "há N min" / "há N h" / "há N dias", para o rodape de cada noticia. */
export function tempoRelativo(iso: string, agora: Date = new Date()): string {
  const diffMs = Math.max(0, agora.getTime() - new Date(iso).getTime());
  if (diffMs < HORA) return `há ${Math.max(1, Math.round(diffMs / MINUTO))} min`;
  if (diffMs < DIA) return `há ${Math.round(diffMs / HORA)} h`;
  return `há ${Math.round(diffMs / DIA)} dias`;
}
