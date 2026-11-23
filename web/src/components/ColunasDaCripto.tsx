"use client";

import { useSearchParams } from "next/navigation";

/**
 * Lista e grafico lado a lado no computador. No celular nao cabem os dois: sem
 * moeda na URL aparece a lista; com moeda, o grafico em tela cheia, e o "‹ Moedas"
 * da ficha volta para a lista.
 */
export function ColunasDaCripto({
  cabecalho,
  lista,
  children,
}: {
  cabecalho: React.ReactNode;
  lista: React.ReactNode;
  children: React.ReactNode;
}) {
  const aberta = useSearchParams().has("moeda");
  return (
    <div className="flex flex-col gap-4">
      <div className={aberta ? "hidden lg:block" : ""}>{cabecalho}</div>
      <div className="grid items-start gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside className={`lg:sticky lg:top-4 ${aberta ? "hidden lg:block" : ""}`}>{lista}</aside>
        <div className={`min-w-0 ${aberta ? "" : "hidden lg:block"}`}>{children}</div>
      </div>
    </div>
  );
}
