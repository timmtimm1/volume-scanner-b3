/**
 * Barras de um papel, para a previa do historico no computador.
 *
 * Estatica como a ficha: um JSON por papel com evento, gerado no build e
 * servido do CDN. Clicar de evento em evento no historico nao toca no banco.
 * Papel fora da lista do build (o que cruzou o limiar depois do ultimo deploy)
 * e gerado no primeiro pedido, como a ficha dele.
 *
 * Leva so o que o grafico desenha: as barras e as datas dos eventos do papel
 * (o candle desses dias sai dourado). O resto do evento ja esta na linha do
 * historico.
 */

import { NextResponse } from "next/server";
import { papeisComEvento, papel } from "@/lib/db";
import { TICKER } from "@/lib/ticker";

// O GET de rota e dinamico por padrao desde o Next 15. Aqui nada depende de
// quem pede -- nem cookie, nem cabecalho --, entao a resposta e a do build.
export const dynamic = "force-static";

export async function generateStaticParams() {
  const tickers = await papeisComEvento();
  return tickers.map((ticker) => ({ ticker }));
}

export async function GET(_pedido: Request, ctx: RouteContext<"/api/barras/[ticker]">) {
  const ticker = (await ctx.params).ticker.toUpperCase();
  if (!TICKER.test(ticker)) {
    return NextResponse.json({ erro: "ticker fora do formato da B3" }, { status: 400 });
  }
  const dados = await papel(ticker);
  if (dados.barras.length === 0) {
    return NextResponse.json({ erro: "papel sem barras" }, { status: 404 });
  }
  return NextResponse.json({
    barras: dados.barras,
    eventos: dados.eventos.map((e) => ({ tradeDate: e.tradeDate })),
  });
}
