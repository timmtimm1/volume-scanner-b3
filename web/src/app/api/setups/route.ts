/**
 * Setups de um papel, para as setas da ficha.
 *
 * Exige sessao, como alertas e trades: a aba Setups e so de quem esta logado
 * (decisao de 21/10/2026), e a seta no grafico e o mesmo dado.
 */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import { listarSetups } from "@/lib/setups";
import { TICKER } from "@/lib/ticker";

// O estado do setup muda a noite e o alerta durante o pregao: nada de cache.
export const dynamic = "force-dynamic";

export async function GET(pedido: Request) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  const ticker = (new URL(pedido.url).searchParams.get("ticker") ?? "").toUpperCase();
  if (!TICKER.test(ticker)) {
    return NextResponse.json({ erro: "ticker fora do formato da B3" }, { status: 400 });
  }
  return NextResponse.json({ setups: await listarSetups(ticker) });
}
