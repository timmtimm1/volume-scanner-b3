/**
 * O arranjo das caixas de uma pagina no computador: a logica pura do "Organizar".
 *
 * Um arranjo e a lista ORDENADA das caixas, cada uma com a coluna onde comeca e
 * quantas colunas ocupa. A regra de posicao e a de uma grade que "sobe": cada
 * caixa fica logo abaixo da ultima caixa anterior (na ordem) que divide coluna
 * com ela. Caixa na largura toda fica abaixo de tudo o que veio antes; caixas
 * em colunas diferentes empilham cada uma na sua, sem buraco.
 *
 * Essa regra vira CSS puro, sem medir altura nenhuma (`planejar`): a pagina sai
 * do servidor ja arrumada, e o padrao nao pisca antes do arranjo do dono.
 *
 * Sem import de valor: os testes rodam este arquivo direto no Node.
 */

export type ItemDoArranjo = { id: string; coluna: number; largura: number };
export type Arranjo = ItemDoArranjo[];

export const PAGINAS = ["semana", "inicio", "ficha", "historico", "trades", "trade"] as const;
export type PaginaArrumavel = (typeof PAGINAS)[number];

/** Quantas colunas cada pagina tem no computador (as `trilhas` de cada uma). */
export const COLUNAS_DA_PAGINA: Record<PaginaArrumavel, number> = {
  semana: 2,
  inicio: 3,
  ficha: 3,
  historico: 2,
  trades: 1,
  trade: 1,
};

/** Onde o navegador guarda a copia dos arranjos (todas as paginas num objeto). */
export const CHAVE_DOS_ARRANJOS = "vs:arranjos";

/** A largura do `lg:` do Tailwind: daqui para cima a pagina tem colunas. */
export const CONSULTA_DO_COMPUTADOR = "(min-width: 1024px)";

/** O `id` do lugar na barra do topo onde o botao Organizar aparece. */
export const LUGAR_DO_ORGANIZAR = "lugar-do-organizar";

/** No maximo isto de caixas numa pagina; acima disso o pedido e lixo. */
export const MAXIMO_DE_CAIXAS = 40;

const ID = /^[a-z][a-z0-9-]{0,39}$/;

/**
 * Qual pagina arrumavel um caminho abre. Expressoes, e nao funcao, porque o
 * script do <head> usa a mesma lista: uma fonte so para os dois lados.
 */
export const ROTAS: readonly (readonly [string, PaginaArrumavel])[] = [
  ["^/$", "inicio"],
  ["^/semana(/|$)", "semana"],
  ["^/papel/", "ficha"],
  ["^/historico(/|$)", "historico"],
  ["^/trades/\\d+", "trade"],
  ["^/trades/?$", "trades"],
];

export function paginaDoCaminho(caminho: string): PaginaArrumavel | null {
  for (const [expressao, pagina] of ROTAS) {
    if (new RegExp(expressao).test(caminho)) return pagina;
  }
  return null;
}

/**
 * Roda no <head>, antes da primeira pintura. O HTML estatico sai com o arranjo
 * padrao; se este navegador guardou um arranjo do dono para a pagina aberta, as
 * caixas ficam invisiveis ate o React aplicar o arranjo -- em vez de mostrar o
 * padrao e pular. O CSS devolve a visibilidade sozinho depois de 1,5 s, caso o
 * JavaScript nao chegue.
 */
export const SCRIPT_DO_ARRANJO =
  `try{if(matchMedia(${JSON.stringify(CONSULTA_DO_COMPUTADOR)}).matches){` +
  `var a=JSON.parse(localStorage.getItem(${JSON.stringify(CHAVE_DOS_ARRANJOS)})||"{}"),` +
  `r=${JSON.stringify(ROTAS)},p=location.pathname;` +
  `for(var i=0;i<r.length;i++)if(new RegExp(r[i][0]).test(p)){` +
  `if(a&&a[r[i][1]])document.documentElement.setAttribute("data-arranjo","pendente");break}}}catch(e){}`;

function inteiro(v: unknown): v is number {
  return typeof v === "number" && Number.isInteger(v);
}

