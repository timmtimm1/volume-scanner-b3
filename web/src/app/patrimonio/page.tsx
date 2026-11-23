import Link from "next/link";
import { ehDono, signIn } from "@/auth";
import { CurvaDoPatrimonio } from "@/components/CurvaDoPatrimonio";
import { PerfilDeRisco } from "@/components/PerfilDeRisco";
import { SecaoRecolhida } from "@/components/SecaoRecolhida";
import { ZerarTrades } from "@/components/ZerarTrades";
import { semCripto } from "@/lib/cripto";
import { data, percentual } from "@/lib/formato";
import { valor, valorComSinal } from "@/lib/mercado";
import { lerPatrimonio } from "@/lib/patrimonio-dados";

/**
 * Evolucao do patrimonio em cripto, em dolar (pedido de 23/11/2026): capital do
 * perfil + resultado dos trades, dia a dia. So para quem esta logado.
 */
export const dynamic = "force-dynamic";

const MERCADO = "cripto" as const;
const DIAS_NA_TABELA = 60;

const corDe = (v: number) => (v > 0 ? "text-alta" : v < 0 ? "text-baixa" : "text-tinta");

function Numero({
  rotulo,
  texto,
  detalhe,
  cor = "text-tinta",
}: {
  rotulo: string;
  texto: string;
  detalhe?: string;
  cor?: string;
}) {
  return (
    <div className="cartao flex min-w-0 flex-col gap-0.5 p-4">
      <span className="text-[12px] font-bold text-tinta-3">{rotulo}</span>
      <span className={`num truncate text-[20px] font-extrabold ${cor}`}>{texto}</span>
      {detalhe && <span className="num text-[12px] font-semibold text-tinta-3">{detalhe}</span>}
    </div>
  );
}

export default async function Patrimonio() {
  if (!(await ehDono())) {
    return (
      <section className="cartao mx-auto flex max-w-[560px] flex-col gap-4 p-6 md:mt-8 md:p-8">
        <h1 className="text-[22px] font-extrabold tracking-tight">Patrimônio</h1>
        <p className="text-[14px] leading-relaxed text-tinta-2">
          A evolução do seu capital em cripto, com o resultado de cada trade somado dia a dia.
        </p>
        <form
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: "/patrimonio" });
          }}
        >
          <button
            type="submit"
            className="toque flex h-12 w-full items-center justify-center rounded-full bg-primario text-[15px] font-extrabold text-primario-tinta"
          >
            Entrar com GitHub
          </button>
        </form>
      </section>
    );
  }

  let dados: Awaited<ReturnType<typeof lerPatrimonio>>;
  try {
    dados = await lerPatrimonio();
  } catch (erro) {
    if (!semCripto(erro)) throw erro;
    return (
      <section className="cartao p-5 text-[14px] font-semibold text-tinta-2">
        Ainda não há dado de cripto neste banco.
      </section>
    );
  }
  const { perfil, curva, resumo, totais } = dados;

  if (perfil === null) {
    return (
      <div className="flex flex-col gap-4">
        <section className="cartao flex flex-col gap-1 p-5">
          <h1 className="text-[22px] font-extrabold tracking-tight">Patrimônio</h1>
          <p className="text-[13px] font-semibold text-tinta-3">
            Informe o seu capital em cripto: a curva parte dele.
          </p>
        </section>
        <PerfilDeRisco inicial={null} mercado={MERCADO} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-wrap items-center gap-3 px-5 py-3">
        <div className="flex min-w-0 flex-col">
          <h1 className="text-[22px] font-extrabold tracking-tight">Patrimônio</h1>
          <p className="text-[13px] font-semibold text-tinta-3">Trades de cripto, em dólar</p>
        </div>
        <div className="flex-1" />
        <Link
          href="/trades?mercado=cripto"
          className="toque inline-flex h-10 items-center rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
        >
          Seus trades
        </Link>
      </section>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Numero
          rotulo="Patrimônio agora"
          texto={valor(MERCADO, resumo.atual)}
          detalhe={`capital inicial ${valor(MERCADO, resumo.capital)}`}
        />
        <Numero
          rotulo="Resultado total"
          texto={valorComSinal(MERCADO, resumo.resultado)}
          detalhe={percentual(resumo.resultadoPct)}
          cor={corDe(resumo.resultado)}
        />
        <Numero
          rotulo="Realizado / em aberto"
          texto={valorComSinal(MERCADO, resumo.realizado)}
          detalhe={`em aberto ${valorComSinal(MERCADO, resumo.aberto)}`}
          cor={corDe(resumo.realizado)}
        />
        <Numero
          rotulo="Maior queda"
          texto={valorComSinal(MERCADO, resumo.maiorQueda)}
          detalhe={percentual(resumo.maiorQuedaPct)}
          cor={corDe(resumo.maiorQueda)}
        />
      </div>

      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <h2 className="text-[18px] font-extrabold">Evolução do patrimônio</h2>
        {curva.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-linha-2 p-8 text-center text-[14px] font-semibold text-tinta-3">
            Nenhum trade de cripto registrado. A curva começa no seu primeiro trade.{" "}
            <Link href="/cripto" className="font-bold text-acento">
              Abrir as moedas
            </Link>
          </p>
        ) : (
          <>
            <CurvaDoPatrimonio curva={curva} capital={resumo.capital} />
            <p className="text-[12px] font-semibold leading-relaxed text-tinta-3">
              Capital do seu perfil mais o resultado de todos os trades, já com as taxas. Os dias
              passados usam o fechamento das 21h; o último ponto usa o preço de agora. Depósitos e
              saques não entram: mudar o capital no perfil muda a curva inteira.
            </p>
            <details className="group">
              <summary className="toque flex cursor-pointer list-none items-center text-[13px] font-bold text-tinta-2 [&::-webkit-details-marker]:hidden">
                Ver dia a dia
                <span aria-hidden className="ml-2 transition-transform group-open:rotate-90">
                  ›
                </span>
              </summary>
              <div className="overflow-x-auto">
                <table className="num w-full text-right text-[12px] font-semibold">
                  <thead className="text-tinta-3">
                    <tr>
                      <th className="py-1.5 text-left font-bold">Dia</th>
                      <th className="py-1.5 font-bold">Patrimônio</th>
                      <th className="py-1.5 font-bold">Realizado</th>
                      <th className="py-1.5 font-bold">Em aberto</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-linha">
                    {curva
                      .slice(-DIAS_NA_TABELA)
                      .reverse()
                      .map((p) => (
                        <tr key={p.dia}>
                          <td className="py-1.5 text-left">{data(p.dia)}</td>
                          <td className="py-1.5 font-bold">{valor(MERCADO, p.patrimonio)}</td>
                          <td className="py-1.5">{valorComSinal(MERCADO, p.realizado)}</td>
                          <td className="py-1.5">{valorComSinal(MERCADO, p.aberto)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        )}
      </section>

      <SecaoRecolhida titulo="Seu capital em cripto">
        <PerfilDeRisco inicial={perfil} mercado={MERCADO} />
      </SecaoRecolhida>

      {totais.trades > 0 && (
        <SecaoRecolhida titulo="Zerar trades de cripto" contagem={totais.trades}>
          <ZerarTrades totais={totais} />
        </SecaoRecolhida>
      )}
    </div>
  );
}
