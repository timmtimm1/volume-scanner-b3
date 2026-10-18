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
import { createPortal } from "react-dom";
import {
  alternarLargura,
  CHAVE_DOS_ARRANJOS,
  LUGAR_DO_ORGANIZAR,
  iguais,
  moverComSeta,
  normalizar,
  planejar,
  rotuloDaLargura,
  validarItens,
  type Arranjo,
  type No,
  type PaginaArrumavel,
  type Seta,
} from "@/lib/arranjo";
import { arrastar, assentar, retangulos } from "@/lib/arrasto";
import { arranjoPadrao, PAGINAS_DE_CAIXAS, type CaixaDaPagina } from "@/lib/paginas-arrumaveis";
import { useComputador } from "@/lib/useComputador";

/**
 * Organizar: o dono arrasta as caixas de uma pagina no computador e muda a
 * largura delas; o arranjo fica salvo na conta (`/api/arranjos`).
 *
 * A pagina envolve a grade com `ArranjoDaPagina` e passa as caixas para a
 * `GradeDeCaixas`. O botao Organizar vai sozinho para a barra do topo, ao lado
 * do tema: no Inicio e na ficha o titulo mora dentro de uma caixa que se move.
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
  caixas: Record<string, CaixaDaPagina>;
  ordemNoCelular: Record<string, number>;
  arranjo: Arranjo;
  podeOrganizar: boolean;
  editando: boolean;
  organizar: () => void;
  mudar: (novo: Arranjo) => void;
  /** A grade guarda aqui como tirar a foto de antes de uma troca, para deslizar ate a nova. */
  antesDeTrocarRef: { current: (() => void) | null };
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
  const colunas = definicao.trilhas.length;
  const padrao = useMemo(() => arranjoPadrao(definicao), [definicao]);

  const computador = useComputador();
  // `undefined` no servidor e na hidratacao: o HTML sai com o padrao.
  const copia = useSyncExternalStore(assinarCopia, lerCopia, () => undefined);
  const [dono, setDono] = useState(false);
  const [rascunho, setRascunho] = useState<Arranjo | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const antesDeTrocarRef = useRef<(() => void) | null>(null);

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
    caixas: Object.fromEntries(definicao.caixas.map((c) => [c.id, c])),
    ordemNoCelular: Object.fromEntries(padrao.map((c, i) => [c.id, i])),
    arranjo,
    podeOrganizar,
    editando,
    organizar: () => {
      setErro(null);
      setRascunho(arranjo);
    },
    mudar: setRascunho,
    antesDeTrocarRef,
  };

  return (
    <Contexto.Provider value={valor}>
      {children}
      <BotaoOrganizar />
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
              onClick={() => {
                antesDeTrocarRef.current?.();
                setRascunho(padrao);
              }}
              disabled={salvando || iguais(rascunho, padrao)}
              className={`${BOTAO} text-tinta-2 hover:text-acento`}
            >
              Restaurar padrão
            </button>
            <button
              type="button"
              onClick={() => {
                setErro(null);
                antesDeTrocarRef.current?.();
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

const semAviso = () => () => {};

/** O botao da barra do topo. So para o dono, no computador, fora do modo. */
function BotaoOrganizar() {
  const o = useOrganizar();
  // O lugar esta no layout raiz, que ja existe quando a pagina monta.
  const lugar = useSyncExternalStore(
    semAviso,
    () => document.getElementById(LUGAR_DO_ORGANIZAR),
    () => null,
  );
  if (!lugar || !o.podeOrganizar || o.editando) return null;
  return createPortal(
    <button
      type="button"
      onClick={o.organizar}
      title="Arrastar as caixas desta página e mudar a largura delas"
      className="flex h-11 shrink-0 items-center gap-2 rounded-full border border-linha bg-painel px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-acento"
    >
      <svg width="15" height="15" viewBox="0 0 20 20" aria-hidden fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinejoin="round">
        <rect x="3" y="3" width="6" height="8" rx="1.5" />
        <rect x="11" y="3" width="6" height="4" rx="1.5" />
        <rect x="11" y="9" width="6" height="8" rx="1.5" />
        <rect x="3" y="13" width="6" height="4" rx="1.5" />
      </svg>
      Organizar
    </button>,
    lugar,
  );
}

// --------------------------------------------------------------------- grade

const SETAS: Record<string, Seta> = {
  ArrowUp: "cima",
  ArrowDown: "baixo",
  ArrowLeft: "esquerda",
  ArrowRight: "direita",
};

export function GradeDeCaixas({ caixas }: { caixas: Record<string, ReactNode> }) {
  const o = useOrganizar();
  const raiz = useRef<HTMLDivElement>(null);
  const vaga = useRef<HTMLDivElement>(null);
  const camada = useRef<HTMLDivElement>(null);
  const [focar, setFocar] = useState<string | null>(null);
  const plano = useMemo(() => planejar(o.arranjo, o.colunas), [o.arranjo, o.colunas]);
  /** A foto de antes de uma troca: depois de o React desenhar, cada caixa desliza dela ate o lugar novo. */
  const pouso = useRef<{ antes: Map<string, DOMRect>; entrando: string | null; removerFantasma?: () => void } | null>(null);

  // A caixa movida pelo teclado pode ter mudado de lugar na arvore: o foco volta a ela.
  useEffect(() => {
    if (!focar) return;
    raiz.current?.querySelector<HTMLElement>(`[data-caixa="${focar}"] [data-mover]`)?.focus();
  }, [focar, o.arranjo]);

  useLayoutEffect(() => {
    const p = pouso.current;
    if (!p || !raiz.current) return;
    pouso.current = null;
    assentar(raiz.current, vaga.current, p.antes, p.entrando, p.removerFantasma);
  }, [o.arranjo]);

  // Cancelar e Restaurar padrao (na barra) tambem deslizam.
  const { antesDeTrocarRef } = o;
  useEffect(() => {
    antesDeTrocarRef.current = () => {
      pouso.current = { antes: retangulos(raiz.current), entrando: null };
    };
    return () => {
      antesDeTrocarRef.current = null;
    };
  }, [antesDeTrocarRef]);

  /** Troca o arranjo deslizando as caixas (largura, setas). */
  function mudarDeslizando(novo: Arranjo) {
    pouso.current = { antes: retangulos(raiz.current), entrando: null };
    o.mudar(novo);
  }

  function comecarArrasto(e: EventoDePonteiro, id: string) {
    if (e.button !== 0 || !raiz.current || !vaga.current || !camada.current) return;
    e.preventDefault();
    const [grade, lugarVazio] = [raiz.current, vaga.current];
    arrastar({
      x: e.clientX,
      y: e.clientY,
      id,
      arranjo: o.arranjo,
      colunas: o.colunas,
      raiz: grade,
      vaga: lugarVazio,
      camada: camada.current,
      aoPousar: ({ novo, antes, removerFantasma }) => {
        if (novo) {
          pouso.current = { antes, entrando: id, removerFantasma };
          o.mudar(novo);
        } else {
          assentar(grade, lugarVazio, antes, id, removerFantasma);
        }
      },
    });
  }

  /**
   * `onde`: direto na grade (alinha no topo da celula), numa pilha, ou como a
   * ultima da pilha -- a unica posicao em que uma caixa `fixa` pode acompanhar
   * a rolagem sem passar por cima das caixas de baixo.
   */
  function caixa(id: string, onde: "grade" | "pilha" | "fim-da-pilha", posicao?: CSSProperties) {
    const item = o.arranjo.find((i) => i.id === id);
    const definicao = o.caixas[id];
    const nome = definicao?.nome ?? id;
    const classes = [
      "relative min-w-0 max-lg:order-(--ordem)",
      onde === "grade" ? "lg:self-start" : "",
      onde === "fim-da-pilha" && definicao?.fixa ? "lg:sticky lg:top-4 lg:z-10" : "",
      definicao?.soComputador ? "max-lg:hidden" : "",
    ];
    return (
      <div
        key={id}
        data-caixa={id}
        className={classes.filter(Boolean).join(" ")}
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
                mudarDeslizando(moverComSeta(o.arranjo, id, seta, o.colunas));
              }}
              className="flex min-w-0 cursor-grab items-center gap-1.5 whitespace-nowrap rounded-full bg-painel px-3 py-1.5 text-[13px] font-extrabold text-acento shadow-[var(--sombra)]"
            >
              <span aria-hidden>⠿</span>
              <span className="truncate">{nome}</span>
            </button>
            {o.colunas > 1 && (
              <button
                type="button"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => mudarDeslizando(alternarLargura(o.arranjo, id, o.colunas))}
                title="Mudar a largura"
                className="flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-painel px-3 py-1.5 text-[12px] font-bold text-tinta-2 shadow-[var(--sombra)] transition-colors hover:text-acento"
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
      {ids.map((id, i) => caixa(id, i === ids.length - 1 ? "fim-da-pilha" : "pilha"))}
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
        return caixa(no.id, "grade", toda);
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
          if (f.tipo === "caixa") return caixa(f.id, "grade", posicao);
          return regiao(trilhas, `faixa-${i}`, posicao, desenhar(f, de, trilhas));
        });
    }
  }

  return (
    <>
      <div
        ref={raiz}
        data-grade
        // `content-start`: a altura minima que o arrasto poe na grade nao estica as linhas.
        className="flex flex-col gap-4 lg:relative lg:grid lg:content-start"
        style={{ gridTemplateColumns: o.trilhas.join(" ") }}
      >
        {/* O lugar vazio onde a caixa arrastada vai cair (lib/arrasto.ts). */}
        <div
          ref={vaga}
          data-vaga
          aria-hidden
          className="pointer-events-none absolute left-0 top-0 hidden rounded-[18px] border-2 border-dashed border-acento/60 bg-acento/5"
        />
        {plano && desenhar(plano, 0, o.trilhas)}
      </div>
      {/* A copia da caixa que segue o mouse. */}
      <div ref={camada} aria-hidden className="pointer-events-none fixed left-0 top-0 z-[60] hidden" />
    </>
  );
}
