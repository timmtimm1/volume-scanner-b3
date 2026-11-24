import { ehDono, signIn } from "@/auth";
import { SecaoRecolhida } from "@/components/SecaoRecolhida";
import { TabelaDaAnalise } from "@/components/TabelaDaAnalise";
import { lerVisaoGeral } from "@/lib/analise-dados";
import { montarTabela } from "@/lib/analise";
import { semCripto } from "@/lib/cripto";
import { data } from "@/lib/formato";

/**
 * Cada cripto contra o Bitcoin, ano a ano (pedido de 24/11/2026). Retorno
 * passado, medido e mostrado com a conta a vista: nao e recomendacao. So para
 * quem esta logado.
 */
export const dynamic = "force-dynamic";

const MOTIVOS: Record<string, [string, string]> = {
  estavel: ["moeda estável", "moedas estáveis"],
  embrulhado: ["moeda embrulhada", "moedas embrulhadas"],
  alavancado: ["token alavancado", "tokens alavancados"],
  "acao tokenizada": ["ação tokenizada", "ações tokenizadas"],
};

function listaDoQueFicouFora(fora: { motivo: string; n: number }[]): string {
  const partes = fora.map(({ motivo, n }) => {
    const [um, varios] = MOTIVOS[motivo] ?? [motivo, motivo];
    return `${n} ${n === 1 ? um : varios}`;
  });
  if (partes.length === 0) return "nada";
  if (partes.length === 1) return partes[0];
  return `${partes.slice(0, -1).join(", ")} e ${partes[partes.length - 1]}`;
}

export default async function Analise() {
  if (!(await ehDono())) {
    return (
      <section className="cartao mx-auto flex max-w-[560px] flex-col gap-4 p-6 md:mt-8 md:p-8">
        <h1 className="text-[22px] font-extrabold tracking-tight">Análise</h1>
        <p className="text-[14px] leading-relaxed text-tinta-2">
          Cada cripto contra o Bitcoin, ano a ano e mês a mês, com beta e correlação.
        </p>
        <form
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: "/analise" });
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

  let visao: Awaited<ReturnType<typeof lerVisaoGeral>>;
  try {
    visao = await lerVisaoGeral();
  } catch (erro) {
    if (!semCripto(erro)) throw erro;
    return (
      <section className="cartao p-5 text-[14px] font-semibold text-tinta-2">
        Ainda não há dado de cripto neste banco.
      </section>
    );
  }

  if (visao.ate === null) {
    return (
      <section className="cartao p-5 text-[14px] font-semibold leading-relaxed text-tinta-2">
        A análise ainda não foi calculada. Ela roda toda noite depois da carga de cripto (workflow
        cripto analise).
      </section>
    );
  }

  const { anos, linhas } = montarTabela(visao.moedas, visao.anuais);
  const totalFora = visao.fora.reduce((soma, f) => soma + f.n, 0);

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-col gap-0.5 px-5 py-3">
        <h1 className="text-[22px] font-extrabold tracking-tight">Análise</h1>
        <p className="text-[13px] font-semibold text-tinta-3">
          Cada cripto contra o Bitcoin, ano a ano · dados até {data(visao.ate)}
        </p>
      </section>

      <SecaoRecolhida titulo="Como ler">
        <div className="flex flex-col gap-2.5 text-[13px] leading-relaxed text-tinta-2">
          <p>
            <b className="text-tinta">Contra o BTC.</b> Imagine que, no começo do ano, você trocou 1
            Bitcoin pela moeda. No fim do ano, quanto a mais ou a menos de Bitcoin você teria? Verde:
            a moeda foi mais forte que o Bitcoin. Vermelho: foi mais fraca. Quanto mais escuro, maior
            a diferença. Isso não é lucro em dólar: uma moeda pode subir em dólar e mesmo assim ficar
            vermelha, se o Bitcoin subiu mais.
          </p>
          <p>
            <b className="text-tinta">Linha do BTC.</b> Na linha &quot;BTC (régua)&quot; aparece o
            que o próprio Bitcoin rendeu em dólar em cada ano. É a régua das outras linhas.
          </p>
          <p>
            <b className="text-tinta">Beta.</b> Num dia em que o Bitcoin mexe 1%, a moeda costuma mexer
            beta% no mesmo sentido. Beta 1,5: ela anda uma vez e meia o que o Bitcoin anda, para cima e
            para baixo. Beta abaixo de 1: anda menos que ele.
          </p>
          <p>
            <b className="text-tinta">Correlação.</b> Vai de −1 a 1 e diz o quanto a moeda se mexe
            junto com o Bitcoin. Perto de 1: quase sempre sobem e descem juntos. Perto de 0: cada um na
            sua. Perto de −1: um sobe quando o outro desce.
          </p>
          <p>
            <b className="text-tinta">Asterisco (*) e itálico.</b> Período incompleto: a moeda
            entrou na Binance no meio do ano, saiu dela, ou o ano ainda não acabou. Passe o mouse (ou
            toque) na célula para ver as datas.
          </p>
          <p>
            <b className="text-tinta">O que ficou de fora.</b>{" "}
            {totalFora > 0
              ? `${totalFora} moedas que não são cripto "de verdade" para esta conta: ${listaDoQueFicouFora(visao.fora)}. `
              : "Nada ficou de fora. "}
            As moedas que saíram da Binance continuam na lista, marcadas como &quot;parada&quot;:
            tirar as que deram errado faria o passado parecer melhor do que foi.
          </p>
        </div>
      </SecaoRecolhida>

      <TabelaDaAnalise anos={anos} linhas={linhas} />
    </div>
  );
}
