import { notFound, redirect } from "next/navigation";
import { ehDono } from "@/auth";
import { FichaDaMoeda } from "@/components/FichaDaMoeda";
import { MOEDA, moedas, semCripto } from "@/lib/cripto";
import { comCandleDeHoje } from "@/lib/cripto-hoje";
import { diaDeHoje } from "@/lib/cripto-hoje-binance";
import { niveisDoPapel, papel } from "@/lib/db";
import { noMercado } from "@/lib/mercado-servidor";
import { listarSetups } from "@/lib/setups";

/** A ficha de uma moeda. So para quem esta logado, como a aba Cripto. */
export const dynamic = "force-dynamic";

/** Dias de grafico: o banco guarda 400; a ficha do papel mostra 180. */
const DIAS = 260;

type Props = {
  params: Promise<{ moeda: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function Moeda({ params, searchParams }: Props) {
  if (!(await ehDono())) redirect("/cripto");
  const { moeda } = await params;
  const ticker = decodeURIComponent(moeda).toUpperCase();
  if (!MOEDA.test(ticker)) notFound();
  const foco = (await searchParams).foco;

  let dados;
  try {
    dados = await noMercado("cripto", async () => {
      const [ficha, nomes, setups] = await Promise.all([
        papel(ticker, DIAS),
        moedas(),
        listarSetups(ticker),
      ]);
      if (ficha.barras.length === 0) return null;
      const niveis = await niveisDoPapel(ticker, ficha.barras[0].tradeDate);
      return { ficha, nome: nomes[ticker] ?? null, setups, niveis };
    });
  } catch (erro) {
    if (!semCripto(erro)) throw erro;
    dados = null;
  }
  if (dados === null) notFound();

  const desde = dados.ficha.barras[0].tradeDate;
  // O candle de hoje, em andamento, direto da Binance a cada abertura.
  const agora = (await diaDeHoje([ticker]))[ticker];
  const barras = comCandleDeHoje(dados.ficha.barras, agora);
  const aoVivo = barras.length > dados.ficha.barras.length && agora ? agora.hora : null;
  return (
    <FichaDaMoeda
      ticker={ticker}
      nome={dados.nome?.nome ?? null}
      posicao={dados.nome?.posicao ?? null}
      barras={barras}
      aoVivo={aoVivo}
      eventos={dados.ficha.eventos.map((e) => ({ tradeDate: e.tradeDate }))}
      niveis={dados.niveis}
      setups={dados.setups.filter((s) => s.tradeDate >= desde)}
      foco={typeof foco === "string" && /^\d{4}-\d{2}-\d{2}$/.test(foco) ? foco : null}
    />
  );
}
