"use client";

import { useCallback, useSyncExternalStore } from "react";

export type Tema = "claro" | "escuro";

/** Onde a escolha fica guardada. So preferencia de quem olha: vive no navegador. */
export const CHAVE_DO_TEMA = "vs:tema";

/**
 * Roda no <head>, antes da primeira pintura: sem isto, quem escolheu o escuro
 * veria a pagina clara por um instante a cada abertura.
 *
 * Sem escolha guardada, o atributo nao e gravado e vale o tema do sistema --
 * o CSS resolve isso sozinho pelo `prefers-color-scheme`.
 */
export const SCRIPT_DO_TEMA = `try{var t=localStorage.getItem("${CHAVE_DO_TEMA}");if(t==="claro"||t==="escuro")document.documentElement.setAttribute("data-tema",t)}catch(e){}`;

const escuroNoSistema = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;

function temaAtual(): Tema {
  const escolhido = document.documentElement.getAttribute("data-tema");
  if (escolhido === "claro" || escolhido === "escuro") return escolhido;
  return escuroNoSistema() ? "escuro" : "claro";
}

function assinar(aoMudar: () => void): () => void {
  const observador = new MutationObserver(aoMudar);
  observador.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-tema"],
  });
  const midia = window.matchMedia("(prefers-color-scheme: dark)");
  midia.addEventListener("change", aoMudar);
  return () => {
    observador.disconnect();
    midia.removeEventListener("change", aoMudar);
  };
}

/**
 * O tema em vigor e a troca entre os dois.
 *
 * No servidor devolve "claro": as paginas sao geradas no build, sem saber o tema
 * de quem vai abrir. Quem depende do valor exato -- o grafico, que pinta em
 * canvas -- recebe o certo assim que a pagina hidrata.
 */
export function useTema(): { tema: Tema; alternar: () => void } {
  const tema = useSyncExternalStore<Tema>(assinar, temaAtual, () => "claro");

  const alternar = useCallback(() => {
    const proximo: Tema = temaAtual() === "escuro" ? "claro" : "escuro";
    document.documentElement.setAttribute("data-tema", proximo);
    try {
      localStorage.setItem(CHAVE_DO_TEMA, proximo);
    } catch {
      // Navegacao privada ou armazenamento bloqueado: o tema troca nesta
      // visita e so nao fica lembrado.
    }
  }, []);

  return { tema, alternar };
}
