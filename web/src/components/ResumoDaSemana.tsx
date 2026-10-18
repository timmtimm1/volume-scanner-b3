import Link from "next/link";
import { data as fmtData } from "@/lib/formato";
import {
  diaComSemana,
  instanteEmBrasilia,
  periodoDaSemana,
  vizinhas,
} from "@/lib/semana";
import type { EdicaoDaSemana, LinhaDeJuros, ResumoDaSemana as Resumo } from "@/lib/types";
import { SemanaAcoes } from "./SemanaAcoes";
import { SemanaQueVem } from "./SemanaAgenda";
import { SemanaEua, SemanaJuros } from "./SemanaJuros";
import { SemanaAbertura, SemanaCripto, SemanaNoticias } from "./SemanaMercado";

/** `sex 16/10/2026`: como a edicao aparece na lista. */
const rotuloDaEdicao = (sexta: string) => `${diaComSemana(sexta)}/${sexta.slice(0, 4)}`;

const BOTAO_DA_SETA =
  "flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-linha-2 text-tinta-2";

function Seta({
  sentido,
  destino,
}: {
  sentido: "anterior" | "seguinte";
  destino: string | null;
}) {
  const rotulo = sentido === "anterior" ? "Edição anterior" : "Edição seguinte";
  const icone = (
    <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d={sentido === "anterior" ? "M12 4l-6 6 6 6" : "M8 4l6 6-6 6"} />
    </svg>
  );
  if (!destino) {
    return (
      <span aria-disabled="true" aria-label={`${rotulo} (não há)`} className={`${BOTAO_DA_SETA} opacity-35`}>
        {icone}
      </span>
    );
  }
  return (
    <Link
      href={`/semana/${destino}`}
      aria-label={`${rotulo}: semana até ${fmtData(destino)}`}
      title={`Semana até ${fmtData(destino)}`}
      className={`${BOTAO_DA_SETA} transition-colors hover:border-acento hover:text-acento`}
    >
      {icone}
    </Link>
  );
}

/** Navegacao entre edicoes: setas e uma lista (`details`, sem JavaScript). */
function Edicoes({ edicoes, sexta }: { edicoes: EdicaoDaSemana[]; sexta: string }) {
  const { anterior, seguinte } = vizinhas(edicoes, sexta);
  return (
    <nav aria-label="Edições do resumo" className="flex items-center gap-2">
      <Seta sentido="anterior" destino={anterior} />
      <details className="group relative min-w-0 flex-1">
        <summary className="flex h-11 cursor-pointer list-none items-center justify-between gap-2 rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:border-acento hover:text-acento [&::-webkit-details-marker]:hidden">
          <span className="num truncate">{rotuloDaEdicao(sexta)}</span>
          <span aria-hidden className="text-[11px] transition-transform group-open:rotate-180">
            ▾
          </span>
        </summary>
        <ul className="cartao absolute inset-x-0 top-full z-20 mt-2 max-h-80 overflow-y-auto p-1.5 shadow-[var(--sombra)]">
          {edicoes.map((e) => (
            <li key={e.sexta}>
              <Link
                href={`/semana/${e.sexta}`}
                aria-current={e.sexta === sexta ? "page" : undefined}
                className={`num flex min-h-11 items-center rounded-xl px-3 text-[13px] font-semibold ${
                  e.sexta === sexta
                    ? "bg-selecao text-acento"
                    : "text-tinta-2 hover:bg-painel-2 hover:text-tinta"
                }`}
              >
                Semana até {rotuloDaEdicao(e.sexta)}
              </Link>
            </li>
          ))}
        </ul>
      </details>
      <Seta sentido="seguinte" destino={seguinte} />
    </nav>
  );
}

export function ResumoDaSemana({
  resumo,
  edicoes,
  nomes,
  juros,
}: {
  resumo: Resumo;
  edicoes: EdicaoDaSemana[];
  nomes: Record<string, string>;
  /** O historico de juros ate a sexta desta edicao. */
  juros: LinhaDeJuros[];
}) {
  const { semana } = resumo;
  return (
    <div className="flex flex-col gap-4">
      <header className="cartao relative z-10 flex flex-col gap-3 p-4 md:p-5">
        <div className="flex flex-col gap-0.5">
          <h1 className="text-[22px] font-extrabold tracking-tight">Resumo da semana</h1>
          <p className="num text-[13px] font-semibold text-tinta-3">
            <span className="text-tinta-2">{periodoDaSemana(semana.pregoes, semana.fim)}</span>
            {" · "}gerado em {instanteEmBrasilia(resumo.gerado_em)}
          </p>
        </div>
        <div className="md:max-w-md">
          <Edicoes edicoes={edicoes} sexta={semana.sexta} />
        </div>
      </header>

      <SemanaAbertura abertura={resumo.abertura} />
      <SemanaAcoes acoes={resumo.acoes} nomes={nomes} />

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <SemanaNoticias noticias={resumo.noticias} />
        <SemanaCripto cripto={resumo.cripto} />
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <SemanaJuros
          curva={resumo.juros_br.curva}
          curvaReal={resumo.juros_br.curva_real}
          indicadores={resumo.juros_br.indicadores}
          historico={juros}
        />
        <SemanaEua treasuries={resumo.eua.treasuries} fed={resumo.eua.fed} />
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <SemanaQueVem proxima={resumo.proxima_semana} />
      </div>
    </div>
  );
}

/** `/semana` sem nenhuma edicao gravada. */
export function SemanaVazia() {
  return (
    <section className="cartao flex flex-col gap-1 p-6">
      <h1 className="text-[22px] font-extrabold tracking-tight">Resumo da semana</h1>
      <p className="text-[14px] font-semibold text-tinta-3">
        O primeiro resumo sai no sábado, às 08:30.
      </p>
    </section>
  );
}
