/**
 * Trades: listar.
 *
 * Tudo aqui exige sessao, inclusive a LEITURA -- mesma razao dos alertas: um
 * trade real e posicao e resultado do usuario, e o site e publico. Quem nao
 * esta logado nao ve nem que a funcionalidade existe.
 *
 * `?mercado=cripto` le o diario de cripto (schema `cripto_scanner`); sem ele, a B3.
 */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import { mercadoDe } from "@/lib/mercado";
import { noMercado } from "@/lib/mercado-servidor";
import { listarTrades } from "@/lib/trades";

// Trade muda por acao do usuario e pela marcacao a mercado noturna, nunca por
// rebuild do site: nada aqui pode ser pre-renderizado nem servido de cache.
export const dynamic = "force-dynamic";

export async function GET(pedido: Request) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  const busca = new URL(pedido.url).searchParams;
  const ticker = busca.get("ticker") ?? undefined;
  const trades = await noMercado(mercadoDe(busca.get("mercado")), () => listarTrades(ticker));
  return NextResponse.json({ trades });
}
