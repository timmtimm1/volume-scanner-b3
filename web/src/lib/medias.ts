/**
 * As medias moveis que o grafico desenha: quais, de que tipo e em que cor.
 *
 * Preferencia de quem olha, entao vive no navegador (localStorage). A lista e
 * a mesma para todos os papeis: quem acompanha MME 9 quer ver a MME 9 em
 * qualquer ficha que abrir.
 *
 * Modulo sem React nem DOM no que e regra (padrao, validacao, rotulo), para
 * os testes rodarem no Node; o acesso ao armazenamento fica isolado embaixo.
 */

import type { TipoDeMedia } from "./indicadores";

export type Media = {
  id: string;
  tipo: TipoDeMedia;
  periodo: number;
  cor: string;
};

/**
 * Cores para escolher. Nenhuma verde nem vermelha (direcao de preco) nem o
 * dourado do evento: uma media nessas cores confundiria a leitura do candle.
 */
export const CORES_DAS_MEDIAS = [
  "#EAB308", // amarelo
  "#EC4899", // rosa
  "#0EA5E9", // azul-claro
  "#A855F7", // violeta
  "#F97316", // laranja
  "#64748B", // ardosia
] as const;

export const MEDIAS_PADRAO: readonly Media[] = [
  { id: "MMA-20", tipo: "MMA", periodo: 20, cor: "#EAB308" },
  { id: "MME-9", tipo: "MME", periodo: 9, cor: "#EC4899" },
];

export const PERIODO_MINIMO = 2;
export const PERIODO_MAXIMO = 200;

export function idDaMedia(tipo: TipoDeMedia, periodo: number): string {
  return `${tipo}-${periodo}`;
}

export function rotuloDaMedia(media: Pick<Media, "tipo" | "periodo">): string {
  return `${media.tipo} ${media.periodo}`;
}

function valida(item: unknown): item is Media {
  if (typeof item !== "object" || item === null) return false;
  const m = item as Record<string, unknown>;
  return (
    (m.tipo === "MMA" || m.tipo === "MME") &&
    Number.isInteger(m.periodo) &&
    (m.periodo as number) >= PERIODO_MINIMO &&
    (m.periodo as number) <= PERIODO_MAXIMO &&
    typeof m.cor === "string" &&
    /^#[0-9a-fA-F]{6}$/.test(m.cor)
  );
}

/**
 * Lista guardada para lista usavel. Texto corrompido, formato antigo ou item
 * invalido nao quebram o grafico: o que nao se aproveita volta ao padrao.
 * Uma lista vazia guardada de proposito continua vazia.
 */
export function lerMedias(texto: string | null): Media[] {
  if (texto === null) return [...MEDIAS_PADRAO];
  try {
    const bruto: unknown = JSON.parse(texto);
    if (!Array.isArray(bruto)) return [...MEDIAS_PADRAO];
    const vistas = new Set<string>();
    const medias: Media[] = [];
    for (const item of bruto) {
      if (!valida(item)) continue;
      const id = idDaMedia(item.tipo, item.periodo);
      if (vistas.has(id)) continue;
      vistas.add(id);
      medias.push({ id, tipo: item.tipo, periodo: item.periodo, cor: item.cor });
    }
    return medias;
  } catch {
    return [...MEDIAS_PADRAO];
  }
}

/** Acrescenta uma media. A mesma media (tipo e periodo) nao entra duas vezes. */
export function comMedia(medias: Media[], nova: Omit<Media, "id">): Media[] {
  const id = idDaMedia(nova.tipo, nova.periodo);
  if (medias.some((m) => m.id === id)) return medias;
  return [...medias, { ...nova, id }];
}

export function semMedia(medias: Media[], id: string): Media[] {
  return medias.filter((m) => m.id !== id);
}

/** A primeira cor da paleta que ainda nao esta em uso, para a proxima media. */
export function proximaCor(medias: Media[]): string {
  const usadas = new Set(medias.map((m) => m.cor.toUpperCase()));
  return CORES_DAS_MEDIAS.find((c) => !usadas.has(c)) ?? CORES_DAS_MEDIAS[0];
}
