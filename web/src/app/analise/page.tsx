import { ehDono, signIn } from "@/auth";
import { SecaoRecolhida } from "@/components/SecaoRecolhida";
import Link from "next/link";
import { EstudoSazonal } from "@/components/EstudoSazonal";
import { RankingsDaAnalise } from "@/components/RankingsDaAnalise";
import { SazonalidadeDaAnalise } from "@/components/SazonalidadeDaAnalise";
import { SobreAsCommodities } from "@/components/SobreAsCommodities";
import { TabelaDaAnalise } from "@/components/TabelaDaAnalise";
import { lerEstudoSazonal, lerRanking, lerSazonalidade, lerVisaoGeral } from "@/lib/analise-dados";
import { celulaSazonal, montarSazonalidade, montarTabela, type CelulaSazonal } from "@/lib/analise";
import { grupoDaUrl, hrefDaAnalise, type Grupo } from "@/lib/commodities";
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

type Aba = "ano" | "sazonalidade" | "rankings";

const ABAS: { valor: Aba; nome: string; resumo: Record<Grupo, string> }[] = [
  {
    valor: "ano",
    nome: "Por ano",
    resumo: {
      cripto: "Cada cripto contra o Bitcoin, ano a ano",
      commodity: "Ouro tokenizado e contratos de commodity contra o Bitcoin, ano a ano",
    },
  },
  {
    valor: "sazonalidade",
    nome: "Sazonalidade",
    resumo: {
      cripto: "Como cada moeda costuma se sair em cada mês do ano",
      commodity: "Como cada commodity costuma se sair em cada mês do ano",
    },
  },
  {
    valor: "rankings",
    nome: "Rankings",
    resumo: {
      cripto: "Quem mais acompanha, e quem menos acompanha, o Bitcoin",
      commodity: "Quais commodities mais e menos acompanham o Bitcoin",
    },
  },
];

const GRUPOS: { valor: Grupo; nome: string }[] = [
  { valor: "cripto", nome: "Criptos" },
  { valor: "commodity", nome: "Commodities" },
];

const abaDe = (v: string | string[] | undefined): Aba =>
  v === "sazonalidade" || v === "rankings" ? v : "ano";

