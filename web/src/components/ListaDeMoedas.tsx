"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import {
  contarFiltros,
  FILTROS_DA_LISTA,
  type FiltroDaLista,
  filtrarMoedas,
  type LinhaDaMoeda,
  MOEDA_PADRAO,
} from "@/lib/cripto-lista";
import { numero, percentual } from "@/lib/formato";
import { casasDoPreco } from "@/lib/mercado";
import { classificar } from "@/lib/tendencia";
import { useFiltroDeTendencia } from "./SeletorDeTendencia";

/**
 * A coluna da aba Cripto: busca, quatro filtros e uma linha por moeda. Clicar
 * troca o grafico ao lado, pela URL (`/cripto?moeda=ETH`), entao o link da moeda
 * pode ser guardado e o botao de voltar do navegador funciona.
 */
export function ListaDeMoedas({ linhas }: { linhas: LinhaDaMoeda[] }) {
  const router = useRouter();
  const aberta = (useSearchParams().get("moeda") ?? MOEDA_PADRAO).toUpperCase();
  const [busca, setBusca] = useState("");
  const [filtro, setFiltro] = useState<FiltroDaLista>("todas");
  // "Em alta" usa as medias escolhidas na pagina de Setups (padrao MME 20 + 80).
  const { escolha } = useFiltroDeTendencia("cripto");

  const emAlta = useMemo(
    () => (l: LinhaDaMoeda) =>
      l.inclinacoes !== null && classificar(l.inclinacoes, escolha) === "alta",
    [escolha],
  );
  const visiveis = useMemo(
    () => filtrarMoedas(linhas, busca, filtro, emAlta),
    [linhas, busca, filtro, emAlta],
  );
  const contagem = useMemo(() => contarFiltros(linhas, emAlta), [linhas, emAlta]);

  return (
    <section className="cartao flex flex-col gap-3 p-3 lg:max-h-[calc(100vh-2rem)]">
      <input
        type="search"
        value={busca}
        onChange={(e) => setBusca(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && visiveis[0]) router.push(`/cripto/?moeda=${visiveis[0].ticker}`);
        }}
        placeholder="Buscar moeda (BTC, Solana...)"
        aria-label="Buscar moeda pelo código ou pelo nome"
        className="h-11 w-full shrink-0 rounded-full border border-linha-2 bg-painel-2 px-4 text-[14px] font-semibold outline-none placeholder:text-tinta-3 focus:border-acento"
      />

      <div role="group" aria-label="Filtrar moedas" className="grid shrink-0 grid-cols-2 gap-1 sm:grid-cols-4 lg:grid-cols-2">
        {FILTROS_DA_LISTA.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFiltro(f.id)}
            aria-pressed={filtro === f.id}
            className={`toque flex h-9 items-center justify-center gap-1.5 rounded-full text-[12px] font-bold transition-colors ${
              filtro === f.id
                ? "bg-primario text-primario-tinta"
                : "bg-painel-2 text-tinta-2 hover:text-tinta"
            }`}
          >
            {f.nome}
            <span className="num opacity-70">{contagem[f.id]}</span>
          </button>
        ))}
      </div>

      {visiveis.length === 0 ? (
        <p className="px-2 py-6 text-center text-[13px] font-semibold text-tinta-3">
          {busca.trim() ? `Nenhuma moeda com "${busca.trim()}" neste filtro.` : "Nenhuma moeda neste filtro."}
        </p>
      ) : (
        <ul className="flex min-h-0 flex-col overflow-y-auto">
          {visiveis.map((m) => (
            <li key={m.ticker}>
              <Link
                href={`/cripto/?moeda=${m.ticker}`}
                prefetch={false}
                aria-current={m.ticker === aberta ? "true" : undefined}
                className={`flex min-h-12 items-center gap-2 rounded-xl px-2.5 py-1.5 transition-colors ${
                  m.ticker === aberta ? "bg-painel-2" : "hover:bg-painel-2"
                }`}
              >
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="flex items-center gap-1.5">
                    <span className="text-[14px] font-extrabold">{m.ticker}</span>
                    {m.comTrade && (
                      <span className="rounded-md bg-primario px-1.5 py-0.5 text-[10px] font-extrabold text-primario-tinta">
                        em trade
                      </span>
                    )}
                    {m.setups > 0 && (
                      <span className="whitespace-nowrap rounded-md border border-linha-2 px-1.5 py-0.5 text-[10px] font-bold text-tinta-3">
                        {m.setups} {m.setups === 1 ? "setup" : "setups"}
                      </span>
                    )}
                  </span>
                  <span className="truncate text-[11px] font-semibold text-tinta-3">{m.nome}</span>
                </span>
                <span className="flex shrink-0 flex-col items-end">
                  <span className="num text-[13px] font-bold">
                    {m.preco === null ? "—" : numero(m.preco, casasDoPreco(m.preco))}
                  </span>
                  <span
                    className={`num text-[11px] font-bold ${
                      m.variacao === null ? "text-tinta-3" : m.variacao >= 0 ? "text-alta" : "text-baixa"
                    }`}
                  >
                    {percentual(m.variacao)}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
