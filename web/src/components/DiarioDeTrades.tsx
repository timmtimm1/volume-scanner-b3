"use client";

import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import type { Perfil } from "@/lib/lote";
import { linkDoTrade, type Mercado } from "@/lib/mercado";
import type { TradeResumo } from "@/lib/trades";
import { FormularioDeCompra } from "./FormularioDeCompra";
import { ListaDeTrades } from "./ListaDeTrades";
import { ResultadoPorSetup } from "./ResultadoPorSetup";

export type Filtro = "tudo" | Mercado;

const OPCOES: { valor: Filtro; rotulo: string }[] = [
  { valor: "tudo", rotulo: "Tudo" },
  { valor: "b3", rotulo: "Ações" },
  { valor: "cripto", rotulo: "Cripto" },
];

const VAZIO: Record<Filtro, string> = {
  tudo: "Nenhum trade ainda. Registre a compra na ficha do papel, no botão Entrei de um setup ou em Registrar compra.",
  b3: "Nenhum trade de ações ainda. Registre a compra na ficha do papel ou no botão Entrei de um setup.",
  cripto: "Nenhum trade de cripto ainda. Registre pelo botão Entrei na aba Cripto ou em Registrar compra.",
};

/** O filtro na URL (`?mercado=`), para o link do Telegram e o recarregar abrirem no mesmo. */
function guardarNaUrl(filtro: Filtro) {
  try {
    const url = new URL(window.location.href);
    if (filtro === "tudo") url.searchParams.delete("mercado");
    else url.searchParams.set("mercado", filtro);
    window.history.replaceState(null, "", url);
  } catch {
    // sem historico (previa, iframe): o filtro so nao sobrevive ao recarregar
  }
}

/**
 * O diario dos dois mercados numa tela so (decisao de 17/11/2026): o filtro
 * escolhe Tudo, Ações ou Cripto, e vale para o resultado por setup e para a
 * lista. Reais e dolares nunca se somam; o R, que nao tem moeda, sim.
 */
export function DiarioDeTrades({
  trades,
  filtroInicial,
  perfis,
  perfilDaB3,
}: {
  trades: TradeResumo[];
  filtroInicial: Filtro;
  /** Capital e risco de cada mercado, para o lote da compra a mao. */
  perfis: Record<Mercado, Perfil | null>;
  /** O cartao do capital das acoes, que some com o filtro em Cripto. */
  perfilDaB3: ReactNode;
}) {
  const router = useRouter();
  const [filtro, setFiltro] = useState<Filtro>(filtroInicial);
  const [comprando, setComprando] = useState(false);
  const [mercadoDaCompra, setMercadoDaCompra] = useState<Mercado>(
    filtroInicial === "cripto" ? "cripto" : "b3",
  );

  function escolher(f: Filtro) {
    setFiltro(f);
    if (f !== "tudo") setMercadoDaCompra(f);
    guardarNaUrl(f);
  }

  const visiveis = filtro === "tudo" ? trades : trades.filter((t) => t.mercado === filtro);

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <div role="group" aria-label="Mercado" className="flex rounded-full border border-linha-2 p-0.5">
          {OPCOES.map((o) => (
            <button
              key={o.valor}
              type="button"
              onClick={() => escolher(o.valor)}
              aria-pressed={filtro === o.valor}
              className={`toque h-9 rounded-full px-4 text-[13px] font-bold transition-colors ${
                filtro === o.valor ? "bg-painel text-acento shadow-sm" : "text-tinta-3 hover:text-tinta"
              }`}
            >
              {o.rotulo}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => setComprando((v) => !v)}
          aria-expanded={comprando}
          className="toque h-10 rounded-full bg-primario px-4 text-[13px] font-bold text-primario-tinta"
        >
          Registrar compra
        </button>
      </div>

      {comprando && (
        <section className="cartao flex flex-col gap-3 p-4 md:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-[16px] font-extrabold">Registrar compra</h2>
            <div role="group" aria-label="Mercado da compra" className="flex rounded-xl border border-linha-2 p-0.5">
              {(["b3", "cripto"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMercadoDaCompra(m)}
                  aria-pressed={mercadoDaCompra === m}
                  className={`toque h-8 rounded-[10px] px-3 text-[12px] font-bold transition-colors ${
                    mercadoDaCompra === m ? "bg-painel text-acento shadow-sm" : "text-tinta-3"
                  }`}
                >
                  {m === "b3" ? "Ações" : "Cripto"}
                </button>
              ))}
            </div>
          </div>
          <p className="text-[12px] font-semibold text-tinta-3">
            Para um trade que não veio do botão Entrei. A compra abre o trade; as próximas compras e
            vendas entram na página dele.
          </p>
          <FormularioDeCompra
            key={mercadoDaCompra}
            mercado={mercadoDaCompra}
            ticker={null}
            perfil={perfis[mercadoDaCompra]}
            stopObrigatorio={false}
            escolherSetup
            aoSalvar={(t) => router.push(linkDoTrade(t.mercado, t.id))}
            aoCancelar={() => setComprando(false)}
          />
        </section>
      )}

      {filtro !== "cripto" && perfilDaB3}

      <ResultadoPorSetup trades={visiveis} mercado={filtro === "tudo" ? null : filtro} />

      <ListaDeTrades trades={visiveis} misturado={filtro === "tudo"} vazio={VAZIO[filtro]} />
    </>
  );
}
