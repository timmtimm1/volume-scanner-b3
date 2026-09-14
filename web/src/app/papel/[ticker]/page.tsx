import { notFound } from "next/navigation";
import { Suspense } from "react";
import { FichaDoPapel } from "@/components/FichaDoPapel";
import { papeisComEvento, papel } from "@/lib/db";
import { TICKER } from "@/lib/ticker";

/** Uma pagina estatica por papel que teve ao menos um evento. */
export async function generateStaticParams() {
  const tickers = await papeisComEvento();
  return tickers.map((ticker) => ({ ticker }));
}

/**
 * Papel fora da lista do build tambem ganha ficha, gerada no primeiro acesso e
 * guardada ate o proximo deploy.
 *
 * E o caso do papel que cruza o limiar pela primeira vez: o Telegram manda o
 * link antes de o rebuild terminar, e com `dynamicParams = false` o link dava
 * 404. Ticker fora do formato ou sem barra nenhuma continua 404.
 */
export const dynamicParams = true;

export default async function Papel({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  if (!TICKER.test(ticker)) notFound();

  const dados = await papel(ticker);
  if (dados.barras.length === 0) notFound();

  return (
    <Suspense
      fallback={
        <div className="p-6 text-[13px] text-tinta-3">Carregando {ticker}…</div>
      }
    >
      <FichaDoPapel
        ticker={dados.ticker}
        barras={dados.barras}
        eventos={dados.eventos}
      />
    </Suspense>
  );
}
