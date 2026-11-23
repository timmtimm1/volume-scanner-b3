/**
 * Zerar os trades de cripto: GET baixa o backup, POST apaga.
 *
 * O mercado e fixo aqui, e nao um parametro: esta rota nao tem como apagar os
 * trades de acoes. O POST exige a palavra digitada e a quantidade que a tela
 * mostrou (`zerar-trades.ts` recusa se ela mudou).
 */

import { NextResponse } from "next/server";
import { ehDono } from "@/auth";
import { noMercado } from "@/lib/mercado-servidor";
import { backupDosTrades, ContagemMudou, zerarTrades } from "@/lib/zerar-trades";

export const dynamic = "force-dynamic";

const MERCADO = "cripto" as const;
const PALAVRA = "ZERAR";

export async function GET() {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  const backup = await noMercado(MERCADO, backupDosTrades);
  return new Response(backup, {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

export async function POST(pedido: Request) {
  if (!(await ehDono())) {
    return NextResponse.json({ erro: "nao autorizado" }, { status: 401 });
  }
  const corpo: unknown = await pedido.json().catch(() => null);
  const { confirmacao, esperado } = (corpo ?? {}) as { confirmacao?: unknown; esperado?: unknown };
  if (confirmacao !== PALAVRA || typeof esperado !== "number" || !Number.isInteger(esperado) || esperado < 0) {
    return NextResponse.json({ erro: "confirmação inválida" }, { status: 400 });
  }
  try {
    const { apagados } = await noMercado(MERCADO, () => zerarTrades(esperado));
    return NextResponse.json({ apagados });
  } catch (erro) {
    if (erro instanceof ContagemMudou) {
      return NextResponse.json(
        { erro: "A quantidade de trades mudou. Recarregue a página e baixe o backup de novo.", atual: erro.atual },
        { status: 409 },
      );
    }
    throw erro;
  }
}
