"use client";

import { useSyncExternalStore } from "react";

/**
 * A mesma largura do `lg:` do Tailwind, onde a ficha vira tres colunas e o
 * scanner ganha a previa. Abaixo disso a tela e tratada como celular.
 */
const CONSULTA = "(min-width: 1024px)";

function assinar(aoMudar: () => void): () => void {
  const midia = window.matchMedia(CONSULTA);
  midia.addEventListener("change", aoMudar);
  return () => midia.removeEventListener("change", aoMudar);
}

const instantaneo = () => window.matchMedia(CONSULTA).matches;

/**
 * Se a tela e de computador.
 *
 * No servidor (e na hidratacao) e `false`: o HTML estatico sai na versao do
 * celular, e o computador troca logo depois, sem erro de hidratacao. E por isso
 * que o que so existe no computador -- a previa do historico, arrastar alerta
 * no grafico -- nao aparece no HTML.
 */
export function useComputador(): boolean {
  return useSyncExternalStore(assinar, instantaneo, () => false);
}
