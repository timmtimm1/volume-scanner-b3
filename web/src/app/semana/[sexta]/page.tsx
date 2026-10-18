import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ResumoDaSemana } from "@/components/ResumoDaSemana";
import { edicoesDaSemana, jurosHistorico, nomesDosPapeis, resumoDaSemana } from "@/lib/db";
import { periodoDaSemana, sextaValida, tickersDasAcoes } from "@/lib/semana";

/** Uma pagina estatica por edicao gravada. */
export async function generateStaticParams() {
  const edicoes = await edicoesDaSemana();
  return edicoes.map((e) => ({ sexta: e.sexta }));
}

/**
 * Edicao fora da lista do build tambem ganha pagina, gerada no primeiro acesso.
 *
 * O Telegram manda o link logo depois do envio e o rebuild da Vercel leva
 * alguns minutos; com `dynamicParams = false` o link dava 404. Data fora do
 * formato AAAA-MM-DD, ou sem edicao gravada, continua 404.
 */
export const dynamicParams = true;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ sexta: string }>;
}): Promise<Metadata> {
  const { sexta } = await params;
  if (!sextaValida(sexta)) return { title: "Resumo da semana · volume-scanner-b3" };
  const resumo = await resumoDaSemana(sexta);
  if (!resumo) return { title: "Resumo da semana · volume-scanner-b3" };
  return {
    title: `Semana de ${periodoDaSemana(resumo.semana.pregoes, resumo.semana.fim)} · volume-scanner-b3`,
  };
}

export default async function EdicaoDaSemana({
  params,
}: {
  params: Promise<{ sexta: string }>;
}) {
  const { sexta } = await params;
  if (!sextaValida(sexta)) notFound();

  const [resumo, edicoes] = await Promise.all([resumoDaSemana(sexta), edicoesDaSemana()]);
  if (!resumo) notFound();
  const [nomes, juros] = await Promise.all([
    nomesDosPapeis(tickersDasAcoes(resumo.acoes)),
    jurosHistorico(resumo.semana.sexta),
  ]);
  return <ResumoDaSemana resumo={resumo} edicoes={edicoes} nomes={nomes} juros={juros} />;
}
