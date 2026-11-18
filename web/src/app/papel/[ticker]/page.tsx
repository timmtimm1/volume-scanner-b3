import { notFound } from "next/navigation";
import { Suspense } from "react";
import { FichaDoPapel } from "@/components/FichaDoPapel";
import { fundamentos, niveisDoPapel, papeisComEventoRecente, papel } from "@/lib/db";
import { TICKER } from "@/lib/ticker";
import { juroLongo } from "@/lib/valuation-dados";

/**
 * Uma pagina estatica por papel com evento nos ultimos pregoes (o scanner do
 * dia e os links do Telegram da semana). As outras fichas sao geradas no
 * primeiro acesso -- ver `papeisComEventoRecente` para o porque.
 */
export async function generateStaticParams() {
  const tickers = await papeisComEventoRecente();
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

  // As duas em paralelo: o build faz isso uma vez por papel com ficha.
  const [dados, balancos, juro] = await Promise.all([
    papel(ticker),
    fundamentos(ticker),
    // O juro longo da taxa de desconto do "Preço justo": uma linha de uma tabela pequena.
    juroLongo(),
  ]);
  if (dados.barras.length === 0) notFound();
  // Suportes e resistencias que chegam ao trecho do grafico (aba Setups).
  const niveis = await niveisDoPapel(dados.ticker, dados.barras[0].tradeDate);

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
        fundamentos={balancos}
        niveis={niveis}
        juro={juro}
      />
    </Suspense>
  );
}
