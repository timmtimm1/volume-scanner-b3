import Link from "next/link";
import { ehDono, signIn, signOut } from "@/auth";
import { DetalheDoBacktest } from "@/components/DetalheDoBacktest";
import { ResumoDoBacktest } from "@/components/ResumoDoBacktest";
import { anosDo, curvaDo, escolhasDa, resultadosDo, rodadaAtual, tradesDo } from "@/lib/backtest";
import { fmtCusto, lerSelecao } from "@/lib/backtest-tela";
import { data } from "@/lib/formato";

/**
 * Backtest: o resultado da suite que roda na maquina do dono (30 anos de
 * COTAHIST), gravado numa "rodada" no banco. Mostra sempre a mais recente.
 *
 * Mesma regra de `/setups`: so quem esta logado. Uma pagina publica de
 * resultados de setups leria como recomendacao de investimento.
 */
export const dynamic = "force-dynamic";

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function Backtest({ searchParams }: Props) {
  if (!(await ehDono())) {
    return (
      <section className="cartao mx-auto flex max-w-[560px] flex-col gap-4 p-6 md:mt-8 md:p-8">
        <h1 className="text-[22px] font-extrabold tracking-tight">Backtest</h1>
        <p className="text-[14px] leading-relaxed text-tinta-2">
          O que teria acontecido com cada setup de compra nos últimos 30 anos da bolsa, com
          custo, comparado a um papel sorteado no mesmo dia.
        </p>
        <form
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: "/setups/backtest" });
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

  const params = await searchParams;
  const rodada = await rodadaAtual();

  if (rodada === null) {
    return (
      <div className="flex flex-col gap-4">
        <Cabecalho />
        <section className="cartao flex flex-col gap-3 p-5">
          <h2 className="text-[18px] font-extrabold">Ainda não há rodada do backtest no banco</h2>
          <p className="text-[14px] leading-relaxed text-tinta-2">
            O backtest roda no seu computador e manda só o resultado para cá. Depois de rodar a
            suite, envie com:
          </p>
          <code className="block overflow-x-auto rounded-xl bg-painel-2 px-3.5 py-3 text-[13px] font-semibold text-tinta">
            python scripts/backtest_setups.py enviar &lt;pasta&gt;
          </code>
        </section>
      </div>
    );
  }

  const escolhas = await escolhasDa(rodada.id);
  const selecao = lerSelecao(params, escolhas);
  const [resultados, anos, curva, trades] = await Promise.all([
    resultadosDo(rodada.id, selecao.setup),
    anosDo(rodada.id, selecao.setup, selecao.saida, selecao.grupo),
    curvaDo(rodada.id, selecao.setup, selecao.saida, selecao.grupo),
    tradesDo(rodada.id, selecao.setup, selecao.saida, 50),
  ]);

  return (
    <div className="flex flex-col gap-4">
      <Cabecalho
        subtitulo={`Dados de ${data(rodada.dadosDe)} a ${data(rodada.dadosAte)} · ${rodada.trades.toLocaleString("pt-BR")} trades · custo de ${fmtCusto(rodada.custo)} por lado · saída forçada em ${rodada.teto} pregões`}
      />
      <ResumoDoBacktest escolhas={escolhas} selecao={selecao} />
      <DetalheDoBacktest
        selecao={selecao}
        escolha={escolhas.find((e) => e.setup === selecao.setup)}
        resultados={resultados}
        anos={anos}
        curva={curva}
        trades={trades}
      />
    </div>
  );
}

function Cabecalho({ subtitulo }: { subtitulo?: string }) {
  return (
    <section className="cartao flex flex-wrap items-center gap-x-4 gap-y-3 p-5">
      <div className="flex min-w-0 flex-col gap-1">
        <Link
          href="/setups"
          className="text-[13px] font-bold text-tinta-3 transition-colors hover:text-tinta"
        >
          ← Setups de hoje
        </Link>
        <h1 className="text-[22px] font-extrabold tracking-tight">Backtest</h1>
        {subtitulo && <p className="text-[13px] font-semibold text-tinta-3">{subtitulo}</p>}
      </div>
      <div className="flex-1" />
      <form
        action={async () => {
          "use server";
          await signOut({ redirectTo: "/setups/backtest" });
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
  );
}
