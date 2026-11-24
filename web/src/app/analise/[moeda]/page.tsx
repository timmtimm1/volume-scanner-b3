import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ehDono } from "@/auth";
import { GraficoDoBetaMovel } from "@/components/GraficoDoBetaMovel";
import { MapaMensalDaAnalise } from "@/components/MapaMensalDaAnalise";
import { pctCurto } from "@/lib/analise";
import { lerMoeda } from "@/lib/analise-dados";
import { semCripto } from "@/lib/cripto";
import { data, numero } from "@/lib/formato";

/**
 * Uma moeda contra o Bitcoin: ano a ano, mes a mes e a janela de 90 dias. So
 * para quem esta logado; sem sessao volta para a lista, que pede o login.
 */
export const dynamic = "force-dynamic";

type Props = { params: Promise<{ moeda: string }> };

const corDe = (v: number | null | undefined) =>
  v === null || v === undefined ? "text-tinta" : v > 0 ? "text-alta" : v < 0 ? "text-baixa" : "text-tinta";

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

/** Ticker da Binance: 1 a 20 caracteres, sem barra (ha moedas com nome chines). So ASCII vai para maiuscula. */
function tickerDoEndereco(bruto: string): string | null {
  let t: string;
  try {
    t = decodeURIComponent(bruto);
  } catch {
    return null;
  }
  if (t.length < 1 || t.length > 20 || t.includes("/")) return null;
  return /^[\x20-\x7e]+$/.test(t) ? t.toUpperCase() : t;
}