/**
 * Le um arranjo vindo de fora (pedido da rota, banco, copia do navegador).
 * Devolve null se qualquer coisa estiver fora do formato: nada de meio arranjo.
 */
export function validarItens(dados: unknown, colunas: number): Arranjo | null {
  if (!Array.isArray(dados) || dados.length === 0 || dados.length > MAXIMO_DE_CAIXAS) {
    return null;
  }
  const vistos = new Set<string>();
  const itens: Arranjo = [];
  for (const d of dados) {
    if (typeof d !== "object" || d === null) return null;
    const { id, coluna, largura } = d as Record<string, unknown>;
    if (typeof id !== "string" || !ID.test(id) || vistos.has(id)) return null;
    if (!inteiro(coluna) || !inteiro(largura)) return null;
    if (coluna < 0 || largura < 1 || coluna + largura > colunas) return null;
    vistos.add(id);
    itens.push({ id, coluna, largura });
  }
  return itens;
}

/**
 * O arranjo salvo, conferido contra as caixas que a pagina tem hoje.
 *
 * Caixa que saiu do codigo some; caixa nova entra logo depois da que a precede
 * no padrao (ou no comeco), com a coluna e a largura do padrao. Sem arranjo
 * salvo, vale o padrao.
 */
export function normalizar(
  salvo: Arranjo | null | undefined,
  padrao: Arranjo,
  colunas: number,
): Arranjo {
  const conhecidas = new Set(padrao.map((c) => c.id));
  const postas = new Set<string>();
  const resultado: Arranjo = [];
  for (const item of salvo ?? []) {
    if (!conhecidas.has(item.id) || postas.has(item.id)) continue;
    const largura = Math.min(Math.max(1, item.largura), colunas);
    const coluna = Math.min(Math.max(0, item.coluna), colunas - largura);
    postas.add(item.id);
    resultado.push({ id: item.id, coluna, largura });
  }
  padrao.forEach((item, i) => {
    if (postas.has(item.id)) return;
    let posicao = 0;
    for (let j = i - 1; j >= 0; j--) {
      const k = resultado.findIndex((r) => r.id === padrao[j].id);
      if (k >= 0) {
        posicao = k + 1;
        break;
      }
    }
    resultado.splice(posicao, 0, { ...item });
    postas.add(item.id);
  });
  return resultado;
}

export function iguais(a: Arranjo, b: Arranjo): boolean {
  return (
    a.length === b.length &&
    a.every((x, i) => x.id === b[i].id && x.coluna === b[i].coluna && x.largura === b[i].largura)
  );
}

/**
 * Como desenhar o arranjo com CSS: uma arvore de regioes.
 *
 * - `caixa`: uma caixa ocupando a regiao inteira;
 * - `pilha`: regiao de uma coluna, caixas uma embaixo da outra;
 * - `lado`: regioes vizinhas, independentes (nenhuma caixa cruza a divisa);
 * - `faixas`: regioes uma embaixo da outra, cada uma na largura da regiao.
 *
 * `inicio` das partes e a coluna na pagina (nao na regiao).
 */
export type No =
  | { tipo: "caixa"; id: string }
  | { tipo: "pilha"; ids: string[] }
  | { tipo: "lado"; partes: { inicio: number; largura: number; no: No }[] }
  | { tipo: "faixas"; faixas: No[] };

function cruza(item: ItemDoArranjo, divisa: number): boolean {
  return item.coluna < divisa && divisa < item.coluna + item.largura;
}

function cortes(itens: Arranjo, de: number, ate: number): number[] {
  const achados: number[] = [];
  for (let divisa = de + 1; divisa < ate; divisa++) {
    if (!itens.some((i) => cruza(i, divisa))) achados.push(divisa);
  }
  return achados;
}

