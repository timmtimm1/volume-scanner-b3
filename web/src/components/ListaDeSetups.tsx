"use client";

import { useMemo } from "react";
import type { Nivel } from "@/lib/backtest-tela";
import {
  agruparPorCategoria,
  type CategoriaDoSetup,
  type Conferencia,
  type Preferencias,
  type Setup,
} from "@/lib/setups-tela";
import { BlocoFechado, BlocoLigado } from "./BlocoDeSetup";

type Props = {
  setups: Setup[];
  preferencias: Preferencias;
  /** Nivel do backtest (rodada mais recente) por setup; sem rodada, vazio. */
  niveis: Partial<Record<CategoriaDoSetup, Nivel>>;
  /** O ao vivo de cada setup contra o backtest. */
  conferencias: Partial<Record<CategoriaDoSetup, Conferencia>>;
  hoje: string;
};

/**
 * A aba Setups: no topo os setups com alerta ligado, embaixo os outros, cada
 * um num bloco fechado. A ordem e fixa (a do Backtest), nunca por resultado.
 */
export function ListaDeSetups({ setups, preferencias, niveis, conferencias, hoje }: Props) {
  const { ligados, outros } = useMemo(
    () => agruparPorCategoria(setups, preferencias),
    [setups, preferencias],
  );
  const ultimoPregao = setups.find((s) => s.ultimoPregao)?.ultimoPregao ?? null;

  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-col gap-3">
        <h2 className="px-1 text-[16px] font-extrabold">Com alerta ligado</h2>
        {ligados.length === 0 ? (
          <p className="cartao p-5 text-[13px] font-semibold text-tinta-3">
            Nenhum setup com alerta ligado. Abra um dos outros abaixo e ligue o alerta.
          </p>
        ) : (
          ligados.map((b) => (
            <BlocoLigado
              key={b.categoria}
              bloco={b}
              nivel={niveis[b.categoria]}
              conferencia={conferencias[b.categoria]}
              hoje={hoje}
              ultimoPregao={ultimoPregao}
            />
          ))
        )}
      </section>

      {outros.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="px-1 text-[16px] font-extrabold">Outros setups</h2>
          {outros.map((b) => (
            <BlocoFechado
              key={b.categoria}
              bloco={b}
              nivel={niveis[b.categoria]}
              conferencia={conferencias[b.categoria]}
              hoje={hoje}
              ultimoPregao={ultimoPregao}
            />
          ))}
        </section>
      )}
    </div>
  );
}
