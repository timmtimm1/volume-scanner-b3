/** Trades: detalhar um (com operacoes e snapshots) e editar o setup e o stop dele. */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import { OperacaoInvalida, detalharTrade, editarTrade } from "@/lib/trades";

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

/** Corpo: `{ categoriaSetup, stop }`; o que nao vier fica como esta, `null` limpa. */
export async function PATCH(pedido: Request, ctx: RouteContext<"/api/trades/[id]">) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  const id = identificador((await ctx.params).id);
  if (id === null) return NextResponse.json({ erro: "id invalido" }, { status: 400 });

  try {
    const trade = await editarTrade(id, await pedido.json());
    return trade
      ? NextResponse.json({ trade })
      : NextResponse.json({ erro: "nao encontrado" }, { status: 404 });
  } catch (erro) {
    if (erro instanceof OperacaoInvalida) {
      return NextResponse.json({ erro: erro.message }, { status: 400 });
    }
    // JSON malformado tambem cai aqui; a mensagem original nao sai para a internet.
    return NextResponse.json({ erro: "pedido invalido" }, { status: 400 });
  }
}
