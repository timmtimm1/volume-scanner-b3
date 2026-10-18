"use client";

import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type PointerEvent as EventoDePonteiro,
  type ReactNode,
} from "react";
import {
  alternarLargura,
  CHAVE_DOS_ARRANJOS,
  iguais,
  moverComSeta,
  normalizar,
  planejar,
  rotuloDaLargura,
  soltar,
  validarItens,
  type Arranjo,
  type Destino,
  type No,
  type PaginaArrumavel,
  type Seta,
} from "@/lib/arranjo";
import { arranjoPadrao, PAGINAS_DE_CAIXAS } from "@/lib/paginas-arrumaveis";
import { useComputador } from "@/lib/useComputador";

/**
 * Organizar: o dono arrasta as caixas de uma pagina no computador e muda a
 * largura delas; o arranjo fica salvo na conta (`/api/arranjos`).
 *
 * A pagina envolve o cabecalho e a grade com `ArranjoDaPagina`; o botao
 * `BotaoOrganizar` vai no cabecalho e a `GradeDeCaixas` recebe as caixas.
 *
 * No celular nada muda: a grade vira uma coluna so, na ordem do padrao, seja
 * qual for o arranjo (as regioes viram `display: contents` e cada caixa leva a
 * sua `order`).
 *
 * O navegador guarda uma copia dos arranjos. Ela e o que se desenha; a rota
 * so a confirma ou corrige. Assim o arranjo do dono aparece ja na primeira
 * pintura (o script do <head> segura as caixas ate o React aplica-lo).
 */

// ---------------------------------------------------------------- copia local

let copiaEmMemoria: string | null = null;
const ouvintes = new Set<() => void>();

function lerCopia(): string | null {
  try {
    return localStorage.getItem(CHAVE_DOS_ARRANJOS);
  } catch {
    return copiaEmMemoria;
  }
}

function gravarCopia(arranjos: Record<string, unknown> | null): void {
  const texto = arranjos && Object.keys(arranjos).length > 0 ? JSON.stringify(arranjos) : null;
  copiaEmMemoria = texto;
  try {
    if (texto === null) localStorage.removeItem(CHAVE_DOS_ARRANJOS);
    else localStorage.setItem(CHAVE_DOS_ARRANJOS, texto);
  } catch {
    // Navegador sem armazenamento: vale a copia em memoria ate recarregar.
  }
  ouvintes.forEach((avisar) => avisar());
}

