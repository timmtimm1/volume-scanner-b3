import { notFound } from "next/navigation";
import { ehDono, signIn } from "@/auth";
import { DetalheDoTrade } from "@/components/DetalheDoTrade";
import { detalharTrade } from "@/lib/trades";

/** Trade muda por acao do usuario e pela marcacao noturna: nunca pre-renderizado. */
export const dynamic = "force-dynamic";

/** Id da rota para numero, ou null se nao for um -- mesma regra das rotas de API. */
function identificador(bruto: string): number | null {
  const n = Number(bruto);
  return Number.isInteger(n) && n > 0 ? n : null;
}

export default async function TradePorId({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  if (!(await ehDono())) {
    return (
      <section className="cartao mx-auto flex max-w-[560px] flex-col gap-4 p-6 md:mt-8 md:p-8">
        <h1 className="text-[22px] font-extrabold tracking-tight">Trade</h1>
        <p className="text-[14px] leading-relaxed text-tinta-2">
          Este trade é dado pessoal. Entre com a conta dona do projeto para ver.
        </p>
        <form
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: "/trades" });
          }}
        >
          <button
            type="submit"
            className="toque flex h-12 w-full items-center justify-center gap-2.5 rounded-full bg-primario text-[15px] font-extrabold text-primario-tinta"
          >
            <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
            </svg>
            Entrar com GitHub
          </button>
        </form>
      </section>
    );
  }

  const { id } = await params;
  const idNumerico = identificador(id);
  if (idNumerico === null) notFound();

  const trade = await detalharTrade(idNumerico);
  if (!trade) notFound();

  return <DetalheDoTrade inicial={trade} />;
}