export default async function AnaliseDaMoeda({ params }: Props) {
  if (!(await ehDono())) redirect("/analise");

  const ticker = tickerDoEndereco((await params).moeda);
  if (ticker === null) notFound();

  let dados: Awaited<ReturnType<typeof lerMoeda>>;
  try {
    dados = await lerMoeda(ticker);
  } catch (erro) {
    if (!semCripto(erro)) throw erro;
    return (
      <section className="cartao p-5 text-[14px] font-semibold text-tinta-2">
        Ainda não há dado de cripto neste banco.
      </section>
    );
  }
  if (dados === null) notFound();

  const { moeda: m, anuais, mensais, movel } = dados;
  const total = anuais.find((a) => a.ano === 0) ?? null;
  const porAno = anuais.filter((a) => a.ano !== 0).sort((a, b) => b.ano - a.ano);
  const ultimo90 = movel.at(-1) ?? null;
  const eBtc = m.moeda === "BTC";
  const temKraken = m.fonte.includes("kraken");
  const soKraken = m.fonte === "kraken";
  const parciais = porAno.filter((a) => a.parcial);

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-col gap-2 px-5 py-4">
        <Link href="/analise" className="toque inline-flex w-fit items-center text-[13px] font-bold text-acento">
          ← Análise
        </Link>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className="text-[22px] font-extrabold tracking-tight">{m.moeda}</h1>
          {m.negociando ? (
            <span className="rounded-full bg-alta-fundo px-2.5 py-0.5 text-[12px] font-extrabold text-alta">
              negociando
            </span>
          ) : (
            <span className="rounded-full bg-painel-2 px-2.5 py-0.5 text-[12px] font-extrabold text-tinta-3">
              parada desde {data(m.ultimoDia)}
            </span>
          )}
          <div className="flex-1" />
          {m.noTop && (
            <Link
              href={`/cripto/?moeda=${encodeURIComponent(m.moeda)}`}
              className="toque inline-flex h-10 items-center rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
            >
              Abrir o gráfico
            </Link>
          )}
        </div>
        <p className="text-[13px] font-semibold text-tinta-3">
          {soKraken
            ? `Preços da Kraken desde ${data(m.primeiroDia)}`
            : `Na Binance desde ${data(m.primeiroDia)}`}
          {temKraken && !soKraken && " · depois de 2024 os preços vêm da Kraken"}
          {eBtc && " · o Bitcoin é a régua: contra ele mesmo, o resultado é sempre zero"}
        </p>
      </section>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Numero
          rotulo="Contra o BTC no período todo"
          texto={eBtc ? "—" : pctCurto(total?.relativo)}
          detalhe={total ? `${data(total.inicio)} a ${data(total.fim)}` : undefined}
          cor={eBtc ? "text-tinta" : corDe(total?.relativo)}
        />
        <Numero rotulo="Beta" texto={numero(total?.beta, 2)} detalhe="no período todo" />
        <Numero rotulo="Correlação" texto={numero(total?.correlacao, 2)} detalhe="no período todo" />
        {/* Beta em cima e correlacao embaixo: as duas numa linha so cortavam a 390px. */}
        <Numero
          rotulo="Últimos 90 dias"
          texto={ultimo90 ? `beta ${numero(ultimo90.beta, 2)}` : "—"}
          detalhe={
            ultimo90
              ? `correlação ${numero(ultimo90.correlacao, 2)} · até ${data(ultimo90.dia)}`
              : undefined
          }
        />
      </div>

      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <h2 className="text-[18px] font-extrabold">Ano a ano</h2>
        {porAno.length === 0 ? (
          <p className="text-[13px] font-semibold text-tinta-3">Sem anos para mostrar.</p>
        ) : (
          <div className="-mx-4 overflow-x-auto md:-mx-5">
            <table className="num w-full border-collapse text-right text-[12px] font-semibold md:text-[13px]">
              <thead className="text-tinta-3">
                <tr className="border-b border-linha">
                  <th scope="col" className="px-3 py-1.5 text-left font-bold md:px-4">
                    Ano
                  </th>
                  <th scope="col" className="px-2 py-1.5 font-bold">
                    A moeda
                  </th>
                  <th scope="col" className="px-2 py-1.5 font-bold">
                    O BTC
                  </th>
                  <th scope="col" className="px-2 py-1.5 font-bold">
                    Contra o BTC
                  </th>
                  <th scope="col" className="px-2 py-1.5 font-bold">
                    Beta
                  </th>
                  <th scope="col" className="px-3 py-1.5 font-bold md:px-4">
                    Correlação
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-linha">
                {porAno.map((a) => (
                  <tr key={a.ano} className={a.parcial ? "italic" : undefined}>
                    <th scope="row" className="px-3 py-1.5 text-left font-extrabold md:px-4">
                      {a.ano}
                      {a.parcial && "*"}
                    </th>
                    <td className="px-2 py-1.5">{pctCurto(a.retorno)}</td>
                    <td className="px-2 py-1.5">{pctCurto(a.retornoBtc)}</td>
                    <td className={`px-2 py-1.5 font-bold ${eBtc ? "" : corDe(a.relativo)}`}>
                      {pctCurto(a.relativo)}
                    </td>
                    <td className="px-2 py-1.5">{numero(a.beta, 2)}</td>
                    <td className="px-3 py-1.5 md:px-4">{numero(a.correlacao, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {parciais.length > 0 && (
          <p className="text-[12px] font-semibold leading-relaxed text-tinta-3">
            * Período incompleto:{" "}
            {parciais.map((a) => `${a.ano} (de ${data(a.inicio)} a ${data(a.fim)})`).join(", ")}.
          </p>
        )}
      </section>

      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <h2 className="text-[18px] font-extrabold">Mês a mês</h2>
        <MapaMensalDaAnalise moeda={m.moeda} mensais={mensais} anuais={anuais} />
      </section>

      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <h2 className="text-[18px] font-extrabold">Beta e correlação nos últimos 90 dias</h2>
        <GraficoDoBetaMovel pontos={movel} />
        <p className="text-[12px] font-semibold leading-relaxed text-tinta-3">
          Cada ponto usa os 90 dias anteriores; um ponto por semana.
        </p>
      </section>
    </div>
  );
}