export default async function Analise({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
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

  const parametros = await searchParams;
  const aba = abaDe(parametros.aba);
  const grupo = grupoDaUrl(parametros.grupo);
  const commodities = grupo === "commodity";
  const info = ABAS.find((x) => x.valor === aba) ?? ABAS[0];

  // O JSX so e montado depois do try: erro de renderizacao nao passa por ele.
  type Dados =
    | {
        aba: "sazonalidade";
        ate: string | null;
        v: Awaited<ReturnType<typeof lerSazonalidade>>;
        estudo: Awaited<ReturnType<typeof lerEstudoSazonal>> | null;
      }
    | { aba: "rankings"; ate: string | null; v: Awaited<ReturnType<typeof lerRanking>> }
    | { aba: "ano"; ate: string | null; v: Awaited<ReturnType<typeof lerVisaoGeral>> };
  let dados: Dados;
  try {
    if (aba === "sazonalidade") {
      // Sem as tabelas do estudo (42P01) a aba abre mesmo assim, com o aviso.
      const [v, estudo] = await Promise.all([
        lerSazonalidade(grupo),
        // O estudo é da cesta de cripto: as commodities não entram nele.
        commodities
          ? Promise.resolve(null)
          : lerEstudoSazonal().catch((erro: unknown) => {
            if ((erro as { code?: string }).code === "42P01") return null;
            throw erro;
          }),
      ]);
      dados = { aba, ate: v.ate, v, estudo };
    } else if (aba === "rankings") {
      const v = await lerRanking(grupo);
      dados = { aba, ate: v.ate, v };
    } else {
      const v = await lerVisaoGeral(grupo);
      dados = { aba: "ano", ate: v.ate, v };
    }
  } catch (erro) {
    if (!semCripto(erro)) throw erro;
    return (
      <section className="cartao p-5 text-[14px] font-semibold text-tinta-2">
        Ainda não há dado de cripto neste banco.
      </section>
    );
  }
  const { ate } = dados;

  if (ate === null) {
    return (
      <section className="cartao p-5 text-[14px] font-semibold leading-relaxed text-tinta-2">
        A análise ainda não foi calculada. Ela roda toda noite depois da carga de cripto (workflow
        cripto analise).
      </section>
    );
  }

  const mercadoPorMes: Record<number, CelulaSazonal> = {};
  if (dados.aba === "sazonalidade" && !commodities) {
    for (const m of dados.v.mercado) mercadoPorMes[m.mes] = celulaSazonal(m);
  }
  const tabela = dados.aba === "ano" ? montarTabela(dados.v.moedas, dados.v.anuais) : null;
  const totalFora = dados.aba === "ano" ? dados.v.fora.reduce((soma, f) => soma + f.n, 0) : 0;

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-col gap-0.5 px-5 py-3">
        <h1 className="text-[22px] font-extrabold tracking-tight">Análise</h1>
        <p className="text-[13px] font-semibold text-tinta-3">
          {info.resumo[grupo]} · dados até {data(ate)}
        </p>
      </section>

      <nav aria-label="Abas da análise" className="flex flex-wrap gap-1.5">
        {ABAS.map((x) => (
          <Link
            key={x.valor}
            href={hrefDaAnalise(x.valor, grupo)}
            aria-current={x.valor === aba ? "page" : undefined}
            className={`toque flex h-9 items-center rounded-full border px-3.5 text-[13px] font-bold transition-colors ${
              x.valor === aba
                ? "border-acento bg-selecao text-acento"
                : "border-linha-2 text-tinta-3 hover:text-tinta"
            }`}
          >
            {x.nome}
          </Link>
        ))}
      </nav>

      <nav aria-label="Grupo da análise" className="flex flex-wrap gap-1.5">
        {GRUPOS.map((g) => (
          <Link
            key={g.valor}
            href={hrefDaAnalise(aba, g.valor)}
            aria-current={g.valor === grupo ? "page" : undefined}
            className={`toque flex h-8 items-center rounded-full border px-3 text-[12px] font-bold transition-colors ${
              g.valor === grupo
                ? "border-acento bg-selecao text-acento"
                : "border-linha-2 text-tinta-3 hover:text-tinta"
            }`}
          >
            {g.nome}
          </Link>
        ))}
      </nav>

      {dados.aba === "sazonalidade" && (
        <>
          {commodities ? (
            <section className="cartao p-4 text-[13px] leading-relaxed text-tinta-2 md:p-5">
              O estudo de quando comprar e quando vender é da cesta das 50 criptos mais negociadas; as
              commodities não entram nele. Para ver, volte para{" "}
              <Link href={hrefDaAnalise("sazonalidade", "cripto")} className="font-bold text-acento">
                Criptos
              </Link>
              .
            </section>
          ) : (
            <EstudoSazonal estudo={dados.estudo} />
          )}
          <SazonalidadeDaAnalise
            linhas={montarSazonalidade(dados.v.moedas, dados.v.meses)}
            mercado={mercadoPorMes}
            commodities={commodities}
          />
        </>
      )}
      {dados.aba === "rankings" && (
        <RankingsDaAnalise
          candidatos={dados.v.candidatos}
          ano={dados.v.ano}
          dia90={dados.v.dia90}
          total={dados.v.candidatos.length}
          commodities={commodities}
        />
      )}
      {dados.aba === "ano" && (
        <>
          {commodities && <SobreAsCommodities />}
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
              {commodities ? (
                <p>
                  As commodities ficam fora da cesta das 50 criptos do estudo de compra e venda e da
                  moeda típica da Sazonalidade. Os contratos têm menos de um ano de histórico.
                </p>
              ) : (
                <p>
                  <b className="text-tinta">O que ficou de fora.</b>{" "}
                  {totalFora > 0
                    ? `${totalFora} moedas que não são cripto "de verdade" para esta conta: ${listaDoQueFicouFora(dados.v.fora)}. `
                    : "Nada ficou de fora. "}
                  As moedas que saíram da Binance continuam na lista, marcadas como &quot;parada&quot;:
                  tirar as que deram errado faria o passado parecer melhor do que foi.
                </p>
              )}
            </div>
          </SecaoRecolhida>

          {tabela && <TabelaDaAnalise anos={tabela.anos} linhas={tabela.linhas} commodities={commodities} />}
        </>
      )}
    </div>
  );
}
