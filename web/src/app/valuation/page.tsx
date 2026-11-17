import { ehDono, signIn } from "@/auth";
import { TabelaDeValuation } from "@/components/TabelaDeValuation";
import { data, numero } from "@/lib/formato";
import {
  ANOS_DE_PROVENTOS,
  ANOS_PROJETADOS,
  CRESCIMENTO_PERPETUO,
  JURO_DE_RESERVA,
  PREMIO_DE_RISCO,
} from "@/lib/valuation";
import { valuationDeTodos } from "@/lib/valuation-dados";

/**
 * Valuation: tres contas simples de "preco justo" para todas as empresas com
 * balanco na CVM (pedido de 16/11/2026). Graham, Bazin e um fluxo de caixa
 * descontado sobre o lucro, cada uma comparada com o preco do ultimo pregao.
 *
 * So para quem esta logado, pelo mesmo motivo da aba Setups: uma pagina
 * publica dizendo que papel esta "abaixo do preco justo" leria como
 * recomendacao de investimento.
 */
export const dynamic = "force-dynamic";

const pct = (v: number, casas = 0) => `${numero(v * 100, casas)}%`;

export default async function Valuation() {
  if (!(await ehDono())) {
    return (
      <section className="cartao mx-auto flex max-w-[560px] flex-col gap-4 p-6 md:mt-8 md:p-8">
        <h1 className="text-[22px] font-extrabold tracking-tight">Valuation</h1>
        <p className="text-[14px] leading-relaxed text-tinta-2">
          Três contas simples de preço justo (Graham, Bazin e fluxo de caixa) para todas as
          empresas com balanço na CVM, comparadas com o preço do último pregão.
        </p>
        <form
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: "/valuation" });
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

  const { data: pregao, juro, linhas } = await valuationDeTodos();
  const desconto = (juro ?? JURO_DE_RESERVA) + PREMIO_DE_RISCO;
  const comConta = linhas.filter((l) => l.avaliacoes.some((a) => a.precoJusto !== null)).length;

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-col gap-1 p-5">
        <h1 className="text-[22px] font-extrabold tracking-tight">Valuation</h1>
        <p className="text-[13px] font-semibold text-tinta-3">
          Três contas de preço justo para {linhas.length} papéis
          {pregao && <>, com o fechamento de {data(pregao)}</>}. {comConta} têm pelo menos uma
          conta calculada.
        </p>
      </section>

      <section className="cartao flex flex-col gap-2 p-5 text-[13px] font-semibold leading-relaxed text-tinta-2">
        <p>
          <strong className="font-extrabold text-tinta">Graham</strong>: raiz de 22,5 × lucro por
          ação × valor patrimonial por ação.{" "}
          <strong className="font-extrabold text-tinta">Bazin</strong>: provento médio dos últimos{" "}
          {ANOS_DE_PROVENTOS} anos dividido por 6%.{" "}
          <strong className="font-extrabold text-tinta">Fluxo de caixa</strong>: o lucro por ação
          crescendo por {ANOS_PROJETADOS} anos no ritmo da própria empresa (entre 0% e 15% ao
          ano), depois {pct(CRESCIMENTO_PERPETUO)} ao ano, trazido a valor de hoje com{" "}
          {pct(desconto, 1)} ao ano ({juro === null ? "juro de reserva" : "Tesouro prefixado de 10 anos"}{" "}
          mais {pct(PREMIO_DE_RISCO)}).
        </p>
        <p>
          O ponto é verde quando o preço está mais de 10% abaixo do resultado da conta, vermelho
          quando está mais de 10% acima e amarelo no meio. São contas sobre o último balanço
          publicado: não levam em conta o setor, a dívida, o momento da empresa nem nada que não
          esteja no número. Não é recomendação. Na ficha de cada papel dá para ver a conta aberta
          e mudar as premissas do fluxo de caixa.
        </p>
      </section>

      <section className="cartao p-4 md:p-5">
        <TabelaDeValuation linhas={linhas} />
      </section>
    </div>
  );
}