function planejarRegiao(itens: Arranjo, de: number, ate: number): No | null {
  if (itens.length === 0) return null;
  if (ate - de === 1) return { tipo: "pilha", ids: itens.map((i) => i.id) };

  // Divisa que nenhuma caixa cruza: dos dois lados, as colunas sao independentes.
  const divisas = cortes(itens, de, ate);
  if (divisas.length > 0) {
    const limites = [de, ...divisas, ate];
    const partes: { inicio: number; largura: number; no: No }[] = [];
    for (let k = 0; k + 1 < limites.length; k++) {
      const [inicio, fim] = [limites[k], limites[k + 1]];
      const no = planejarRegiao(
        itens.filter((i) => i.coluna >= inicio && i.coluna < fim),
        inicio,
        fim,
      );
      if (no) partes.push({ inicio, largura: fim - inicio, no });
    }
    return { tipo: "lado", partes };
  }

  // Toda divisa cruzada: corta na horizontal.
  const faixas: No[] = [];
  const juntar = (no: No | null) => {
    if (!no) return;
    if (no.tipo === "faixas") faixas.push(...no.faixas);
    else faixas.push(no);
  };
  const inteira = itens.findIndex((i) => i.coluna === de && i.largura === ate - de);
  if (inteira >= 0) {
    // A caixa na largura toda fica abaixo de tudo o que veio antes dela.
    juntar(planejarRegiao(itens.slice(0, inteira), de, ate));
    faixas.push({ tipo: "caixa", id: itens[inteira].id });
    juntar(planejarRegiao(itens.slice(inteira + 1), de, ate));
  } else {
    // Sem caixa inteira (so com 3 colunas: uma caixa de 2 em cada divisa): o
    // maior comeco que ainda tem divisa livre vira uma faixa. Uma caixa sozinha
    // menor que a regiao sempre deixa divisa livre, entao a faixa nunca e vazia.
    let n = 1;
    while (n < itens.length && cortes(itens.slice(0, n + 1), de, ate).length > 0) n++;
    juntar(planejarRegiao(itens.slice(0, n), de, ate));
    juntar(planejarRegiao(itens.slice(n), de, ate));
  }
  return faixas.length === 1 ? faixas[0] : { tipo: "faixas", faixas };
}

export function planejar(arranjo: Arranjo, colunas: number): No | null {
  return planejarRegiao(arranjo, 0, colunas);
}

export type Retangulo = { x: number; y: number; w: number; h: number };

/** As colunas da pagina medidas na tela (x relativo a grade) e o vao entre tudo. */
export type Geometria = { colunas: { x: number; w: number }[]; vao: number };

/**
 * Onde cada caixa fica, em pixels relativos a grade, sem desenhar nada.
 *
 * Reproduz o CSS de `GradeDeCaixas` a partir do mesmo plano: e com isto que o
 * arrasto mostra as caixas abrindo espaco ao vivo, so com `transform`, sem
 * trocar a pagina de verdade enquanto o mouse anda.
 *
 * `alturas` traz so as caixas visiveis; caixa sem altura esta escondida
 * (`display: none`) e, como no CSS, nao ocupa lugar nem abre vao numa pilha.
 * Numa sequencia de faixas ela ainda conta como uma linha vazia da grade, com
 * vao dos dois lados -- e o CSS faz o mesmo.
 */
export function posicoes(
  arranjo: Arranjo,
  alturas: Record<string, number>,
  geometria: Geometria,
): Record<string, Retangulo> {
  const { colunas, vao } = geometria;
  const saida: Record<string, Retangulo> = {};
  const largura = (de: number, n: number) => colunas[de + n - 1].x + colunas[de + n - 1].w - colunas[de].x;

  /** Coloca o no a partir de `y`; devolve a altura, ou null se nada foi exibido. */
  function colocar(no: No, de: number, n: number, y: number): number | null {
    switch (no.tipo) {
      case "caixa": {
        const h = alturas[no.id];
        if (h === undefined) return null;
        saida[no.id] = { x: colunas[de].x, y, w: largura(de, n), h };
        return h;
      }
      case "pilha": {
        let topo = y;
        let primeira = true;
        for (const id of no.ids) {
          const h = alturas[id];
          if (h === undefined) continue;
          if (!primeira) topo += vao;
          saida[id] = { x: colunas[de].x, y: topo, w: largura(de, n), h };
          topo += h;
          primeira = false;
        }
        return topo - y;
      }
      case "lado": {
        let maior = 0;
        for (const p of no.partes) maior = Math.max(maior, colocar(p.no, p.inicio, p.largura, y) ?? 0);
        return maior;
      }
      case "faixas": {
        let acumulado = 0;
        let total = 0;
        let exibiu = false;
        no.faixas.forEach((f, i) => {
          const h = colocar(f, de, n, y + acumulado + vao * i);
          acumulado += h ?? 0;
          if (h !== null) {
            total = acumulado + vao * i;
            exibiu = true;
          }
        });
        return exibiu ? total : null;
      }
    }
  }

  const plano = planejar(arranjo, colunas.length);
  if (plano) colocar(plano, 0, colunas.length, 0);
  return saida;
}

