"use client";

import { useMemo, useSyncExternalStore } from "react";
import type { Mercado } from "@/lib/mercado";
import {
  FILTROS,
  PERIODOS,
  alternar,
  escolhaDoTexto,
  type EscolhaDeMedias,
  type Estado,
  type FiltroDeTendencia,
} from "@/lib/tendencia";

const NOME: Record<FiltroDeTendencia, string> = {
  todas: "Todas",
  alta: "Alta",
  lateral: "Lateral",
  baixa: "Baixa",
};

// A escolha guardada por mercado. A memoria vale quando o navegador nao deixa
// gravar (aba anonima, previa): a escolha so nao sobrevive ao recarregar.
const memoria = new Map<string, string>();
const assinantes = new Set<() => void>();

function assinar(avisar: () => void): () => void {
  assinantes.add(avisar);
  return () => {
    assinantes.delete(avisar);
  };
}

function lerGuardado(chave: string): string | null {
  if (memoria.has(chave)) return memoria.get(chave) ?? null;
  try {
    return window.localStorage.getItem(chave);
  } catch {
    return null;
  }
}

function gravar(chave: string, texto: string): void {
  memoria.set(chave, texto);
  try {
    window.localStorage.setItem(chave, texto);
  } catch {
    // fica so na memoria
  }
  for (const avisar of assinantes) avisar();
}

/**
 * O filtro de tendencia escolhido, guardado no navegador por mercado. No
 * servidor e na hidratacao vale o padrao (Todas, MME 20 + 80): o HTML estatico
 * sai sem filtro e a escolha guardada entra logo depois, sem erro de hidratacao.
 */
export function useFiltroDeTendencia(mercado: Mercado) {
  const chave = `tendencia:${mercado}`;
  const texto = useSyncExternalStore(assinar, () => lerGuardado(chave), () => null);
  const { escolha, filtro } = useMemo(() => escolhaDoTexto(texto), [texto]);
  const mudar = (e: EscolhaDeMedias, f: FiltroDeTendencia) =>
    gravar(chave, JSON.stringify({ ...e, filtro: f }));
  return { escolha, filtro, mudar };
}

/** "Alta" / "Lateral" / "Baixa" ao lado do ticker; nada sem historico. */
export function EtiquetaDeTendencia({ estado }: { estado: Estado | null }) {
  if (estado === null) return null;
  const cor =
    estado === "alta"
      ? "bg-alta-fundo text-alta"
      : estado === "baixa"
        ? "bg-baixa-fundo text-baixa"
        : "bg-painel-2 text-tinta-3";
  return (
    <span className={`whitespace-nowrap rounded-md px-1.5 py-0.5 text-[10px] font-extrabold ${cor}`}>
      {NOME[estado]}
    </span>
  );
}

/**
 * Todas / Alta / Lateral / Baixa, com a contagem, e as medias que entram na
 * conta (9, 20, 50, 80, 200; MME ou MMA). Alta = todas as medias marcadas
 * subindo, baixa = todas caindo, lateral = discordam.
 */
export function SeletorDeTendencia({
  escolha,
  filtro,
  contagem,
  mudar,
}: {
  escolha: EscolhaDeMedias;
  filtro: FiltroDeTendencia;
  contagem: Record<FiltroDeTendencia, number>;
  mudar: (e: EscolhaDeMedias, f: FiltroDeTendencia) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div role="group" aria-label="Tendência" className="grid grid-cols-4 rounded-full border border-linha-2 p-0.5">
        {FILTROS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => mudar(escolha, f)}
            aria-pressed={filtro === f}
            className={`toque h-9 rounded-full text-[12px] font-bold transition-colors md:text-[13px] ${
              filtro === f ? "bg-painel text-acento shadow-sm" : "text-tinta-3 hover:text-tinta"
            }`}
          >
            {NOME[f]} <span className="num font-semibold">{contagem[f]}</span>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rotulo mr-1">Médias</span>
        {PERIODOS.map((p) => {
          const ligada = escolha.periodos.includes(p);
          return (
            <button
              key={p}
              type="button"
              onClick={() => mudar(alternar(escolha, p), filtro)}
              aria-pressed={ligada}
              className={`num toque h-8 min-w-10 rounded-full border px-2.5 text-[12px] font-bold transition-colors ${
                ligada
                  ? "border-acento bg-selecao text-acento"
                  : "border-linha-2 text-tinta-3 hover:text-tinta"
              }`}
            >
              {p}
            </button>
          );
        })}
        <div role="group" aria-label="Tipo de média" className="ml-auto flex rounded-xl border border-linha-2 p-0.5">
          {(["MME", "MMA"] as const).map((tipo) => (
            <button
              key={tipo}
              type="button"
              onClick={() => mudar({ ...escolha, tipo }, filtro)}
              aria-pressed={escolha.tipo === tipo}
              title={tipo === "MME" ? "média exponencial" : "média simples"}
              className={`toque h-7 rounded-[10px] px-2.5 text-[11px] font-bold transition-colors ${
                escolha.tipo === tipo ? "bg-painel text-acento shadow-sm" : "text-tinta-3"
              }`}
            >
              {tipo}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
