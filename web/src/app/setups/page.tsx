import { ehDono, signIn, signOut } from "@/auth";
import Link from "next/link";
import { ListaDeSetups } from "@/components/ListaDeSetups";
import { PerfilDeRisco } from "@/components/PerfilDeRisco";
import { escolhasDa, rodadaAtual } from "@/lib/backtest";
import type { Nivel } from "@/lib/backtest-tela";
import { CATEGORIAS_DE_SETUP } from "@/lib/config";
import { lerPerfil } from "@/lib/perfil";
import { conferenciaAoVivo, listarSetups, preferenciasDosSetups } from "@/lib/setups";
import { type CategoriaDoSetup, type Conferencia, categoriaDaChave } from "@/lib/setups-tela";
import { tradesDosSetups } from "@/lib/trades";
import { hojeNaB3 } from "@/lib/validade";

/**
 * Setups: os de alerta ligado em cima, os outros fechados embaixo (secoes 13 e
 * 14 do plano).
 *
 * Mesma estrutura de `/trades`: le a sessao, entao roda no servidor a cada
 * visita, e quem nao esta logado so ve o que a aba e. Decisao de 21/10/2026:
 * uma pagina publica de "setups" leria como recomendacao de investimento.
 */
export const dynamic = "force-dynamic";

export default async function Setups() {
  if (!(await ehDono())) {
    return (
      <section className="cartao mx-auto flex max-w-[560px] flex-col gap-4 p-6 md:mt-8 md:p-8">
        <h1 className="text-[22px] font-extrabold tracking-tight">Setups</h1>
        <p className="text-[14px] leading-relaxed text-tinta-2">
          Os setups do dia: o que armou, o que está em andamento e o que já terminou, com o
          alerta e a saída que você escolhe para cada um.
        </p>
        <form
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: "/setups" });
          }}
        >
          <button
            type="submit"
            className="toque flex h-12 w-full items-center justify-center gap-2.5 rounded-full bg-primario text-[15px] font-extrabold text-primario-tinta"
          >
            Entrar com GitHub
          </button>
        </form>
        <p className="text-[12px] font-semibold text-tinta-3">
          Só a conta dona do projeto entra. Ter conta no GitHub não basta.
        </p>
      </section>
    );
  }

  const [setups, preferencias, rodada, aoVivo, perfil, trades] = await Promise.all([
    listarSetups(),
    preferenciasDosSetups(),
    rodadaAtual(),
    conferenciaAoVivo(),
    lerPerfil(),
    tradesDosSetups(),
  ]);
  // O selo de cada bloco e o nivel da rodada mais recente; sem rodada, sem selo.
  // A conferencia junta o ao vivo (desde a estreia) com o numero do backtest.
  const niveis: Partial<Record<CategoriaDoSetup, Nivel>> = {};
  const conferencias: Partial<Record<CategoriaDoSetup, Conferencia>> = {};
  for (const c of CATEGORIAS_DE_SETUP) {
    conferencias[c] = { aoVivo: aoVivo[c] ?? null, backtest: null };
  }
  if (rodada) {
    for (const e of await escolhasDa(rodada.id)) {
      const categoria = categoriaDaChave(e.setup);
      if (!categoria) continue;
      niveis[categoria] = e.nivel;
      conferencias[categoria] = {
        aoVivo: aoVivo[categoria] ?? null,
        backtest: { r: e.expConferencia, saida: e.saida },
      };
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-wrap items-center gap-4 p-5">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h1 className="text-[22px] font-extrabold tracking-tight">Setups</h1>
          <p className="text-[13px] font-semibold text-tinta-3">
            Cada setup tem o seu bloco. Ligue o alerta nos que quiser acompanhar.
          </p>
        </div>
        <div className="flex-1" />
        <Link
          href="/setups/backtest"
          className="toque inline-flex h-10 items-center rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
        >
          Backtest
        </Link>
        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/setups" });
          }}
        >
          <button
            type="submit"
            className="toque h-10 rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
          >
            Sair
          </button>
        </form>
      </section>

      <PerfilDeRisco inicial={perfil} />

      <ListaDeSetups
        setups={setups}
        preferencias={preferencias}
        niveis={niveis}
        conferencias={conferencias}
        hoje={hojeNaB3()}
        diario={{ perfil, tradePorSetup: trades.porSetup, abertoPorTicker: trades.abertoPorTicker }}
      />
    </div>
  );
}
