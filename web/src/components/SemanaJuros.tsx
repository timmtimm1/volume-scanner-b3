import { data as fmtData, diaCurto, numero, proporcao } from "@/lib/formato";
import {
  ehErro,
  mesDeReferencia,
  pontosBase,
  prazoDoTreasury,
  prazoEmAnos,
} from "@/lib/semana";
import type {
  BlocoComErro,
  CurvaPrefixada,
  DotPlot,
  IndicadoresBr,
  Treasuries,
} from "@/lib/types";
import { Bloco, Indisponivel, Nota, Rotulo } from "./SemanaPecas";

/** Taxa em % a.a.: `12,92%`. */
const taxa = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${numero(v, 2)}%`;

/** Linha de tabela de taxas: variacao de TAXA e neutra, nunca verde/vermelha. */
function LinhaDeTaxa({
  rotulo,
  atual,
  anterior,
  bp,
}: {
  rotulo: string;
  atual: number;
  anterior: number | null;
  bp: number | null;
}) {
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_72px_72px_84px] items-baseline gap-x-2 border-b border-linha py-2.5 text-[14px] last:border-b-0">
      <span className="truncate font-bold">{rotulo}</span>
      <span className="num text-right font-extrabold">{taxa(atual)}</span>
      <span className="num text-right font-semibold text-tinta-3">{taxa(anterior)}</span>
      <span className="num text-right text-[13px] font-bold text-tinta-2">{pontosBase(bp)}</span>
    </li>
  );
}

function CabecalhoDeTaxas({ primeira }: { primeira: string }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_72px_72px_84px] gap-x-2 border-b border-linha pb-1.5">
      <span className="rotulo">{primeira}</span>
      <span className="rotulo text-right">Atual</span>
      <span className="rotulo text-right">Anterior</span>
      <span className="rotulo text-right">Variação</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Curva de juros: SVG simples, esta semana contra a anterior          */
/* ------------------------------------------------------------------ */

const L = 360;
const A = 176;
const MARGEM = { e: 40, d: 14, t: 12, b: 28 };

function CurvaDeJuros({ curva }: { curva: CurvaPrefixada }) {
  const vs = curva.vertices;
  if (vs.length < 2) return null;
  const todas = vs.flatMap((v) => [v.taxa, v.taxa_anterior]).filter((x): x is number => x !== null);
  const passo = 0.5;
  const minimo = Math.floor(Math.min(...todas) / passo) * passo - passo;
  const maximo = Math.ceil(Math.max(...todas) / passo) * passo + passo;
  const xMax = Math.max(...vs.map((v) => v.anos));
  const x = (anos: number) => MARGEM.e + (anos / xMax) * (L - MARGEM.e - MARGEM.d);
  const y = (t: number) => MARGEM.t + (1 - (t - minimo) / (maximo - minimo)) * (A - MARGEM.t - MARGEM.b);
  const marcas: number[] = [];
  const intervalo = maximo - minimo > 3 ? 1 : 0.5;
  for (let t = Math.ceil(minimo / intervalo) * intervalo; t <= maximo + 1e-9; t += intervalo) marcas.push(t);

  const caminho = (valores: (number | null)[]) =>
    vs
      .map((v, i) => ({ v, t: valores[i] }))
      .filter((p): p is { v: (typeof vs)[number]; t: number } => p.t !== null)
      .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.v.anos).toFixed(1)} ${y(p.t).toFixed(1)}`)
      .join(" ");

  const temAnterior = vs.some((v) => v.taxa_anterior !== null);

  return (
    <div className="flex flex-col gap-1.5">
      <svg
        viewBox={`0 0 ${L} ${A}`}
        role="img"
        aria-label={`Curva prefixada em ${fmtData(curva.data)} contra ${fmtData(curva.data_anterior)}, vértices de ${vs
          .map((v) => prazoEmAnos(v.anos))
          .join(", ")}`}
        className="h-auto w-full max-w-[440px]"
      >
        {marcas.map((t) => (
          <g key={t}>
            <line x1={MARGEM.e} x2={L - MARGEM.d} y1={y(t)} y2={y(t)} stroke="var(--linha)" strokeWidth={1} />
            <text x={MARGEM.e - 6} y={y(t) + 3.5} textAnchor="end" fontSize={10} fill="var(--tinta-3)" className="num">
              {numero(t, intervalo < 1 ? 1 : 0)}%
            </text>
          </g>
        ))}
        {vs.map((v) => (
          <text key={v.anos} x={x(v.anos)} y={A - 10} textAnchor="middle" fontSize={10} fill="var(--tinta-3)" className="num">
            {numero(v.anos, 0)}a
          </text>
        ))}
        {temAnterior && (
          <path
            d={caminho(vs.map((v) => v.taxa_anterior))}
            fill="none"
            stroke="var(--tinta-3)"
            strokeWidth={1.6}
            strokeDasharray="5 4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        <path
          d={caminho(vs.map((v) => v.taxa))}
          fill="none"
          stroke="var(--acento)"
          strokeWidth={2.2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {vs.map((v) => (
          <circle key={v.anos} cx={x(v.anos)} cy={y(v.taxa)} r={3.5} fill="var(--acento)" stroke="var(--painel)" strokeWidth={1.5} />
        ))}
      </svg>
      <div className="num flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-semibold text-tinta-3">
        <span className="flex items-center gap-1.5">
          <svg width="20" height="6" aria-hidden>
            <line x1="0" x2="20" y1="3" y2="3" stroke="var(--acento)" strokeWidth={2.2} strokeLinecap="round" />
          </svg>
          {diaCurto(curva.data)}
        </span>
        {temAnterior && (
          <span className="flex items-center gap-1.5">
            <svg width="20" height="6" aria-hidden>
              <line x1="0" x2="20" y1="3" y2="3" stroke="var(--tinta-3)" strokeWidth={1.6} strokeDasharray="5 4" strokeLinecap="round" />
            </svg>
            {diaCurto(curva.data_anterior)}
          </span>
        )}
        <span>prazo em anos · taxa % a.a.</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Juros no Brasil                                                     */
/* ------------------------------------------------------------------ */

function Indicador({ rotulo, valor, nota }: { rotulo: string; valor: string; nota?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-2xl bg-painel-2 px-3.5 py-3">
      <span className="truncate text-[11px] font-semibold text-tinta-3">{rotulo}</span>
      <span className="num text-[17px] font-extrabold">{valor}</span>
      {nota && <span className="num text-[11px] text-tinta-3">{nota}</span>}
    </div>
  );
}

function IndicadoresDoBrasil({ ind }: { ind: IndicadoresBr | BlocoComErro }) {
  if (ehErro(ind)) return <Indisponivel motivo={ind.erro} />;
  return (
    <div className="grid grid-cols-2 gap-2.5">
      <Indicador rotulo="Selic meta" valor={ind.selic_meta === null ? "—" : `${numero(ind.selic_meta, 2)}% a.a.`} />
      <Indicador
        rotulo="IPCA 12 meses"
        valor={taxa(ind.ipca_12m)}
        nota={ind.ipca_referencia ? `ref. ${mesDeReferencia(ind.ipca_referencia)}` : undefined}
      />
      <Indicador
        rotulo="CDI no mês"
        valor={ind.cdi_mes === null ? "—" : proporcao(ind.cdi_mes, 2)}
        nota={ind.cdi_data ? `até ${fmtData(ind.cdi_data)}` : undefined}
      />
      <Indicador
        rotulo="CDI no ano"
        valor={ind.cdi_ano === null ? "—" : proporcao(ind.cdi_ano, 2)}
        nota={ind.cdi_data ? `até ${fmtData(ind.cdi_data)}` : undefined}
      />
    </div>
  );
}

export function SemanaJuros({
  curva,
  indicadores,
}: {
  curva: CurvaPrefixada | BlocoComErro;
  indicadores: IndicadoresBr | BlocoComErro;
}) {
  if (ehErro(curva) && ehErro(indicadores)) {
    return <Bloco titulo="Juros no Brasil" indisponivel={curva.erro} />;
  }
  return (
    <Bloco
      titulo="Juros no Brasil"
      subtitulo={ehErro(curva) ? undefined : `Curva prefixada · ${fmtData(curva.data)} contra ${fmtData(curva.data_anterior)}`}
    >
      {ehErro(curva) ? (
        <Indisponivel motivo={curva.erro} />
      ) : (
        <>
          <CurvaDeJuros curva={curva} />
          <div>
            <CabecalhoDeTaxas primeira="Prazo" />
            <ul>
              {curva.vertices.map((v) => (
                <LinhaDeTaxa
                  key={v.anos}
                  rotulo={prazoEmAnos(v.anos)}
                  atual={v.taxa}
                  anterior={v.taxa_anterior}
                  bp={v.variacao_bp}
                />
              ))}
            </ul>
          </div>
        </>
      )}
      <Rotulo>Indicadores</Rotulo>
      <IndicadoresDoBrasil ind={indicadores} />
      <Nota>
        Curva prefixada da ANBIMA; Selic, CDI e IPCA do Banco Central. Variação em pontos-base (1 bp =
        0,01 ponto percentual).
      </Nota>
    </Bloco>
  );
}

/* ------------------------------------------------------------------ */
/* EUA                                                                 */
/* ------------------------------------------------------------------ */

function DotPlotDoFed({ fed }: { fed: DotPlot | BlocoComErro }) {
  if (ehErro(fed)) return <Indisponivel motivo={fed.erro} />;
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-5 gap-1.5">
        {fed.medianas.map((m) => (
          <div key={m.periodo} className="flex min-w-0 flex-col items-center gap-0.5 rounded-2xl bg-painel-2 px-1 py-2.5 text-center">
            <span className="num text-[16px] font-extrabold">{numero(m.taxa, 1)}%</span>
            <span className="num text-[10px] font-semibold leading-tight text-tinta-3">{m.periodo}</span>
          </div>
        ))}
      </div>
      <p className="num text-[11px] text-tinta-3">Mediana das projeções do Fed, de {fmtData(fed.data_projecao)}.</p>
    </div>
  );
}

export function SemanaEua({
  treasuries,
  fed,
}: {
  treasuries: Treasuries | BlocoComErro;
  fed: DotPlot | BlocoComErro;
}) {
  if (ehErro(treasuries) && ehErro(fed)) {
    return <Bloco titulo="EUA" indisponivel={treasuries.erro} />;
  }
  return (
    <Bloco
      titulo="EUA"
      subtitulo={ehErro(treasuries) ? undefined : `Treasuries · ${fmtData(treasuries.data)} contra ${fmtData(treasuries.data_anterior)}`}
    >
      {ehErro(treasuries) ? (
        <Indisponivel motivo={treasuries.erro} />
      ) : (
        <div>
          <CabecalhoDeTaxas primeira="Vencimento" />
          <ul>
            {treasuries.vencimentos.map((v) => (
              <LinhaDeTaxa
                key={v.prazo}
                rotulo={prazoDoTreasury(v.prazo)}
                atual={v.taxa}
                anterior={v.taxa_anterior}
                bp={v.variacao_bp}
              />
            ))}
          </ul>
        </div>
      )}
      <Rotulo>Dot plot do Fed</Rotulo>
      <DotPlotDoFed fed={fed} />
      <Nota>Tesouro dos EUA (CSV diário) e projeções do FOMC. Variação em pontos-base.</Nota>
    </Bloco>
  );
}
