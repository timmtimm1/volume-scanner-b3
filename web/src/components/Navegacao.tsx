"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** Sidebar no desktop, barra inferior no celular. */

type Item = { href: string; nome: string; icone: React.ReactNode };

const traco = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const ITENS: Item[] = [
  {
    href: "/",
    nome: "Scanner",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" {...traco}>
        <path d="M3 3h6v6H3zM11 3h6v6h-6zM3 11h6v6H3zM11 11h6v6h-6z" />
      </svg>
    ),
  },
  {
    href: "/historico",
    nome: "Histórico",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" {...traco}>
        <path d="M10 5v5l3 2" />
        <circle cx="10" cy="10" r="7" />
      </svg>
    ),
  },
  {
    href: "/alertas",
    nome: "Alertas",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" {...traco}>
        <path d="M10 3a4.5 4.5 0 0 0-4.5 4.5c0 3.5-1.5 4.5-1.5 4.5h12s-1.5-1-1.5-4.5A4.5 4.5 0 0 0 10 3z" />
        <path d="M8.5 15a1.6 1.6 0 0 0 3 0" />
      </svg>
    ),
  },
  {
    href: "/papeis",
    nome: "Papéis",
    icone: (
      <svg width="18" height="18" viewBox="0 0 20 20" {...traco}>
        <circle cx="10" cy="10" r="7" />
        <path d="M3 10h14M10 3c2 2.5 2 11.5 0 14M10 3c-2 2.5-2 11.5 0 14" />
      </svg>
    ),
  },
];

function ativo(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/papel");
  return pathname.startsWith(href);
}

export function Navegacao() {
  const pathname = usePathname();

  return (
    <>
      <aside className="hidden w-[206px] shrink-0 flex-col border-r border-linha bg-painel py-4 md:flex">
        <Link href="/" className="flex items-center gap-2.5 px-3.5 pb-4">
          <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden>
            <rect x="2" y="13" width="3.4" height="8" fill="#2a3543" />
            <rect x="7" y="9" width="3.4" height="12" fill="#2a3543" />
            <rect x="12" y="3" width="3.4" height="18" fill="#ffb020" />
            <rect x="17" y="11" width="3.4" height="10" fill="#2a3543" />
          </svg>
          <span>
            <span className="block text-[13px] font-bold tracking-tight">
              volume-scanner
            </span>
            <span className="block text-[10px] text-tinta-3">
              B3 · volume anômalo
            </span>
          </span>
        </Link>

        <nav className="flex flex-col gap-0.5">
          {ITENS.map((item) => {
            const on = ativo(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={on ? "page" : undefined}
                className={`flex items-center gap-2.5 rounded-r border-l-2 px-3 py-2 text-[13px] transition-colors ${
                  on
                    ? "border-ambar bg-selecao font-semibold text-tinta"
                    : "border-transparent text-tinta-2 hover:bg-painel-2 hover:text-tinta"
                }`}
              >
                {item.icone}
                {item.nome}
              </Link>
            );
          })}
        </nav>
      </aside>

      <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-linha bg-painel pb-[env(safe-area-inset-bottom)] md:hidden">
        {ITENS.map((item) => {
          const on = ativo(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={on ? "page" : undefined}
              className={`toque flex flex-1 flex-col items-center justify-center gap-1 py-2.5 ${
                on ? "text-ambar" : "text-tinta-3"
              }`}
            >
              {item.icone}
              <span
                className={`text-[10px] ${on ? "font-semibold" : ""}`}
              >
                {item.nome}
              </span>
            </Link>
          );
        })}
      </nav>
    </>
  );
}
