/**
 * O arrasto fluido do Organizar, como o de um app na tela do iPhone.
 *
 * A caixa levanta (sombra, um pouco maior) e segue o mouse; as outras deslizam
 * para abrir espaco onde ela vai cair, e um lugar vazio mostra onde e com que
 * largura. Ao soltar, ela voa para o lugar e assenta.
 *
 * Enquanto o mouse anda, nada passa pelo React: as caixas se movem so com
 * `transform`, para as posicoes que `posicoes` calcula para o arranjo de
 * previa, e a pagina de verdade nao muda (nenhum grafico e redesenhado). So ao
 * soltar o arranjo novo vai para o React; `assentar` entao faz o FLIP: cada
 * caixa parte de onde estava na tela e desliza ate o lugar novo, entao nada
 * pula -- nem se a conta da previa errar por um pixel.
 */

import { iguais, posicoes, soltar } from "./arranjo";
import type { Arranjo, Destino, Geometria, Retangulo } from "./arranjo";

export const MOLA = "cubic-bezier(0.2, 0.9, 0.3, 1)";
export const DURACAO = 260;
const VOO = 220;
const SUMIR = 140;
/** Parado sobre um lugar por isto antes de abrir espaco: sem isto a grade pula a cada pixel. */
const PAUSA = 110;
const LIMIAR = 5;
/** Caixa mais alta que isto da janela vai cortada, com um esmaecido embaixo. */
const ALTURA_MAXIMA = 0.6;
const SOMBRA = "0 22px 50px rgb(20 18 60 / 0.28), 0 4px 12px rgb(20 18 60 / 0.12)";

