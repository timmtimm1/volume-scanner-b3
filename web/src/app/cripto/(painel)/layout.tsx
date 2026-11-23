import Link from "next/link";
import { ehDono, signIn, signOut } from "@/auth";
import { ColunasDaCripto } from "@/components/ColunasDaCripto";
import { ListaDeMoedas } from "@/components/ListaDeMoedas";
import { semCripto } from "@/lib/cripto";
import type { LinhaDaMoeda } from "@/lib/cripto-lista";
import { lerListaDeMoedas } from "@/lib/cripto-painel";

/**
 * A aba Cripto (refeita em 23/11/2026): a lista de moedas fica aqui, no layout,
 * porque layout nao recarrega quando so a `?moeda=` muda. Trocar de moeda busca
 * apenas o grafico, e a busca digitada continua no campo.
 *
 * So para quem esta logado. As entradas, o volume e os encerrados foram para
 * `/cripto/setups`.
 */
export const dynamic = "force-dynamic";

const BOTAO =
  "toque inline-flex h-10 items-center rounded-full border border-linha-2 px-3 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta sm:px-4";

export default async function LayoutDaCripto({ children }: { children: React.ReactNode }) {
  if (!(await ehDono())) {
    return (
      <section className="cartao mx-auto flex max-w-[560px] flex-col gap-4 p-6 md:mt-8 md:p-8">
        <h1 className="text-[22px] font-extrabold tracking-tight">Cripto</h1>
        <p className="text-[14px] leading-relaxed text-tinta-2">
          As 50 maiores criptomoedas numa lista só: busque a moeda, abra o gráfico e registre seus
          trades.
        </p>
        <form
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: "/cripto" });
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

  let linhas: LinhaDaMoeda[];
  try {
    linhas = await lerListaDeMoedas();
  } catch (erro) {
    if (!semCripto(erro)) throw erro;
    return (
      <section className="cartao flex flex-col gap-3 p-5">
        <h1 className="text-[22px] font-extrabold tracking-tight">Cripto</h1>
        <p className="text-[14px] leading-relaxed text-tinta-2">
          Ainda não há dado de cripto neste banco. A primeira carga roda pelo workflow{" "}
          <span className="num font-bold">cripto</span> do GitHub (Actions → cripto → Run
          workflow).
        </p>
      </section>
    );
  }

  const cabecalho = (
    <section className="cartao flex items-center gap-2 px-4 py-3 sm:gap-3 sm:px-5">
      <h1 className="text-[22px] font-extrabold tracking-tight">Cripto</h1>
      <div className="flex-1" />
      <Link href="/cripto/setups" className={BOTAO}>
        Setups
      </Link>
      <Link href="/trades?mercado=cripto" className={BOTAO}>
        Seus trades
      </Link>
      <form
        action={async () => {
          "use server";
          await signOut({ redirectTo: "/cripto" });
        }}
      >
        <button type="submit" className={BOTAO}>
          Sair
        </button>
      </form>
    </section>
  );

  return (
    <ColunasDaCripto cabecalho={cabecalho} lista={<ListaDeMoedas linhas={linhas} />}>
      {children}
    </ColunasDaCripto>
  );
}
