import { Suspense } from "react";
import { FichaDoPapel } from "@/components/FichaDoPapel";
import { papeisComEvento, papel } from "@/lib/db";

/** Uma pagina estatica por papel que teve ao menos um evento. */
export async function generateStaticParams() {
  const tickers = await papeisComEvento();
  return tickers.map((ticker) => ({ ticker }));
}

export const dynamicParams = false;

export default async function Papel({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const dados = await papel(ticker);

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