export function semMovimento(): boolean {
  return typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function caixasVisiveis(raiz: HTMLElement): HTMLElement[] {
  return [...raiz.querySelectorAll<HTMLElement>("[data-caixa]")].filter((el) => el.getClientRects().length > 0);
}

/** Onde cada caixa esta na tela agora (com qualquer `transform` em curso). */
export function retangulos(raiz: HTMLElement | null): Map<string, DOMRect> {
  const mapa = new Map<string, DOMRect>();
  if (!raiz) return mapa;
  for (const el of caixasVisiveis(raiz)) mapa.set(el.dataset.caixa ?? "", el.getBoundingClientRect());
  return mapa;
}

/**
 * Depois de o React desenhar o arranjo novo: limpa o que o arrasto pos nas
 * caixas e faz cada uma deslizar de onde estava (`antes`) ate onde ficou. A
 * caixa `entrando` (a que foi solta) aparece no lugar enquanto o fantasma some.
 */
export function assentar(
  raiz: HTMLElement,
  vaga: HTMLElement | null,
  antes: Map<string, DOMRect>,
  entrando: string | null,
  removerFantasma?: () => void,
): void {
  const tempo = semMovimento() ? 0 : DURACAO;
  raiz.removeAttribute("data-arrastando");
  raiz.style.minHeight = "";
  if (vaga) vaga.style.display = "";
  const todas = [...raiz.querySelectorAll<HTMLElement>("[data-caixa]")];
  for (const el of todas) {
    el.style.transition = "none";
    el.style.transform = "";
  }
  const mexer: HTMLElement[] = [];
  let nova: HTMLElement | null = null;
  for (const el of caixasVisiveis(raiz)) {
    const id = el.dataset.caixa ?? "";
    if (id === entrando) {
      nova = el;
      el.style.opacity = "0";
      continue;
    }
    const a = antes.get(id);
    if (!a) continue;
    const b = el.getBoundingClientRect();
    const dx = a.left - b.left;
    const dy = a.top - b.top;
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue;
    el.style.transform = `translate(${dx}px, ${dy}px)`;
    mexer.push(el);
  }
  // Forca o navegador a aplicar o ponto de partida antes de ligar a transicao.
  void raiz.offsetWidth;
  requestAnimationFrame(() => {
    for (const el of mexer) {
      el.style.transition = tempo ? `transform ${tempo}ms ${MOLA}` : "";
      el.style.transform = "";
    }
    if (nova) {
      nova.style.transition = tempo ? `opacity ${SUMIR}ms ease-out` : "";
      nova.style.opacity = "";
    }
    removerFantasma?.();
    setTimeout(() => {
      for (const el of [...mexer, nova]) if (el) el.style.transition = "";
    }, tempo + 50);
  });
}

/** Uma copia visual da caixa, graficos inclusive (o `cloneNode` deixa o canvas em branco). */
function copiar(caixa: HTMLElement): HTMLElement {
  const fonte = caixa.querySelector<HTMLElement>(":scope > [data-conteudo]") ?? caixa;
  const copia = fonte.cloneNode(true) as HTMLElement;
  const origem = fonte.querySelectorAll("canvas");
  const destino = copia.querySelectorAll("canvas");
  origem.forEach((canvas, i) => {
    try {
      destino[i]?.getContext("2d")?.drawImage(canvas, 0, 0);
    } catch {
      // Canvas que nao deixa copiar fica em branco no fantasma; a caixa de verdade nao muda.
    }
  });
  copia.removeAttribute("inert");
  return copia;
}

export type Pouso = {
  /** O arranjo novo, ou null se a caixa voltou para onde estava. */
  novo: Arranjo | null;
  antes: Map<string, DOMRect>;
  removerFantasma: () => void;
};

export type OpcoesDoArrasto = {
  x: number;
  y: number;
  id: string;
  arranjo: Arranjo;
  colunas: number;
  raiz: HTMLElement;
  /** O lugar vazio, dentro da grade (absoluto). */
  vaga: HTMLElement;
  /** Onde o fantasma vive (fixo, por cima da pagina). */
  camada: HTMLElement;
  aoPousar: (pouso: Pouso) => void;
};

const distancia = (v: number, de: number, ate: number) => (v < de ? de - v : v > ate ? v - ate : 0);

/** Comeca a acompanhar o ponteiro. Vira arrasto so depois de `LIMIAR` px; antes disso e clique. */
export function arrastar(op: OpcoesDoArrasto): void {
  const { id, arranjo, colunas, raiz, vaga, camada } = op;
  const item = arranjo.find((i) => i.id === id);
  if (!item) return;
  const inicio = { x: op.x, y: op.y };
  let ponteiro = inicio;
  let ativo = false;
  let terminado = false;
  let quadro = 0;
  let pausa: ReturnType<typeof setTimeout> | undefined;
  let pendente: Arranjo | null = null;
  let previa = arranjo;

  // Medidas tiradas uma vez, quando o arrasto comeca.
  let geometria: Geometria = { colunas: [], vao: 0 };
  const alturas: Record<string, number> = {};
  let inicial: Record<string, Retangulo> = {};
  /** O quanto a tela difere da conta em cada caixa (a previa a sticky, arredondamento). */
  const correcao: Record<string, { x: number; y: number }> = {};
  const elementos = new Map<string, HTMLElement>();
  let alturaDaGrade = 0;
  let largura = 0;
  let agarre = { x: 0, y: 0 };
  const casca = document.createElement("div");
  const selecao = document.body.style.userSelect;

  function medir() {
    const r = raiz.getBoundingClientRect();
    const estilo = getComputedStyle(raiz);
    const vao = parseFloat(estilo.columnGap) || 0;
    let x = 0;
    geometria = {
      colunas: estilo.gridTemplateColumns.split(" ").map((v) => {
        const coluna = { x, w: parseFloat(v) };
        x += coluna.w + vao;
        return coluna;
      }),
      vao: parseFloat(estilo.rowGap) || vao,
    };
    for (const el of caixasVisiveis(raiz)) {
      const cid = el.dataset.caixa ?? "";
      elementos.set(cid, el);
      alturas[cid] = el.getBoundingClientRect().height;
    }
    inicial = posicoes(arranjo, alturas, geometria);
    for (const [cid, el] of elementos) {
      const b = el.getBoundingClientRect();
      const p = inicial[cid];
      if (p) correcao[cid] = { x: b.left - r.left - p.x, y: b.top - r.top - p.y };
    }
    alturaDaGrade = raiz.getBoundingClientRect().height;
  }

  function moverFantasma() {
    camada.style.transform = `translate3d(${ponteiro.x - agarre.x}px, ${ponteiro.y - agarre.y}px, 0)`;
  }

  /** Onde, na grade, a caixa fica no arranjo `p` (corrigido para a tela). */
  function lugar(p: Record<string, Retangulo>): Retangulo {
    const alvo = p[id] ?? inicial[id];
    const c = correcao[id] ?? { x: 0, y: 0 };
    return { x: alvo.x + c.x, y: alvo.y + c.y, w: alvo.w, h: alvo.h };
  }

  function mostrarVaga(p: Record<string, Retangulo>) {
    const l = lugar(p);
    vaga.style.display = "block";
    vaga.style.width = `${l.w}px`;
    vaga.style.height = `${l.h}px`;
    vaga.style.transform = `translate(${l.x}px, ${l.y}px)`;
  }

  function levantar() {
    medir();
    const el = elementos.get(id);
    if (!el) return;
    const r = el.getBoundingClientRect();
    largura = r.width;
    const visivel = Math.min(r.height, innerHeight * ALTURA_MAXIMA);
    agarre = { x: inicio.x - r.left, y: Math.min(inicio.y - r.top, visivel - 24) };

    Object.assign(casca.style, {
      width: `${r.width}px`,
      maxHeight: `${ALTURA_MAXIMA * 100}vh`,
      overflow: "hidden",
      borderRadius: "18px",
      transformOrigin: `${agarre.x}px ${agarre.y}px`,
      transition: `transform 180ms ${MOLA}, box-shadow 180ms ${MOLA}`,
    });
    if (r.height > visivel) casca.style.maskImage = "linear-gradient(to bottom, #000 80%, transparent)";
    casca.replaceChildren(copiar(el));
    camada.replaceChildren(casca);
    camada.style.display = "block";
    moverFantasma();
    requestAnimationFrame(() => {
      casca.style.transform = "scale(1.03)";
      casca.style.boxShadow = SOMBRA;
    });

    el.style.opacity = "0";
    raiz.setAttribute("data-arrastando", "");
    raiz.style.minHeight = `${alturaDaGrade}px`;
    mostrarVaga(inicial);
    document.documentElement.style.cursor = "grabbing";
    document.body.style.userSelect = "none";
  }

  /** Mostra a previa do arranjo `novo`: as outras deslizam, a vaga vai para o lugar. */
  function aplicar(novo: Arranjo) {
    previa = novo;
    const p = posicoes(novo, alturas, geometria);
    let fundo = alturaDaGrade;
    for (const [cid, el] of elementos) {
      if (cid === id) continue;
      const a = inicial[cid];
      const b = p[cid];
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      el.style.transform = dx || dy ? `translate(${dx}px, ${dy}px)` : "";
    }
    for (const r of Object.values(p)) fundo = Math.max(fundo, r.y + r.h);
    raiz.style.minHeight = `${fundo}px`;
    mostrarVaga(p);
  }

  /** O arranjo que o ponteiro pede agora; null = continuar como esta (sobre a vaga). */
  function pedido(): Arranjo | null {
    const v = vaga.getBoundingClientRect();
    const { x, y } = ponteiro;
    if (x >= v.left && x <= v.right && y >= v.top && y <= v.bottom) return null;
    const r = raiz.getBoundingClientRect();
    let sob = geometria.colunas.findIndex((c) => x <= r.left + c.x + c.w);
    if (sob < 0) sob = geometria.colunas.length - 1;
    const coluna = Math.min(Math.max(sob, 0), colunas - (item?.largura ?? 1));
    const outras = [...elementos]
      .filter(([cid]) => cid !== id)
      .map(([cid, el]) => ({ id: cid, r: el.getBoundingClientRect() }));
    let destino: Destino = { referencia: null, lado: "depois", coluna };
    if (outras.length > 0) {
      // A caixa sob o ponteiro; fora de todas, a mais perto na mesma coluna.
      const naColuna = outras.filter((c) => x >= c.r.left && x <= c.r.right);
      const candidatas = naColuna.length > 0 ? naColuna : outras;
      let alvo = candidatas[0];
      let menor = Infinity;
      for (const c of candidatas) {
        const d = distancia(y, c.r.top, c.r.bottom) + distancia(x, c.r.left, c.r.right);
        if (d < menor) {
          menor = d;
          alvo = c;
        }
      }
      destino = { referencia: alvo.id, lado: y < (alvo.r.top + alvo.r.bottom) / 2 ? "antes" : "depois", coluna };
    }
    return soltar(arranjo, id, destino, colunas);
  }

  function avaliar() {
    const novo = pedido();
    if (novo === null || iguais(novo, previa)) {
      clearTimeout(pausa);
      pendente = null;
      return;
    }
    if (pendente && iguais(novo, pendente)) return;
    pendente = novo;
    clearTimeout(pausa);
    pausa = setTimeout(() => {
      if (pendente) aplicar(pendente);
      pendente = null;
    }, PAUSA);
  }

  const mover = (ev: PointerEvent) => {
    ponteiro = { x: ev.clientX, y: ev.clientY };
    if (!ativo) {
      if (Math.hypot(ponteiro.x - inicio.x, ponteiro.y - inicio.y) < LIMIAR) return;
      ativo = true;
      levantar();
    }
    moverFantasma();
    avaliar();
  };

  // Perto da borda da janela a pagina rola sozinha: a Semana e mais alta que a tela.
  const rolar = () => {
    if (ativo) {
      const margem = 80;
      const { y } = ponteiro;
      const passo = y < margem ? -(margem - y) / 3 : y > innerHeight - margem ? (y - innerHeight + margem) / 3 : 0;
      if (passo !== 0) {
        window.scrollBy(0, passo);
        avaliar();
      }
    }
    quadro = requestAnimationFrame(rolar);
  };

  function removerFantasma() {
    const tempo = semMovimento() ? 0 : SUMIR;
    camada.style.transition = `opacity ${tempo}ms ease-out`;
    camada.style.opacity = "0";
    setTimeout(() => {
      camada.replaceChildren();
      for (const p of ["display", "opacity", "transition", "transform"] as const) camada.style[p] = "";
    }, tempo + 20);
  }

  function terminar(cancelou: boolean) {
    if (terminado) return;
    terminado = true;
    cancelAnimationFrame(quadro);
    clearTimeout(pausa);
    window.removeEventListener("pointermove", mover);
    window.removeEventListener("pointerup", aoSoltar);
    window.removeEventListener("pointercancel", aoCancelar);
    window.removeEventListener("keydown", aoTeclar);
    document.documentElement.style.cursor = "";
    document.body.style.userSelect = selecao;
    if (!ativo) return;

    // Cancelar (Esc) e soltar no lugar de origem: as outras voltam, e ela voa de volta.
    if (cancelou) aplicar(arranjo);
    const tempo = semMovimento() ? 0 : VOO;
    const r = raiz.getBoundingClientRect();
    const alvo = lugar(posicoes(previa, alturas, geometria));
    const agora = casca.getBoundingClientRect();
    // Troca a origem da escala para o canto sem mexer na tela, e voa ate a vaga.
    casca.style.transition = "none";
    casca.style.transformOrigin = "0 0";
    casca.style.transform = `scale(${agora.width / largura})`;
    camada.style.transform = `translate3d(${agora.left}px, ${agora.top}px, 0)`;
    void camada.offsetWidth;
    camada.style.transition = tempo ? `transform ${tempo}ms ${MOLA}` : "";
    casca.style.transition = tempo ? `transform ${tempo}ms ${MOLA}, box-shadow ${tempo}ms ${MOLA}` : "";
    camada.style.transform = `translate3d(${r.left + alvo.x}px, ${r.top + alvo.y}px, 0)`;
    casca.style.transform = `scale(${alvo.w / largura})`;
    casca.style.boxShadow = "none";

    setTimeout(() => {
      op.aoPousar({
        novo: iguais(previa, arranjo) ? null : previa,
        antes: retangulos(raiz),
        removerFantasma,
      });
    }, tempo);
  }

  const aoSoltar = () => terminar(false);
  const aoCancelar = () => terminar(true);
  const aoTeclar = (ev: KeyboardEvent) => {
    if (ev.key === "Escape") terminar(true);
  };
  window.addEventListener("pointermove", mover);
  window.addEventListener("pointerup", aoSoltar);
  window.addEventListener("pointercancel", aoCancelar);
  window.addEventListener("keydown", aoTeclar);
  quadro = requestAnimationFrame(rolar);
}
