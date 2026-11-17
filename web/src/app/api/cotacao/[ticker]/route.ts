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
import type { CandleDeHoje } from "@/lib/candle-de-hoje";
import { candleDeHoje } from "@/lib/cotacao";
import { diaDeHoje } from "@/lib/cripto-hoje-binance";
import { mercadoDe, tickerValido } from "@/lib/mercado";
import { TICKER } from "@/lib/ticker";

/**
 * Com `?mercado=cripto`: o dia UTC em andamento da moeda na Binance, no mesmo
 * formato de candle, para o preco de agora de um trade de cripto aberto. A
 * Binance nao tem cota a proteger; quem chama ja limita a uma busca por moeda.
 */
async function candleDaMoeda(moeda: string): Promise<CandleDeHoje | null> {
  const dia = (await diaDeHoje([moeda]))[moeda];
  if (!dia) return null;
  return {
    ticker: moeda,
    dia: dia.dia,
    open: dia.abertura,
    high: dia.maxima,
    low: dia.minima,
    close: dia.ultimo,
    volumeAcoes: null,
    hora: dia.hora,
    fonte: "binance",
  };
}

export async function GET(pedido: Request, ctx: RouteContext<"/api/cotacao/[ticker]">) {
  const ticker = (await ctx.params).ticker.toUpperCase();
  if (mercadoDe(new URL(pedido.url).searchParams.get("mercado")) === "cripto") {
    if (!tickerValido("cripto", ticker)) {
      return NextResponse.json({ erro: "moeda fora do formato" }, { status: 400 });
    }
    return NextResponse.json({ candle: await candleDaMoeda(ticker) });
  }
  if (!TICKER.test(ticker)) {
    return NextResponse.json({ erro: "ticker fora do formato da B3" }, { status: 400 });
  }
  return NextResponse.json({ candle: await candleDeHoje(ticker) });
}
