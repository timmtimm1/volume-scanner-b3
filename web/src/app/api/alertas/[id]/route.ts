/** Alertas: apagar e religar. */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import { apagarAlerta, reativarAlerta } from "@/lib/alertas";

// Redundante no Next 16 -- desde a v15 o padrao de handler GET ja e dinamico, e
// `auth()` le cookie, o que por si so tiraria a rota do cache. Fica explicito
// de proposito: alerta e dado pessoal, e a intencao de nunca ser cacheado deve
// estar escrita, nao inferida de um efeito colateral.
export const dynamic = "force-dynamic";

/** Id da rota para numero, ou null se nao for um. */
function identificador(bruto: string): number | null {
  const n = Number(bruto);
  return Number.isInteger(n) && n > 0 ? n : null;
}

export async function DELETE(_pedido: Request, ctx: RouteContext<"/api/alertas/[id]">) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  const id = identificador((await ctx.params).id);
  if (id === null) return NextResponse.json({ erro: "id invalido" }, { status: 400 });

  return (await apagarAlerta(id))
    ? new NextResponse(null, { status: 204 })
    : NextResponse.json({ erro: "nao encontrado" }, { status: 404 });
}

export async function PATCH(_pedido: Request, ctx: RouteContext<"/api/alertas/[id]">) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  const id = identificador((await ctx.params).id);
  if (id === null) return NextResponse.json({ erro: "id invalido" }, { status: 400 });

  // A unica alteracao possivel e religar. Nao ha edicao de nivel: mudar o preco
  // de um alerta ja disparado apagaria o registro de por que ele disparou.
  const alerta = await reativarAlerta(id);
  return alerta
    ? NextResponse.json({ alerta })
    : NextResponse.json({ erro: "nao encontrado" }, { status: 404 });
}
