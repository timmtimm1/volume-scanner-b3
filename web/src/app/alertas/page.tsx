import { ehDono, signIn, signOut } from "@/auth";
import { ListaDeAlertas } from "@/components/ListaDeAlertas";
import { listarAlertas } from "@/lib/alertas";

/**
 * A unica tela do site que depende de quem esta olhando.
 *
 * As outras sao geradas no build e servidas do CDN. Esta le a sessao, entao
 * roda no servidor a cada visita -- e por isso ela existe sozinha, numa rota
 * propria, em vez de virar um pedaco condicional das telas de dado.
 */
export const dynamic = "force-dynamic";

export default async function Alertas() {
  if (!(await ehDono())) {
    return (
      <section className="cartao mx-auto flex max-w-[560px] flex-col gap-4 p-6 md:mt-8 md:p-8">
        <h1 className="text-[22px] font-extrabold tracking-tight">Alertas de rompimento</h1>
        <p className="text-[14px] leading-relaxed text-tinta-2">
          Escolha um nível no gráfico de um papel e receba no Telegram quando o preço chegar lá.
          A checagem roda de 15 em 15 minutos durante o pregão.
        </p>
        <form
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: "/alertas" });
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
        <p className="text-[12px] font-semibold text-tinta-3">
          Só a conta dona do projeto entra. Ter conta no GitHub não basta.
        </p>
      </section>
    );
  }

  const alertas = await listarAlertas();

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-wrap items-center gap-4 p-5">
        {/* Sem contador aqui: ele mudaria ao religar ou apagar, e este e um
            componente de servidor -- ficaria mostrando o numero de antes. Ele
            vive dentro da lista, junto do estado que o determina. */}
        <div className="flex flex-col gap-0.5">
          <h1 className="text-[22px] font-extrabold tracking-tight">Alertas de rompimento</h1>
          <p className="text-[13px] font-semibold text-tinta-3">
            Checagem de 15 em 15 minutos durante o pregão
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
            className="toque h-10 rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
          >
            Sair
          </button>
        </form>
      </section>

      <ListaDeAlertas iniciais={alertas} />
    </div>
  );
}
