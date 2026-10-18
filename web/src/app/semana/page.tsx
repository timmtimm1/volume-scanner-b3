import type { Metadata } from "next";
import { ResumoDaSemana, SemanaVazia } from "@/components/ResumoDaSemana";
import { edicoesDaSemana, nomesDosPapeis, resumoDaSemana } from "@/lib/db";
import { periodoDaSemana, tickersDasAcoes } from "@/lib/semana";

/** A edicao mais recente. Mesma tela de `/semana/[sexta]`, sem redirecionar. */

export async function generateMetadata(): Promise<Metadata> {
  const [maisRecente] = await edicoesDaSemana();
  const resumo = maisRecente ? await resumoDaSemana(maisRecente.sexta) : null;
  if (!resumo) return { title: "Resumo da semana · volume-scanner-b3" };
  return {
    title: `Semana de ${periodoDaSemana(resumo.semana.pregoes, resumo.semana.fim)} · volume-scanner-b3`,
  };
}

export default async function Semana() {
  const edicoes = await edicoesDaSemana();
  if (edicoes.length === 0) return <SemanaVazia />;
  const resumo = await resumoDaSemana(edicoes[0].sexta);
  if (!resumo) return <SemanaVazia />;
  const nomes = await nomesDosPapeis(tickersDasAcoes(resumo.acoes));
  return <ResumoDaSemana resumo={resumo} edicoes={edicoes} nomes={nomes} />;
}