function arranjosDaCopia(texto: string | null): Record<string, unknown> {
  if (!texto) return {};
  try {
    const dados: unknown = JSON.parse(texto);
    return dados && typeof dados === "object" ? (dados as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function assinarCopia(avisar: () => void): () => void {
  ouvintes.add(avisar);
  // Outra aba salvou: esta acompanha.
  const aoGuardar = (e: StorageEvent) => {
    if (e.key === CHAVE_DOS_ARRANJOS) avisar();
  };
  window.addEventListener("storage", aoGuardar);
  return () => {
    ouvintes.delete(avisar);
    window.removeEventListener("storage", aoGuardar);
  };
}

// ------------------------------------------------------------------ contexto

type Organizar = {
  colunas: number;
  trilhas: string[];
  nomes: Record<string, string>;
  ordemNoCelular: Record<string, number>;
  arranjo: Arranjo;
  podeOrganizar: boolean;
  editando: boolean;
  organizar: () => void;
  mudar: (novo: Arranjo) => void;
};

const Contexto = createContext<Organizar | null>(null);

function useOrganizar(): Organizar {
  const o = useContext(Contexto);
  if (!o) throw new Error("Organizar fora de ArranjoDaPagina");
  return o;
}

const BOTAO =
  "inline-flex h-10 items-center rounded-full px-4 text-[13px] font-bold transition-colors disabled:opacity-40";

export function ArranjoDaPagina({
  pagina,
  children,
}: {
  pagina: PaginaArrumavel;
  children: ReactNode;
}) {
  const definicao = PAGINAS_DE_CAIXAS[pagina];
  if (!definicao) throw new Error(`pagina sem caixas definidas: ${pagina}`);
  const colunas = definicao.trilhas.length;
  const padrao = useMemo(() => arranjoPadrao(definicao), [definicao]);

  const computador = useComputador();
  // `undefined` no servidor e na hidratacao: o HTML sai com o padrao.
  const copia = useSyncExternalStore(assinarCopia, lerCopia, () => undefined);
  const [dono, setDono] = useState(false);
  const [rascunho, setRascunho] = useState<Arranjo | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const salvo = useMemo(
    () => (copia === undefined ? null : validarItens(arranjosDaCopia(copia)[pagina], colunas)),
    [copia, pagina, colunas],
  );
  const podeOrganizar = dono && computador;
  const editando = podeOrganizar && rascunho !== null;
  const arranjo = useMemo(
    () => (editando && rascunho ? rascunho : normalizar(salvo, padrao, colunas)),
    [editando, rascunho, salvo, padrao, colunas],
  );

  // A copia ja foi lida e o arranjo desenhado: as caixas podem aparecer.
  useLayoutEffect(() => {
    if (copia !== undefined) document.documentElement.removeAttribute("data-arranjo");
  }, [copia]);

  // A palavra final e a do banco. So no computador, onde o arranjo aparece.
  useEffect(() => {
    if (!computador) return;
    let cancelada = false;
    fetch("/api/arranjos/", { cache: "no-store" })
      .then(async (r) => {
        if (cancelada) return;
        if (r.status === 401) {
          // Visitante, ou o dono deslogado: o padrao, e nada guardado.
          setDono(false);
          gravarCopia(null);
          return;
        }
        if (!r.ok) return;
        const corpo = (await r.json()) as { arranjos: Record<string, unknown> };
        if (cancelada) return;
        setDono(true);
        gravarCopia(corpo.arranjos);
      })
      .catch(() => {
        // Sem rede: fica a copia que ja estava.
      });
    return () => {
      cancelada = true;
    };
  }, [computador]);

  async function concluir() {
    if (!rascunho) return;
    const voltaAoPadrao = iguais(rascunho, padrao);
    setSalvando(true);
    setErro(null);
    try {
      const r = voltaAoPadrao
        ? await fetch(`/api/arranjos/?pagina=${pagina}`, { method: "DELETE" })
        : await fetch("/api/arranjos/", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pagina, itens: rascunho }),
          });
      if (!r.ok) {
        setErro(
          r.status === 401
            ? "A sessão expirou. Entre de novo para salvar."
            : "Não deu para salvar. Tente de novo.",
        );
        return;
      }
      const arranjos = arranjosDaCopia(lerCopia());
      if (voltaAoPadrao) delete arranjos[pagina];
      else arranjos[pagina] = rascunho;
      gravarCopia(arranjos);
      setRascunho(null);
    } catch {
      setErro("Sem conexão. Tente de novo.");
    } finally {
      setSalvando(false);
    }
  }

  const valor: Organizar = {
    colunas,
    trilhas: definicao.trilhas,
    nomes: Object.fromEntries(definicao.caixas.map((c) => [c.id, c.nome])),
    ordemNoCelular: Object.fromEntries(padrao.map((c, i) => [c.id, i])),
    arranjo,
    podeOrganizar,
    editando,
    organizar: () => {
      setErro(null);
      setRascunho(arranjo);
    },
    mudar: setRascunho,
  };

  return (
    <Contexto.Provider value={valor}>
      {children}
      {editando && rascunho && (
        <div
          role="toolbar"
          aria-label="Organizar caixas"
          className="cartao fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-4 py-2.5 pl-5 pr-2.5 shadow-[var(--sombra)]"
        >
          <div className="flex flex-col">
            <span className="text-[14px] font-extrabold">Organizando</span>
            <span
              aria-live="polite"
              className={`text-[12px] font-semibold ${erro ? "text-baixa" : "text-tinta-3"}`}
            >
              {erro ?? "Arraste as caixas. ↔ muda a largura."}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setRascunho(padrao)}
              disabled={salvando || iguais(rascunho, padrao)}
              className={`${BOTAO} text-tinta-2 hover:text-acento`}
            >
              Restaurar padrão
            </button>
            <button
              type="button"
              onClick={() => {
                setErro(null);
                setRascunho(null);
              }}
              disabled={salvando}
              className={`${BOTAO} border border-linha-2 text-tinta-2 hover:border-acento hover:text-acento`}
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={concluir}
              disabled={salvando}
              className={`${BOTAO} bg-primario text-primario-tinta`}
            >
              {salvando ? "Salvando…" : "Concluir"}
            </button>
          </div>
        </div>
      )}
    </Contexto.Provider>
  );
}

