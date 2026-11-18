"use client";

import { useCallback, useSyncExternalStore } from "react";
import { lerMarcas, type MarcasDoGrafico, TUDO_LIGADO } from "./marcas-do-grafico";

const EVENTO = "vs:marcas-mudaram";

function lerDoNavegador(chave: string): string | null {
  try {
    return localStorage.getItem(chave);
  } catch {
    return null;
  }
}

// Um cache por chave: o React exige a mesma referencia enquanto o texto
// guardado nao muda.
const cache = new Map<string, { texto: string | null; marcas: MarcasDoGrafico }>();

function instantaneo(chave: string): MarcasDoGrafico {
  const texto = lerDoNavegador(chave);
  const guardado = cache.get(chave);
  if (guardado && guardado.texto === texto) return guardado.marcas;
  const marcas = lerMarcas(texto);
  cache.set(chave, { texto, marcas });
  return marcas;
}

function assinar(aoMudar: () => void): () => void {
  window.addEventListener("storage", aoMudar);
  window.addEventListener(EVENTO, aoMudar);
  return () => {
    window.removeEventListener("storage", aoMudar);
    window.removeEventListener(EVENTO, aoMudar);
  };
}

/**
 * O que o grafico mostra e a forma de ligar ou desligar uma das marcas,
 * guardado no navegador em `chave`. Sem chave (o grafico das acoes), tudo fica
 * ligado e nada e guardado.
 */
export function useMarcasDoGrafico(
  chave: string | undefined,
): [MarcasDoGrafico, (marca: keyof MarcasDoGrafico) => void] {
  const marcas = useSyncExternalStore(
    assinar,
    () => (chave ? instantaneo(chave) : TUDO_LIGADO),
    () => TUDO_LIGADO,
  );

  const alternar = useCallback(
    (marca: keyof MarcasDoGrafico) => {
      if (!chave) return;
      // Le o guardado agora, e nao o da ultima renderizacao: dois cliques
      // antes de a tela redesenhar nao podem desfazer um ao outro.
      const atual = instantaneo(chave);
      try {
        localStorage.setItem(chave, JSON.stringify({ ...atual, [marca]: !atual[marca] }));
      } catch {
        // Armazenamento bloqueado: a escolha nao persiste, e o grafico segue
        // mostrando tudo -- melhor que esconder sem como desfazer.
      }
      window.dispatchEvent(new Event(EVENTO));
    },
    [chave],
  );

  return [marcas, alternar];
}
