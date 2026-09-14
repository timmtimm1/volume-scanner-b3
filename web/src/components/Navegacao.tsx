"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTema } from "@/lib/tema";

/**
 * Barra do topo com as secoes em pilula no computador; pilula flutuante embaixo
 * no celular, onde o polegar alcanca.
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
    href: "/alertas",
    nome: "Alertas",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden {...traco}>
        <path d="M10 3a4.5 4.5 0 0 0-4.5 4.5c0 3.5-1.5 4.5-1.5 4.5h12s-1.5-1-1.5-4.5A4.5 4.5 0 0 0 10 3z" />
        <path d="M8.5 15a1.6 1.6 0 0 0 3 0" />
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
          </div>
        </nav>

        <div className="flex w-[280px] justify-end">
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
              className={`flex h-12 items-center justify-center gap-2 rounded-full transition-colors ${
                on
                  ? "bg-primario px-4 text-[13px] font-bold text-primario-tinta"
                  : "w-12 text-tinta-3"
              }`}
            >
              {item.icone}
              {on && item.nome}
            </Link>
          );
        })}
        <BotaoDoTema />
      </nav>
    </>
  );
}
