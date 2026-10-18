import { data as fmtData, diaCurto, numero } from "@/lib/formato";
import { agruparAgenda, diaComSemana, ehErro } from "@/lib/semana";
import type {
  BalancoConfirmado,
  BalancoProvavel,
  BalancosDaSemana,
  BlocoComErro,
  EventoDaAgenda,
  ProximaSemana,
} from "@/lib/types";
import { Bloco, Indisponivel, LinkDoPapel, Nota, Rotulo } from "./SemanaPecas";

function consenso(c: NonNullable<EventoDaAgenda["consenso"]>): string {
  const unidade = c.unidade.startsWith("%") ? "%" : ` ${c.unidade}`;
  return `${c.fonte} ${numero(c.mediana, 2)}${unidade}`;
}

function LinhaDaAgenda({ e }: { e: EventoDaAgenda }) {
  return (
    <li className="grid grid-cols-[42px_34px_minmax(0,1fr)] items-baseline gap-x-2 py-1.5">
      <span className="num text-[13px] font-bold text-tinta-2">{e.hora ?? "—"}</span>
      <span
        title={e.fonte}
        className="rounded bg-selecao px-1 py-px text-center text-[10px] font-bold text-tinta-2"
      >
        {e.pais}
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="text-[14px] font-bold leading-snug">
          {e.evento}
          {e.detalhe && <span className="font-semibold text-tinta-3"> · {e.detalhe}</span>}
        </span>
        {e.consenso && (
          <span className="num text-[12px] font-semibold text-tinta-2">
            consenso: {consenso(e.consenso)}
          </span>
        )}
      </span>
    </li>
  );
}

function Tickers({ tickers }: { tickers: string[] }) {
  return (
    <>
      {tickers.map((t, i) => (
        <span key={t}>
          {i > 0 && ", "}
          <LinkDoPapel ticker={t} />
        </span>
      ))}
    </>
  );
}

function Confirmado({ b }: { b: BalancoConfirmado }) {
  return (
    <li className="border-b border-linha py-2.5 last:border-b-0">
      <p className="text-[13px] font-bold leading-snug">{b.empresa}</p>
      <p className="num mt-0.5 text-[12px] font-semibold text-tinta-3">
        {diaComSemana(b.data)}
        {b.horario && ` · ${b.horario}`}
        {b.trimestre && ` · ${b.trimestre}`}
        {b.tickers.length > 0 && " · "}
        <Tickers tickers={b.tickers} />
      </p>
    </li>
  );
}

function Provavel({ b }: { b: BalancoProvavel }) {
  return (
    <li className="border-b border-linha py-2.5 last:border-b-0">
      <p className="text-[13px] font-bold leading-snug">{b.empresa}</p>
      <p className="num mt-0.5 text-[12px] font-semibold text-tinta-3">
        {b.documento} · entregue em {fmtData(b.entregue_em)}
        {b.tickers.length > 0 && " · "}
        <Tickers tickers={b.tickers} />
      </p>
    </li>
  );
}

function Balancos({ balancos }: { balancos: BalancosDaSemana | BlocoComErro }) {
  if (ehErro(balancos)) return <Indisponivel motivo={balancos.erro} />;
  const { confirmados, provaveis, avisos } = balancos;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col">
        <Rotulo>Confirmados (data anunciada pela empresa)</Rotulo>
        {confirmados.length === 0 ? (
          <p className="py-2 text-[13px] text-tinta-3">Nenhum balanço com data anunciada.</p>
        ) : (
          <ul>
            {confirmados.map((b) => (
              <Confirmado key={`${b.cd_cvm}-${b.data}`} b={b} />
            ))}
          </ul>
        )}
      </div>
      <div className="flex flex-col">
        <Rotulo>Prováveis (entregaram nesta semana no ano passado)</Rotulo>
        <p className="pt-0.5 text-[11px] leading-relaxed text-tinta-3">
          Tendência, não data: a empresa ainda não anunciou.
        </p>
        {provaveis.length === 0 ? (
          <p className="py-2 text-[13px] text-tinta-3">Nenhum.</p>
        ) : (
          <ul>
            {provaveis.map((b) => (
              <Provavel key={b.cd_cvm} b={b} />
            ))}
          </ul>
        )}
      </div>
      {avisos.length > 0 && <Nota>{avisos.join(" · ")}</Nota>}
    </div>
  );
}

export function SemanaQueVem({ proxima }: { proxima: ProximaSemana }) {
  const grupos = agruparAgenda(proxima.agenda);
  return (
    <>
      <Bloco
        titulo="Semana que vem"
        subtitulo={`${diaCurto(proxima.inicio)} a ${fmtData(proxima.fim)} · agenda em horário de Brasília`}
      >
        {proxima.feriados_b3.length > 0 && (
          <div className="rounded-2xl bg-evento-fundo px-4 py-3 text-[13px] font-bold leading-snug text-evento-tinta">
            {proxima.feriados_b3.length === 1 ? "Feriado da B3" : "Feriados da B3"}:{" "}
            {proxima.feriados_b3.map((d) => diaComSemana(d)).join(", ")}. Sem pregão.
          </div>
        )}
        {grupos.length === 0 ? (
          <p className="text-[13px] text-tinta-3">Nenhum evento na agenda.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {grupos.map((g) => (
              <div key={g.data} className="flex flex-col border-b border-linha pb-2 last:border-b-0">
                <h3 className="rotulo">{diaComSemana(g.data)}</h3>
                <ul>
                  {g.eventos.map((e) => (
                    <LinhaDaAgenda key={`${e.data}-${e.hora}-${e.pais}-${e.evento}`} e={e} />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
        {proxima.agenda_avisos.length > 0 && (
          <ul className="flex flex-col gap-1">
            {proxima.agenda_avisos.map((a) => (
              <li key={a} className="text-[11px] leading-relaxed text-tinta-3">
                {a}
              </li>
            ))}
          </ul>
        )}
      </Bloco>
      <Bloco titulo="Balanços" subtitulo="Resultados do trimestre">
        <Balancos balancos={proxima.balancos} />
      </Bloco>
    </>
  );
}
