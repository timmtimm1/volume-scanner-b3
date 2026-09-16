/**
 * Operacoes de trade: registrar uma compra ou venda.
 *
 * Compra sem trade aberto do papel abre um trade novo; venda sem trade
 * aberto e erro (`registrarOperacao` cuida disso). A validacao da posicao
 * inteira -- nao so dos campos da operacao -- mora em `trades.ts`.
 */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import { OperacaoInvalida, registrarOperacao } from "@/lib/trades";

export const dynamic = "force-dynamic";

export async function POST(pedido: Request) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  try {
    const corpo = await pedido.json();
    return NextResponse.json({ trade: await registrarOperacao(corpo) }, { status: 201 });
  } catch (erro) {
    if (erro instanceof OperacaoInvalida) {
      return NextResponse.json({ erro: erro.message }, { status: 400 });
    }
    // JSON malformado tambem cai aqui. Nao vaza a mensagem original: ela pode
    // conter detalhe do banco, e isto responde para a internet.
    return NextResponse.json({ erro: "pedido invalido" }, { status: 400 });
  }
}
