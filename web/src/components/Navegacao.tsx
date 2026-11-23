"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { LUGAR_DO_ORGANIZAR } from "@/lib/arranjo";
import { useTema } from "@/lib/tema";

/**
 * Barra do topo com as secoes em pilula no computador; pilula flutuante embaixo
 * no celular, onde o polegar alcanca.
 *
 * No celular so os icones, o ativo destacado pelo fundo. Com seis secoes mais o
 * botao do tema, o ativo com nome comprimia os outros para 38px a 390px e 32px a
 * 360px, abaixo dos 44px de alvo de toque. So icones: 48px cada (44px no minimo
 * quando a tela aperta), e o nome fica no `aria-label` e no `title`.
 *
 * Cripto e o foco desde 23/11/2026: as secoes das acoes ficam no menu "Acoes".
 */

type Item = { href: string; nome: string; icone: React.ReactNode };

const traco = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const ITENS: Item[] = [
  {
    href: "/cripto",
    nome: "Cripto",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden {...traco}>
        <circle cx="10" cy="10" r="7" />
        <path d="M8 6.5v7M8 6.5h2.6a1.7 1.7 0 0 1 0 3.5H8M8 10h3a1.75 1.75 0 0 1 0 3.5H8M9.5 5v1.5M9.5 13.5V15" />
      </svg>
    ),
  },
  {
    href: "/patrimonio",
    nome: "Patrimônio",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden {...traco}>
        <path d="M3 3v14h14" />
        <path d="M6 13l3-3 2.5 2L16 7" />
      </svg>
    ),
  },
  {
    href: "/trades",
    nome: "Trades",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden {...traco}>
        <path d="M3 15l4.5-6 3.5 4 6-8" />
        <path d="M13.5 5H17v3.5" />
      </svg>
    ),
  },
  {
    href: "/alertas",
    nome: "Alertas",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden {...traco}>
        <path d="M10 3a4.5 4.5 0 0 0-4.5 4.5c0 3.5-1.5 4.5-1.5 4.5h12s-1.5-1-1.5-4.5A4.5 4.5 0 0 0 10 3z" />
        <path d="M8.5 15a1.6 1.6 0 0 0 3 0" />
      </svg>
    ),
  },
];

/** As secoes da B3, em segundo plano desde 23/11/2026. */
const ACOES: Item[] = [
  {
    href: "/setups",
    nome: "Setups",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden {...traco}>
        <path d="M7 2.5v3M7 13.5v4" />
        <rect x="5" y="5.5" width="4" height="8" rx="1" />
        <path d="M12 11.5l2.5-3 2.5 3M14.5 8.5v8" />
      </svg>
    ),
  },
  {
    href: "/",
    nome: "Scanner",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden {...traco}>
        <path d="M3 3h6v6H3zM11 3h6v6h-6zM3 11h6v6H3zM11 11h6v6h-6z" />
      </svg>
    ),
  },
  {
    href: "/historico",
    nome: "Histórico",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden {...traco}>
        <path d="M10 5v5l3 2" />
        <circle cx="10" cy="10" r="7" />
      </svg>
    ),
  },
  {
    href: "/semana",
    nome: "Semana",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden {...traco}>
        <rect x="3" y="4" width="14" height="13" rx="2" />
        <path d="M3 8h14M7 2.5v3M13 2.5v3" />
        <path d="M6 14.5l2.5-2.5 2 1.5 3.5-3.5" />
      </svg>
    ),
  },
  {
    href: "/papeis",
    nome: "Papéis",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden {...traco}>
        <circle cx="10" cy="10" r="7" />
        <path d="M3 10h14M10 3c2 2.5 2 11.5 0 14M10 3c-2 2.5-2 11.5 0 14" />
      </svg>
    ),
  },
];

function ativo(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/papel/");
  return pathname.startsWith(href);
}

function Marca() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" aria-hidden>
      <rect x="2" y="13" width="3.4" height="8" rx="1" fill="var(--lavanda)" />
      <rect x="7" y="9" width="3.4" height="12" rx="1" fill="var(--lavanda)" />
      <rect x="12" y="3" width="3.4" height="18" rx="1" fill="var(--evento)" />
      <rect x="17" y="11" width="3.4" height="10" rx="1" fill="var(--acento)" />
    </svg>
  );
}

