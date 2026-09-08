import type { MetadataRoute } from "next";

/**
 * PWA: instalavel na tela inicial do celular, abrindo como app (F7 do plano).
 *
 * Sem service worker de proposito. O site e reconstruido uma vez por pregao e o
 * valor dele e mostrar o dado do dia; um cache offline serviria pregao velho
 * sem avisar, que e pior do que nao abrir. O plano pede manifest e icones, e e
 * isso que basta para instalar.
 */
// O export estatico precisa disto para materializar a rota como arquivo.
export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "volume-scanner-b3",
    short_name: "vol-scanner",
    description:
      "Detector de volume financeiro anômalo na B3. Detecta e apresenta; a leitura é sua.",
    start_url: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0a0e14",
    theme_color: "#0a0e14",
    lang: "pt-BR",
    categories: ["finance"],
    icons: [
      {
        src: "/icone-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icone-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icone-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