function limitar(v: number, minimo: number, maximo: number): number {
  return Math.min(Math.max(v, minimo), maximo);
}

export type Destino = {
  /** A caixa ao lado de quem soltar; null = no fim. */
  referencia: string | null;
  lado: "antes" | "depois";
  /** Coluna sob o ponteiro; a caixa e encaixada para caber. */
  coluna: number;
};

/** Solta a caixa `id` no destino. Mesma largura; coluna ajustada para caber. */
export function soltar(arranjo: Arranjo, id: string, destino: Destino, colunas: number): Arranjo {
  const atual = arranjo.findIndex((i) => i.id === id);
  if (atual < 0) return arranjo;
  const item = arranjo[atual];
  const movido = { ...item, coluna: limitar(destino.coluna, 0, colunas - item.largura) };
  const resto = arranjo.filter((i) => i.id !== id);
  let posicao: number;
  if (destino.referencia === id) {
    posicao = atual;
  } else if (destino.referencia === null) {
    posicao = resto.length;
  } else {
    const k = resto.findIndex((i) => i.id === destino.referencia);
    posicao = k < 0 ? resto.length : destino.lado === "depois" ? k + 1 : k;
  }
  resto.splice(posicao, 0, movido);
  return resto;
}

/** O botao de largura: 1 -> 2 -> ... -> todas -> 1. Sem sair da pagina pela direita. */
export function alternarLargura(arranjo: Arranjo, id: string, colunas: number): Arranjo {
  return arranjo.map((item) => {
    if (item.id !== id) return item;
    const largura = item.largura >= colunas ? 1 : item.largura + 1;
    return { id: item.id, largura, coluna: Math.min(item.coluna, colunas - largura) };
  });
}

export function rotuloDaLargura(largura: number, colunas: number): string {
  if (largura >= colunas) return "Largura toda";
  if (colunas === 2) return "Meia largura";
  return largura === 1 ? "1 coluna" : `${largura} colunas`;
}

function dividemColuna(a: ItemDoArranjo, b: ItemDoArranjo): boolean {
  return a.coluna < b.coluna + b.largura && b.coluna < a.coluna + a.largura;
}

export type Seta = "cima" | "baixo" | "esquerda" | "direita";

/**
 * O mesmo arrasto pelo teclado. Cima e baixo trocam com a caixa vizinha que
 * divide coluna com esta (a que aparece logo acima ou abaixo); esquerda e
 * direita andam uma coluna.
 */
export function moverComSeta(arranjo: Arranjo, id: string, seta: Seta, colunas: number): Arranjo {
  const k = arranjo.findIndex((i) => i.id === id);
  if (k < 0) return arranjo;
  const item = arranjo[k];
  if (seta === "esquerda" || seta === "direita") {
    const coluna = limitar(item.coluna + (seta === "esquerda" ? -1 : 1), 0, colunas - item.largura);
    if (coluna === item.coluna) return arranjo;
    return arranjo.map((i) => (i.id === id ? { ...i, coluna } : i));
  }
  if (seta === "cima") {
    for (let j = k - 1; j >= 0; j--) {
      if (dividemColuna(arranjo[j], item)) {
        return soltar(arranjo, id, { referencia: arranjo[j].id, lado: "antes", coluna: item.coluna }, colunas);
      }
    }
    return arranjo;
  }
  for (let j = k + 1; j < arranjo.length; j++) {
    if (dividemColuna(arranjo[j], item)) {
      return soltar(arranjo, id, { referencia: arranjo[j].id, lado: "depois", coluna: item.coluna }, colunas);
    }
  }
  return arranjo;
}
