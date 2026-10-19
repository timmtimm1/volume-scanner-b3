import { data as fmtData, numero, proporcao } from "@/lib/formato";
import { compactar } from "@/lib/juros";
import { ehErro, mesDeReferencia, pontosBase, prazoDoTreasury, prazoEmAnos } from "@/lib/semana";
import type {
  BlocoComErro,
  CurvaPrefixada,
  DotPlot,
  IndicadoresBr,
  LinhaDeJuros,
  Treasuries,
} from "@/lib/types";
import { GraficoDeJuros } from "./GraficoDeJuros";
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
/* Juros no Brasil                                                     */
/* ------------------------------------------------------------------ */

function Indicador({
  rotulo,
  valor,
  nota,
  motivo,
}: {
  rotulo: string;
  valor: string;
  nota?: string;
  motivo?: string;
}) {
  return (
    <div title={motivo} className="flex min-w-0 flex-col gap-0.5 rounded-2xl bg-painel-2 px-3.5 py-3">
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
      <Indicador
        rotulo="Selic meta"
        valor={ind.selic_meta === null ? "—" : `${numero(ind.selic_meta, 2)}% a.a.`}
        motivo={ind.erros?.selic_meta}
      />
      <Indicador
        rotulo="IPCA 12 meses"
        valor={taxa(ind.ipca_12m)}
        nota={ind.ipca_referencia ? `ref. ${mesDeReferencia(ind.ipca_referencia)}` : undefined}
        motivo={ind.erros?.ipca_12m}
      />
      <Indicador
        rotulo="CDI no mês"
        valor={ind.cdi_mes === null ? "—" : proporcao(ind.cdi_mes, 2)}
        nota={ind.cdi_data ? `até ${fmtData(ind.cdi_data)}` : undefined}
        motivo={ind.erros?.cdi_mes}
      />
      <Indicador
        rotulo="CDI no ano"
        valor={ind.cdi_ano === null ? "—" : proporcao(ind.cdi_ano, 2)}
        nota={ind.cdi_data ? `até ${fmtData(ind.cdi_data)}` : undefined}
        motivo={ind.erros?.cdi_ano}
      />
    </div>
  );
}

/** Edicao antiga nao tem `fonte`: a curva vinha da ANBIMA. */
const nomeDaFonte = (curva: CurvaPrefixada) => (curva.fonte === "tesouro_direto" ? "Tesouro Direto" : "ANBIMA");

function TabelaDaCurva({ primeira, curva, prefixo }: { primeira: string; curva: CurvaPrefixada; prefixo: string }) {
  return (
    <div>
      <CabecalhoDeTaxas primeira={primeira} />
      <ul>
        {curva.vertices.map((v) => (
          <LinhaDeTaxa
            key={v.anos}
            rotulo={`${prefixo}${prazoEmAnos(v.anos)}`}
            atual={v.taxa}
            anterior={v.taxa_anterior}
            bp={v.variacao_bp}
          />
        ))}
      </ul>
    </div>
  );
}

export function SemanaJuros({
  curva,
  curvaReal,
  indicadores,
  historico,
}: {
  curva: CurvaPrefixada | BlocoComErro;
  curvaReal?: CurvaPrefixada | BlocoComErro;
  indicadores: IndicadoresBr | BlocoComErro;
  /** O historico semanal ate a sexta desta edicao. Vazio: sem grafico. */
  historico: LinhaDeJuros[];
}) {
  if (ehErro(curva) && ehErro(indicadores)) {
    return <Bloco titulo="Juros no Brasil" indisponivel={curva.erro} />;
  }
  const real = curvaReal !== undefined && !ehErro(curvaReal) ? curvaReal : null;
  // So a forma compacta vai ao cliente: as ~3.600 linhas inteiras pesavam 400 KB na pagina.
  const compacto = compactar(historico);
  const primeira = compacto.semanas[0] ?? null;
  return (
    <Bloco
      titulo="Juros no Brasil"
      subtitulo={
        ehErro(curva)
          ? undefined
          : `${nomeDaFonte(curva)} · ${fmtData(curva.data)}${curva.data_anterior ? ` contra ${fmtData(curva.data_anterior)}` : ""}`
      }
    >
      {compacto.semanas.length > 0 && <GraficoDeJuros historico={compacto} />}
      {ehErro(curva) ? (
        <Indisponivel motivo={curva.erro} />
      ) : (
        <>
          <TabelaDaCurva primeira="Prefixado" curva={curva} prefixo="" />
          {real && <TabelaDaCurva primeira="IPCA+" curva={real} prefixo="" />}
        </>
      )}
      <Rotulo>Indicadores</Rotulo>
      <IndicadoresDoBrasil ind={indicadores} />
      <Nota>
        {primeira !== null
          ? `Tesouro Direto (taxa de compra, interpolada nos prazos de 1, 2, 5 e 10 anos) e Selic meta do Banco Central. Um ponto por semana, desde ${fmtData(primeira)}. No Pré 10 anos, quando o prefixado mais longo vence antes de 10 anos (de janeiro dos anos ímpares a fevereiro do seguinte), a reta dos dois mais longos é prolongada. `
          : ""}
        {!ehErro(curva) && curva.fonte !== "tesouro_direto"
          ? "Tabela da semana: curva prefixada da ANBIMA (edição anterior ao Tesouro Direto). "
          : ""}
        Selic, CDI e IPCA do Banco Central. Variação em pontos-base (1 bp = 0,01 ponto percentual).
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
