/**
 * Arranjos do Organizar: ler, gravar e voltar ao padrao.
 *
 * Tudo exige sessao. Visitante recebe 401 e ve as paginas no arranjo padrao;
 * o botao Organizar nem aparece para ele.
 */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import {
  apagarArranjo,
  ArranjoInvalido,
  gravarArranjo,
  lerArranjos,
  lerPagina,
  lerPedido,
} from "@/lib/arranjos-no-banco";

// Muda por acao do dono, nunca por rebuild.
export const dynamic = "force-dynamic";

const NAO_AUTORIZADO = { erro: "nao autorizado" };

export async function GET() {
  if (!(await ehDono())) return NextResponse.json(NAO_AUTORIZADO, { status: 401 });
  return NextResponse.json({ arranjos: await lerArranjos() });
}

export async function PUT(pedido: Request) {
  if (!(await ehDono())) return NextResponse.json(NAO_AUTORIZADO, { status: 401 });
  try {
    const { pagina, itens } = lerPedido(await pedido.json());
    await gravarArranjo(pagina, itens);
    return NextResponse.json({ pagina, itens });
  } catch (erro) {
    if (erro instanceof ArranjoInvalido) {
      return NextResponse.json({ erro: erro.message }, { status: 400 });
    }
    if (erro instanceof SyntaxError) {
      return NextResponse.json({ erro: "pedido invalido" }, { status: 400 });
    }
    throw erro;
  }
}

export async function DELETE(pedido: Request) {
  if (!(await ehDono())) return NextResponse.json(NAO_AUTORIZADO, { status: 401 });
  try {
    const pagina = lerPagina(new URL(pedido.url).searchParams.get("pagina"));
    await apagarArranjo(pagina);
    return NextResponse.json({ pagina, itens: null });
  } catch (erro) {
    if (erro instanceof ArranjoInvalido) {
      return NextResponse.json({ erro: erro.message }, { status: 400 });
    }
    throw erro;
  }
}