function BotaoDoTema({ className = "" }: { className?: string }) {
  const { tema, alternar } = useTema();
  const escuro = tema === "escuro";
  return (
    <button
      type="button"
      onClick={alternar}
      aria-label={escuro ? "Usar tema claro" : "Usar tema escuro"}
      title={escuro ? "Tema claro" : "Tema escuro"}
      className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-tinta-2 transition-colors hover:text-acento ${className}`}
    >
      {escuro ? (
        <svg width="19" height="19" viewBox="0 0 20 20" aria-hidden {...traco}>
          <circle cx="10" cy="10" r="3.6" />
          <path d="M10 2.5v1.8M10 15.7v1.8M2.5 10h1.8M15.7 10h1.8M4.7 4.7l1.3 1.3M14 14l1.3 1.3M4.7 15.3L6 14M14 6l1.3-1.3" />
        </svg>
      ) : (
        <svg width="19" height="19" viewBox="0 0 20 20" aria-hidden {...traco}>
          <path d="M16.5 12.2A6.8 6.8 0 0 1 7.8 3.5a6.8 6.8 0 1 0 8.7 8.7z" />
        </svg>
      )}
    </button>
  );
}

/** O menu das acoes: abre para baixo no computador e para cima na barra do celular. */
function MenuDeAcoes({ pathname, celular = false }: { pathname: string; celular?: boolean }) {
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  const on = ACOES.some((item) => ativo(pathname, item.href));

  useEffect(() => {
    if (!aberto) return;
    const aoClicar = (e: PointerEvent) => {
      if (!caixa.current?.contains(e.target as Node)) setAberto(false);
    };
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAberto(false);
    };
    document.addEventListener("pointerdown", aoClicar);
    document.addEventListener("keydown", aoTeclar);
    return () => {
      document.removeEventListener("pointerdown", aoClicar);
      document.removeEventListener("keydown", aoTeclar);
    };
  }, [aberto]);

  const icone = (
    <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden {...traco}>
      <path d="M4 17V9M10 17V3M16 17v-5" />
    </svg>
  );
  return (
    <div ref={caixa} className={`relative ${celular ? "flex min-w-10 max-w-12 flex-1" : ""}`}>
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        aria-haspopup="menu"
        aria-label="Ações"
        title="Ações"
        className={
          celular
            ? `flex h-12 w-full items-center justify-center rounded-full transition-colors ${
                on ? "bg-primario text-primario-tinta" : "text-tinta-3"
              }`
            : `flex h-10 items-center gap-2 rounded-full px-5 text-[14px] transition-colors ${
                on ? "bg-primario font-bold text-primario-tinta" : "font-semibold text-tinta-2 hover:text-tinta"
              }`
        }
      >
        {icone}
        {!celular && "Ações"}
        {!celular && <span aria-hidden className="text-[11px]">▾</span>}
      </button>
      {aberto && (
        <div
          role="menu"
          className={`absolute right-0 z-40 flex w-48 flex-col gap-0.5 rounded-2xl border border-linha bg-painel p-1.5 shadow-[var(--sombra)] ${
            celular ? "bottom-full mb-3" : "top-full mt-2"
          }`}
        >
          {ACOES.map((item) => {
            const atual = ativo(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                role="menuitem"
                aria-current={atual ? "page" : undefined}
                onClick={() => setAberto(false)}
                className={`flex h-11 items-center gap-2.5 rounded-xl px-3 text-[14px] font-semibold transition-colors ${
                  atual ? "bg-painel-2 font-bold text-acento" : "text-tinta-2 hover:bg-painel-2 hover:text-tinta"
                }`}
              >
                {item.icone}
                {item.nome}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function Navegacao() {
  const pathname = usePathname();

  return (
    <>
      <header className="mx-auto hidden w-full max-w-[1440px] items-center gap-6 px-6 pt-4 md:flex">
        <Link href="/" className="flex w-[280px] items-center gap-2.5">
          <Marca />
          <span className="flex flex-col">
            <span className="text-[19px] font-extrabold tracking-tight">volume·scanner</span>
            <span className="rotulo !text-[10px]">B3 · volume anômalo</span>
          </span>
        </Link>

        <nav className="flex flex-1 justify-center">
          <div className="flex gap-1 rounded-full border border-linha bg-painel p-1.5">
            {ITENS.map((item) => {
              const on = ativo(pathname, item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={on ? "page" : undefined}
                  className={`flex h-10 items-center gap-2 rounded-full px-5 text-[14px] transition-colors ${
                    on
                      ? "bg-primario font-bold text-primario-tinta"
                      : "font-semibold text-tinta-2 hover:text-tinta"
                  }`}
                >
                  {item.icone}
                  {item.nome}
                </Link>
              );
            })}
            <MenuDeAcoes pathname={pathname} />
          </div>
        </nav>

        <div className="flex w-[280px] items-center justify-end gap-2">
          {/* O botao Organizar da pagina aberta entra aqui (OrganizarCaixas.tsx). */}
          <span id={LUGAR_DO_ORGANIZAR} className="contents" />
          <span className="rounded-full border border-linha bg-painel">
            <BotaoDoTema />
          </span>
        </div>
      </header>

      <nav className="fixed inset-x-4 bottom-[max(16px,env(safe-area-inset-bottom))] z-30 flex items-center justify-between rounded-full border border-linha bg-painel p-1.5 shadow-[var(--sombra)] md:hidden">
        {ITENS.map((item) => {
          const on = ativo(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={on ? "page" : undefined}
              aria-label={item.nome}
              title={item.nome}
              className={`flex h-12 min-w-10 max-w-12 flex-1 items-center justify-center rounded-full transition-colors ${
                on ? "bg-primario text-primario-tinta" : "text-tinta-3"
              }`}
            >
              {item.icone}
            </Link>
          );
        })}
        <MenuDeAcoes pathname={pathname} celular />
        <BotaoDoTema />
      </nav>
    </>
  );
}
