/**
 * Alertas: listar e criar.
 *
 * Tudo aqui exige sessao, inclusive a LEITURA. Alerta e intencao de operacao --
 * "estou de olho na PETR4 em 38,50" -- e o site e publico. Quem nao esta
 * logado ve o scanner exatamente como antes, sem sinal de que alertas existem.
 */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import { criarAlerta, DadoInvalido, listarAlertas } from "@/lib/alertas";

// Alerta muda por acao do usuario, nunca por rebuild: nada aqui pode ser
// pre-renderizado nem servido de cache.
export const dynamic = "force-dynamic";

export async function GET(pedido: Request) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  const ticker = new URL(pedido.url).searchParams.get("ticker") ?? undefined;
  return NextResponse.json({ alertas: await listarAlertas(ticker) });
}

export async function POST(pedido: Request) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  try {
    const corpo = await pedido.json();
    return NextResponse.json({ alerta: await criarAlerta(corpo) }, { status: 201 });
  } catch (erro) {
    if (erro instanceof DadoInvalido) {
      return NextResponse.json({ erro: erro.message }, { status: 400 });
    }
    // JSON malformado tambem cai aqui. Nao vaza a mensagem original: ela pode
    // conter detalhe do banco, e isto responde para a internet.
    return NextResponse.json({ erro: "pedido invalido" }, { status: 400 });
  }
}
