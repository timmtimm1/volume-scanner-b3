import Link from "next/link";
import { Suspense } from "react";
import { ehDono } from "@/auth";
import { FichaDaMoeda } from "@/components/FichaDaMoeda";
import { MOEDA, semCripto } from "@/lib/cripto";
import { MOEDA_PADRAO } from "@/lib/cripto-lista";
import { lerFichaDaMoeda } from "@/lib/cripto-painel";

export const dynamic = "force-dynamic";

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

async function PainelDaMoeda({ ticker, foco }: { ticker: string; foco: string | null }) {
  let ficha: Awaited<ReturnType<typeof lerFichaDaMoeda>>;
  try {
    ficha = await lerFichaDaMoeda(ticker);
  } catch (erro) {
    if (!semCripto(erro)) throw erro;
    ficha = null;
  }
  if (ficha === null) {
    return (
      <section className="cartao flex flex-col gap-2 p-6">
        <Link href="/cripto" className="text-[12px] font-bold text-tinta-3 hover:text-acento lg:hidden">
          ‹ Moedas
        </Link>
        <h2 className="text-[18px] font-extrabold">{ticker}</h2>
        <p className="text-[13px] font-semibold text-tinta-3">
          Esta moeda não tem candles no banco. O scanner acompanha as 50 maiores por valor de mercado.
        </p>
      </section>
    );
  }
  return <FichaDaMoeda {...ficha} foco={foco} />;
}

function Carregando({ ticker }: { ticker: string }) {
  return (
    <section className="cartao flex h-[420px] items-center justify-center p-6 lg:h-[640px]" aria-busy>
      <span className="text-[14px] font-bold text-tinta-3">Abrindo {ticker}...</span>
    </section>
  );
}

/** O painel da moeda aberta. A `key` faz o aviso de carregando aparecer na hora ao trocar. */
export default async function PaginaDaCripto({ searchParams }: Props) {
  // O layout nao e barreira de seguranca: a pagina confere o login por conta propria.
  if (!(await ehDono())) return null;
  const busca = await searchParams;
  const pedida = typeof busca.moeda === "string" ? decodeURIComponent(busca.moeda).toUpperCase() : null;
  const ticker = pedida && MOEDA.test(pedida) ? pedida : MOEDA_PADRAO;
  const foco = typeof busca.foco === "string" && /^\d{4}-\d{2}-\d{2}$/.test(busca.foco) ? busca.foco : null;
  return (
    <Suspense key={`${ticker}:${foco ?? ""}`} fallback={<Carregando ticker={ticker} />}>
      <PainelDaMoeda ticker={ticker} foco={foco} />
    </Suspense>
  );
}
