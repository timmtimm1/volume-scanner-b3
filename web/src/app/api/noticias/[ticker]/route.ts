/**
 * Manchetes recentes sobre a empresa do papel, para a aba Noticias da ficha.
 *
 * Publica, como a ficha. A ficha continua estatica e abre do CDN; esta rota so
 * completa a aba depois, no navegador. Nao consulta o banco: os nomes vem da
 * tabela escrita a mao (`nomes-na-imprensa.ts`).
 */

import { NextResponse } from "next/server";
import { noticiasDoPapel } from "@/lib/noticias-do-google";
import { TICKER } from "@/lib/ticker";

export async function GET(_pedido: Request, ctx: RouteContext<"/api/noticias/[ticker]">) {
  const ticker = (await ctx.params).ticker.toUpperCase();
  if (!TICKER.test(ticker)) {
    return NextResponse.json({ erro: "ticker fora do formato da B3" }, { status: 400 });
  }
  return NextResponse.json(await noticiasDoPapel(ticker));
}
