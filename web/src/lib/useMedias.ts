"use client";

import { useCallback, useSyncExternalStore } from "react";
import { lerMedias, type Media } from "./medias";

const CHAVE = "vs:medias";
const EVENTO = "vs:medias-mudaram";

let textoEmCache: string | null | undefined;
let listaEmCache: Media[] = [];

function lerDoNavegador(): string | null {
  try {
    return localStorage.getItem(CHAVE);
  } catch {
    return null;
  }
}

/** A mesma referencia enquanto o texto guardado nao muda, como o React exige. */
function instantaneo(): Media[] {
  const texto = lerDoNavegador();
  if (texto !== textoEmCache) {
    textoEmCache = texto;
    listaEmCache = lerMedias(texto);
  }
  return listaEmCache;
}

const noServidor = lerMedias(null);

function assinar(aoMudar: () => void): () => void {
  window.addEventListener("storage", aoMudar);
  window.addEventListener(EVENTO, aoMudar);
  return () => {
    window.removeEventListener("storage", aoMudar);
    window.removeEventListener(EVENTO, aoMudar);
  };
}

/**
 * As medias do grafico e a forma de troca-las.
 *
 * Mudar numa ficha muda em todas as abertas, inclusive em outra aba (o evento
 * `storage` do navegador).
 */
export function useMedias(): [Media[], (proximas: Media[]) => void] {
  const medias = useSyncExternalStore(assinar, instantaneo, () => noServidor);

  const salvar = useCallback((proximas: Media[]) => {
    try {
      localStorage.setItem(CHAVE, JSON.stringify(proximas));
    } catch {
      // Armazenamento bloqueado: a troca nao persiste. Sem onde guardar, nao ha
      // como a tela refletir a mudanca por este caminho.
    }
    window.dispatchEvent(new Event(EVENTO));
  }, []);

  return [medias, salvar];
}
