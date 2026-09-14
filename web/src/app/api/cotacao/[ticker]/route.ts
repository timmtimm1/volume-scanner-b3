/**
 * Cotacao de agora de um papel, para o candle de hoje na ficha.
 *
 * Publica, como a ficha: quem abre pelo link do Telegram ve o candle sem
 * entrar. O que protege a cota da brapi e o cache de 5 minutos por papel e o
 * Yahoo barrando ticker que nao existe (ver `candleDeHoje`).
 *
 * A ficha continua estatica e abre do CDN; esta rota so completa o grafico
 * depois, no navegador.
 */

import { NextResponse } from "next/server";
import { candleDeHoje } from "@/lib/cotacao";
import { TICKER } from "@/lib/ticker";

export async function GET(_pedido: Request, ctx: RouteContext<"/api/cotacao/[ticker]">) {
  const ticker = (await ctx.params).ticker.toUpperCase();
  if (!TICKER.test(ticker)) {
    return NextResponse.json({ erro: "ticker fora do formato da B3" }, { status: 400 });
  }
  return NextResponse.json({ candle: await candleDeHoje(ticker) });
}
