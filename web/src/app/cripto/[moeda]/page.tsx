import { notFound, redirect } from "next/navigation";
import { MOEDA } from "@/lib/cripto";

/**
 * O endereco antigo da ficha (`/cripto/BTC`), que continua nos cartoes de setup,
 * no diario e nas mensagens ja enviadas no Telegram. A ficha agora abre ao lado
 * da lista, na aba Cripto.
 */
export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ moeda: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function Moeda({ params, searchParams }: Props) {
  const { moeda } = await params;
  const ticker = decodeURIComponent(moeda).toUpperCase();
  if (!MOEDA.test(ticker)) notFound();
  const foco = (await searchParams).foco;
  const comFoco = typeof foco === "string" && /^\d{4}-\d{2}-\d{2}$/.test(foco) ? `&foco=${foco}` : "";
  redirect(`/cripto/?moeda=${ticker}${comFoco}`);
}
