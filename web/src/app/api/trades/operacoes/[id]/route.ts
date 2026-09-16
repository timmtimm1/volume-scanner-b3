/** Operacoes de trade: editar e apagar. */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import { OperacaoInvalida, apagarOperacao, editarOperacao } from "@/lib/trades";

export const dynamic = "force-dynamic";

/** Id da rota para numero, ou null se nao for um. */
function identificador(bruto: string): number | null {
  const n = Number(bruto);
  return Number.isInteger(n) && n > 0 ? n : null;
}

export async function PATCH(
  pedido: Request,
  ctx: RouteContext<"/api/trades/operacoes/[id]">,
) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  const id = identificador((await ctx.params).id);
  if (id === null) return NextResponse.json({ erro: "id invalido" }, { status: 400 });

  try {
    const corpo = await pedido.json();
    const trade = await editarOperacao(id, corpo);
    return trade
      ? NextResponse.json({ trade })
      : NextResponse.json({ erro: "nao encontrado" }, { status: 404 });
  } catch (erro) {
    if (erro instanceof OperacaoInvalida) {
      return NextResponse.json({ erro: erro.message }, { status: 400 });
    }
    return NextResponse.json({ erro: "pedido invalido" }, { status: 400 });
  }
}

export async function DELETE(
  _pedido: Request,
  ctx: RouteContext<"/api/trades/operacoes/[id]">,
) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  const id = identificador((await ctx.params).id);
  if (id === null) return NextResponse.json({ erro: "id invalido" }, { status: 400 });

  try {
    const { apagado, trade } = await apagarOperacao(id);
    // 200 com corpo, e nao 204: ver o comentario em `api/alertas/[id]/route.ts`
    // -- resposta sem corpo chega no navegador como net::ERR_ABORTED.
    return apagado
      ? NextResponse.json({ apagado: true, trade })
      : NextResponse.json({ erro: "nao encontrado" }, { status: 404 });
  } catch (erro) {
    if (erro instanceof OperacaoInvalida) {
      return NextResponse.json({ erro: erro.message }, { status: 400 });
    }
    return NextResponse.json({ erro: "pedido invalido" }, { status: 400 });
  }
}
