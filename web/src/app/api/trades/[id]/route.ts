/** Trades: detalhar um, com operacoes e snapshots. */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import { detalharTrade } from "@/lib/trades";

export const dynamic = "force-dynamic";

/** Id da rota para numero, ou null se nao for um. */
function identificador(bruto: string): number | null {
  const n = Number(bruto);
  return Number.isInteger(n) && n > 0 ? n : null;
}

export async function GET(_pedido: Request, ctx: RouteContext<"/api/trades/[id]">) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  const id = identificador((await ctx.params).id);
  if (id === null) return NextResponse.json({ erro: "id invalido" }, { status: 400 });

  const trade = await detalharTrade(id);
  return trade
    ? NextResponse.json({ trade })
    : NextResponse.json({ erro: "nao encontrado" }, { status: 404 });
}
