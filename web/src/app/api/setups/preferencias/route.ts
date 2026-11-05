/**
 * Preferencias dos setups: alerta ligado ou nao e a saida de cada um.
 *
 * Exige sessao, como o resto da aba Setups. O pipeline le a mesma tabela na
 * proxima noite: o que vale para os setups que armarem dali em diante.
 */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import { CATEGORIAS_DE_SETUP, type CategoriaDoSetup, type SaidaDoSetup } from "@/lib/config";
import { gravarPreferencia, preferenciasDosSetups } from "@/lib/setups";

export const dynamic = "force-dynamic";

const SAIDAS: readonly string[] = ["alvo1", "alvo2", "alvo3", "minimas", "mme9"];

export async function GET() {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  return NextResponse.json({ preferencias: await preferenciasDosSetups() });
}

export async function PATCH(pedido: Request) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  let corpo: unknown;
  try {
    corpo = await pedido.json();
  } catch {
    return NextResponse.json({ erro: "pedido invalido" }, { status: 400 });
  }
  const { categoria, alerta, saida } = (corpo ?? {}) as Record<string, unknown>;
  if (typeof categoria !== "string" || !(CATEGORIAS_DE_SETUP as readonly string[]).includes(categoria)) {
    return NextResponse.json({ erro: "setup desconhecido" }, { status: 400 });
  }
  if (typeof alerta !== "boolean") {
    return NextResponse.json({ erro: "alerta deve ser verdadeiro ou falso" }, { status: 400 });
  }
  if (typeof saida !== "string" || !SAIDAS.includes(saida)) {
    return NextResponse.json({ erro: "saida desconhecida" }, { status: 400 });
  }
  try {
    await gravarPreferencia(categoria as CategoriaDoSetup, alerta, saida as SaidaDoSetup);
  } catch (erro) {
    // A tabela nasce na migration 0017: sem ela, nao ha onde gravar.
    if ((erro as { code?: string }).code === "42P01") {
      return NextResponse.json({ erro: "a tabela de preferências ainda não existe" }, { status: 503 });
    }
    throw erro;
  }
  return NextResponse.json({ preferencias: await preferenciasDosSetups() });
}
