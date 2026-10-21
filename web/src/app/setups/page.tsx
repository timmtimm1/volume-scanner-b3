import { ehDono, signIn, signOut } from "@/auth";
import { ListaDeSetups } from "@/components/ListaDeSetups";
import { listarSetups } from "@/lib/setups";
import { hojeNaB3 } from "@/lib/validade";

/**
 * Setups: candle de reversao no suporte, filtrado (secao 13 do plano).
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
          Candles de reversão em suporte, filtrados por volume, contexto e espaço até a
          resistência, com o alerta de confirmação e o histórico de cada um.
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

  const setups = await listarSetups();

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-wrap items-center gap-4 p-5">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h1 className="text-[22px] font-extrabold tracking-tight">Setups</h1>
          <p className="text-[13px] font-semibold text-tinta-3">
            Candle de reversão em suporte de 3+ toques · volume de 1,5× ou mais · fora de queda
            e de tendência de baixa · resistência a 2× o risco ou mais
          </p>
        </div>
        <div className="flex-1" />
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

      <ListaDeSetups setups={setups} hoje={hojeNaB3()} />
    </div>
  );
}