/** O botao do cabecalho. So para o dono, no computador, fora do modo. */
export function BotaoOrganizar() {
  const o = useOrganizar();
  if (!o.podeOrganizar || o.editando) return null;
  return (
    <button
      type="button"
      onClick={o.organizar}
      title="Arrastar as caixas desta página e mudar a largura delas"
      className="hidden h-9 shrink-0 items-center gap-2 rounded-full border border-linha-2 px-3.5 text-[13px] font-bold text-tinta-2 transition-colors hover:border-acento hover:text-acento lg:inline-flex"
    >
      <svg width="15" height="15" viewBox="0 0 20 20" aria-hidden fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinejoin="round">
        <rect x="3" y="3" width="6" height="8" rx="1.5" />
        <rect x="11" y="3" width="6" height="4" rx="1.5" />
        <rect x="11" y="9" width="6" height="8" rx="1.5" />
        <rect x="3" y="13" width="6" height="4" rx="1.5" />
      </svg>
      Organizar
    </button>
  );
}

// --------------------------------------------------------------------- grade

type Faixa = { left: number; right: number };
type Arrasto = { id: string; x: number; y: number; marca: { left: number; top: number; width: number } | null };

/** As colunas da grade na tela, em pixels da janela. */
function colunasNaTela(raiz: HTMLElement): Faixa[] {
  const estilo = getComputedStyle(raiz);
  const larguras = estilo.gridTemplateColumns.split(" ").map(parseFloat);
  const vao = parseFloat(estilo.columnGap) || 0;
  let x = raiz.getBoundingClientRect().left;
  return larguras.map((largura) => {
    const faixa = { left: x, right: x + largura };
    x += largura + vao;
    return faixa;
  });
}

const distancia = (v: number, de: number, ate: number) => (v < de ? de - v : v > ate ? v - ate : 0);

const SETAS: Record<string, Seta> = {
  ArrowUp: "cima",
  ArrowDown: "baixo",
  ArrowLeft: "esquerda",
  ArrowRight: "direita",
};

