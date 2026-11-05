/**
 * Perfil de risco: capital e risco por trade, salvos na conta.
 *
 * Exige sessao, inclusive a leitura: o capital e dado pessoal e o site e
 * publico.
 */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import { PerfilInvalido, faltaAMigration, gravarPerfil, lerPerfil } from "@/lib/perfil";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  return NextResponse.json({ perfil: await lerPerfil() });
}

export async function PUT(pedido: Request) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  let corpo: unknown;
  try {
    corpo = await pedido.json();
  } catch {
    return NextResponse.json({ erro: "pedido invalido" }, { status: 400 });
  }
  try {
    return NextResponse.json({ perfil: await gravarPerfil(corpo) });
  } catch (erro) {
    if (erro instanceof PerfilInvalido) {
      return NextResponse.json({ erro: erro.message }, { status: 400 });
    }
    // A tabela nasce na migration 0018: sem ela, nao ha onde gravar.
    if (faltaAMigration(erro)) {
      return NextResponse.json({ erro: "a tabela do perfil ainda não existe" }, { status: 503 });
    }
    throw erro;
  }
}
