import { auth, signIn, signOut } from "@/auth";
import { listarAlertas } from "@/lib/alertas";
import { ListaDeAlertas } from "@/components/ListaDeAlertas";

/**
 * A unica tela do site que depende de quem esta olhando.
 *
 * As outras sao geradas no build e servidas do CDN. Esta le a sessao, entao
 * roda no servidor a cada visita -- e por isso ela existe sozinha, numa rota
 * propria, em vez de virar um pedaco condicional das telas de dado.
 */
export const dynamic = "force-dynamic";

export default async function Alertas() {
  const sessao = await auth();

  if (!sessao?.user) {
    return (
      <div className="p-6 md:p-10">
        <h1 className="text-[17px] font-bold">Alertas de rompimento</h1>
        <p className="mt-2 max-w-[52ch] text-[13px] leading-relaxed text-tinta-2">
          Escolha um nível no gráfico de um papel e receba no Telegram quando o
          preço chegar lá. A checagem roda de 15 em 15 minutos durante o pregão.
        </p>
        <form
          className="mt-6"
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: "/alertas" });
          }}
        >
          <button
            type="submit"
            className="toque rounded border border-ambar bg-selecao px-4 py-2 text-[13px] text-ambar transition-colors hover:bg-linha-2"
          >
            Entrar com GitHub
          </button>
        </form>
        <p className="mt-3 text-[11px] text-tinta-3">
          Só a conta dona do projeto entra. Ter conta no GitHub não basta.
        </p>
      </div>
    );
  }

  const alertas = await listarAlertas();

  return (
    <>
      <header className="flex flex-wrap items-center gap-4 border-b border-linha bg-painel px-4 py-3.5 md:px-6">
        <div>
          <h1 className="text-[17px] font-bold">Alertas de rompimento</h1>
          <p className="num mt-0.5 text-[11px] text-tinta-3">
            {alertas.filter((a) => a.ativo).length} ativos de {alertas.length}
          </p>
        </div>
        <div className="flex-1" />
        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/alertas" });
          }}
        >
          <button
            type="submit"
            className="toque rounded border border-linha-2 px-3 py-1.5 text-[11px] text-tinta-2 transition-colors hover:text-tinta"
          >
            sair
          </button>
        </form>
      </header>

      <ListaDeAlertas iniciais={alertas} />
    </>
  );
}
