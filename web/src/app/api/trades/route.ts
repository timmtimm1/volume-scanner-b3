/**
 * Trades: listar.
 *
 * Tudo aqui exige sessao, inclusive a LEITURA -- mesma razao dos alertas: um
 * trade real e posicao e resultado do usuario, e o site e publico. Quem nao
 * esta logado nao ve nem que a funcionalidade existe.
 */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import { listarTrades } from "@/lib/trades";

// Trade muda por acao do usuario e pela marcacao a mercado noturna, nunca por
// rebuild do site: nada aqui pode ser pre-renderizado nem servido de cache.
export const dynamic = "force-dynamic";

export async function GET(pedido: Request) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  const ticker = new URL(pedido.url).searchParams.get("ticker") ?? undefined;
  return NextResponse.json({ trades: await listarTrades(ticker) });
}