export function GradeDeCaixas({ caixas }: { caixas: Record<string, ReactNode> }) {
  const o = useOrganizar();
  const raiz = useRef<HTMLDivElement>(null);
  const [arrasto, setArrasto] = useState<Arrasto | null>(null);
  const [focar, setFocar] = useState<string | null>(null);
  const plano = useMemo(() => planejar(o.arranjo, o.colunas), [o.arranjo, o.colunas]);

  // A caixa movida pelo teclado pode ter mudado de lugar na arvore: o foco volta a ela.
  useEffect(() => {
    if (!focar) return;
    raiz.current?.querySelector<HTMLElement>(`[data-caixa="${focar}"] [data-mover]`)?.focus();
  }, [focar, o.arranjo]);

  /** Onde a caixa `id` cai com o ponteiro em (x, y), e onde desenhar a marca. */
  function destinoEm(id: string, x: number, y: number): { destino: Destino; marca: Arrasto["marca"] } | null {
    const grade = raiz.current;
    const item = o.arranjo.find((i) => i.id === id);
    if (!grade || !item) return null;
    const faixas = colunasNaTela(grade);
    let sob = faixas.findIndex((f) => x <= f.right);
    if (sob < 0) sob = faixas.length - 1;
    const coluna = Math.min(Math.max(sob, 0), o.colunas - item.largura);
    const outras = [...grade.querySelectorAll<HTMLElement>("[data-caixa]")]
      .filter((el) => el.dataset.caixa !== id && el.getClientRects().length > 0)
      .map((el) => ({ id: el.dataset.caixa ?? "", r: el.getBoundingClientRect() }));
    if (outras.length === 0) return { destino: { referencia: null, lado: "depois", coluna }, marca: null };

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
    const lado = y < (alvo.r.top + alvo.r.bottom) / 2 ? "antes" : "depois";
    const left = faixas[coluna].left;
    const right = faixas[coluna + item.largura - 1].right;
    return {
      destino: { referencia: alvo.id, lado, coluna },
      marca: { left, width: right - left, top: lado === "antes" ? alvo.r.top - 10 : alvo.r.bottom + 6 },
    };
  }

  function comecarArrasto(e: EventoDePonteiro, id: string) {
    if (e.button !== 0) return;
    e.preventDefault();
    const inicio = { x: e.clientX, y: e.clientY };
    let ponteiro = inicio;
    let ativo = false;
    let quadro = 0;
    const selecao = document.body.style.userSelect;

    const atualizar = () => {
      const achado = destinoEm(id, ponteiro.x, ponteiro.y);
      setArrasto({ id, x: ponteiro.x, y: ponteiro.y, marca: achado?.marca ?? null });
    };
    const mover = (ev: PointerEvent) => {
      ponteiro = { x: ev.clientX, y: ev.clientY };
      if (!ativo && Math.hypot(ponteiro.x - inicio.x, ponteiro.y - inicio.y) < 5) return;
      if (!ativo) document.body.style.userSelect = "none";
      ativo = true;
      atualizar();
    };
    // Perto da borda da janela, a pagina rola sozinha: a Semana e mais alta que a tela.
    const rolar = () => {
      if (ativo) {
        const margem = 80;
        const { y } = ponteiro;
        const passo =
          y < margem ? -(margem - y) / 3 : y > innerHeight - margem ? (y - innerHeight + margem) / 3 : 0;
        if (passo !== 0) {
          window.scrollBy(0, passo);
          atualizar();
        }
      }
      quadro = requestAnimationFrame(rolar);
    };
    const terminar = (soltou: boolean) => {
      cancelAnimationFrame(quadro);
      window.removeEventListener("pointermove", mover);
      window.removeEventListener("pointerup", aoSoltar);
      window.removeEventListener("pointercancel", aoCancelar);
      window.removeEventListener("keydown", aoTeclar);
      document.body.style.userSelect = selecao;
      if (ativo && soltou) {
        const achado = destinoEm(id, ponteiro.x, ponteiro.y);
        if (achado) o.mudar(soltar(o.arranjo, id, achado.destino, o.colunas));
      }
      setArrasto(null);
    };
    const aoSoltar = () => terminar(true);
    const aoCancelar = () => terminar(false);
    const aoTeclar = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") terminar(false);
    };
    window.addEventListener("pointermove", mover);
    window.addEventListener("pointerup", aoSoltar);
    window.addEventListener("pointercancel", aoCancelar);
    window.addEventListener("keydown", aoTeclar);
    quadro = requestAnimationFrame(rolar);
  }

  function caixa(id: string, naGrade: boolean, posicao?: CSSProperties) {
    const item = o.arranjo.find((i) => i.id === id);
    const nome = o.nomes[id] ?? id;
    return (
      <div
        key={id}
        data-caixa={id}
        className={`relative min-w-0 max-lg:order-(--ordem) ${naGrade ? "lg:self-start" : ""} ${
          arrasto?.id === id ? "opacity-35" : ""
        }`}
        style={{ "--ordem": o.ordemNoCelular[id] ?? 0, ...posicao } as CSSProperties}
      >
        <div data-conteudo inert={o.editando}>
          {caixas[id]}
        </div>
        {o.editando && item && (
          <div
            onPointerDown={(e) => comecarArrasto(e, id)}
            className="absolute inset-0 z-20 flex cursor-grab touch-none select-none items-start justify-between gap-2 rounded-[18px] border-2 border-dashed border-acento bg-acento/5 p-2.5 active:cursor-grabbing"
          >
            <button
              type="button"
              data-mover
              aria-label={`Mover ${nome}. Arraste, ou use as setas.`}
              onKeyDown={(e) => {
                const seta = SETAS[e.key];
                if (!seta) return;
                e.preventDefault();
                setFocar(id);
                o.mudar(moverComSeta(o.arranjo, id, seta, o.colunas));
              }}
              className="flex cursor-grab items-center gap-1.5 rounded-full bg-painel px-3 py-1.5 text-[13px] font-extrabold text-acento shadow-[var(--sombra)]"
            >
              <span aria-hidden>⠿</span>
              {nome}
            </button>
            {o.colunas > 1 && (
              <button
                type="button"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => o.mudar(alternarLargura(o.arranjo, id, o.colunas))}
                title="Mudar a largura"
                className="flex items-center gap-1.5 rounded-full bg-painel px-3 py-1.5 text-[12px] font-bold text-tinta-2 shadow-[var(--sombra)] transition-colors hover:text-acento"
              >
                <span aria-hidden>↔</span>
                {rotuloDaLargura(item.largura, o.colunas)}
              </button>
            )}
          </div>
        )}
      </div>
    );
  }

  const pilha = (ids: string[], chave: string, posicao: CSSProperties) => (
    <div key={chave} className="contents lg:flex lg:min-w-0 lg:flex-col lg:gap-4" style={posicao}>
      {ids.map((id) => caixa(id, false))}
    </div>
  );

  const regiao = (trilhas: string[], chave: string, posicao: CSSProperties, filhos: ReactNode) => (
    <div
      key={chave}
      className="contents lg:grid lg:min-w-0 lg:content-start lg:gap-4"
      style={{ gridTemplateColumns: trilhas.join(" "), ...posicao }}
    >
      {filhos}
    </div>
  );

  /** Os filhos de uma regiao que comeca na coluna `de` e tem estas `trilhas`. */
  function desenhar(no: No, de: number, trilhas: string[]): ReactNode {
    const toda: CSSProperties = { gridColumn: "1 / -1" };
    switch (no.tipo) {
      case "caixa":
        return caixa(no.id, true, toda);
      case "pilha":
        return pilha(no.ids, `pilha-${de}`, toda);
      case "lado":
        return no.partes.map((p) => {
          const posicao: CSSProperties = { gridColumn: `${p.inicio - de + 1} / span ${p.largura}`, gridRow: 1 };
          if (p.no.tipo === "pilha") return pilha(p.no.ids, `pilha-${p.inicio}`, posicao);
          const sub = trilhas.slice(p.inicio - de, p.inicio - de + p.largura);
          return regiao(sub, `regiao-${p.inicio}`, posicao, desenhar(p.no, p.inicio, sub));
        });
      case "faixas":
        return no.faixas.map((f, i) => {
          const posicao: CSSProperties = { gridColumn: "1 / -1", gridRow: i + 1 };
          if (f.tipo === "caixa") return caixa(f.id, true, posicao);
          return regiao(trilhas, `faixa-${i}`, posicao, desenhar(f, de, trilhas));
        });
    }
  }

  return (
    <>
      <div
        ref={raiz}
        data-grade
        className="flex flex-col gap-4 lg:grid"
        style={{ gridTemplateColumns: o.trilhas.join(" ") }}
      >
        {plano && desenhar(plano, 0, o.trilhas)}
      </div>
      {arrasto && (
        <>
          {arrasto.marca && (
            <div
              aria-hidden
              className="pointer-events-none fixed z-50 h-1 rounded-full bg-acento"
              style={{ left: arrasto.marca.left, top: arrasto.marca.top, width: arrasto.marca.width }}
            />
          )}
          <div
            aria-hidden
            className="pointer-events-none fixed z-50 rounded-full bg-acento px-3 py-1.5 text-[13px] font-extrabold text-painel shadow-[var(--sombra)]"
            style={{ left: arrasto.x + 14, top: arrasto.y + 14 }}
          >
            ⠿ {o.nomes[arrasto.id] ?? arrasto.id}
          </div>
        </>
      )}
    </>
  );
}
