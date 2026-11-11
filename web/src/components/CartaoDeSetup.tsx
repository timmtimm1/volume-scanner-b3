"use client";

import Link from "next/link";
import { fmtR } from "@/lib/backtest-tela";
import { diaCurto, percentual, reais } from "@/lib/formato";
import {
  alvoDoSetup,
  contraOMercado,
  etiquetasDoSetup,
  linkDaFicha,
  NOME_DO_SETUP,
  resultadoEmR,
  rotuloDoEstado,
  type ContextoDoDiario,
  type Setup,
  stopDoSetup,
} from "@/lib/setups-tela";
import { BotaoEntrei } from "./FormularioEntrei";

function ResultadoEmR({ r }: { r: number | null }) {
  if (r === null) return <span className="text-tinta-3">—</span>;
  return <span className={r >= 0 ? "text-alta" : "text-baixa"}>{fmtR(r)}</span>;
}

/**
 * Um em andamento numa linha: o papel, quando entrou, entrada e stop, o
 * resultado ate agora e as etiquetas. Em lista, nao em cartao: um setup com
 * saida pela MME 9 chega a ter duas dezenas abertas ao mesmo tempo.
 */
export function LinhaEmAndamento({ s, diario }: { s: Setup; diario: ContextoDoDiario }) {
  const alvo = alvoDoSetup(s);
  // Duas linhas: em cima o que se le de relance (papel, quando, R, Entrei);
  // embaixo os precos e as etiquetas. Numa linha so, com o botao, os precos
  // viravam uma coluna de cinco linhas no celular.
  return (
    <li className="flex flex-col gap-1.5 py-2.5">
      <div className="flex items-center gap-3">
        <Link
          href={linkDaFicha(s)}
          className="w-16 text-[14px] font-extrabold transition-colors hover:text-acento"
        >
          {s.ticker}
        </Link>
        <span className="num min-w-0 text-[12px] font-semibold text-tinta-3">
          <span className="font-bold text-tinta-2">{NOME_DO_SETUP[s.categoria]}</span> · entrou{" "}
          {s.confirmadoEm ? diaCurto(s.confirmadoEm) : "—"}
        </span>
        <span className="num ml-auto text-right text-[13px] font-bold">
          <ResultadoEmR r={resultadoEmR(s)} />
        </span>
        <BotaoEntrei s={s} diario={diario} />
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="num text-[12px] font-semibold text-tinta-2">
          entrada {reais(s.entrada)} · stop {reais(stopDoSetup(s))}
          {alvo !== null && <> · alvo {reais(alvo)}</>}
        </span>
        <span className="flex flex-wrap gap-1.5 text-[11px] font-semibold text-tinta-3">
          {etiquetasDoSetup(s).map((e) => (
            <span key={e.texto} className="rounded-md bg-painel px-2 py-0.5 text-tinta-2">
              {e.texto}
            </span>
          ))}
        </span>
      </div>
    </li>
  );
}

/** Um encerrado numa linha: o dia, o papel, como terminou e o resultado. */
export function LinhaDeEncerrado({ s }: { s: Setup }) {
  const contra = contraOMercado(s, 20);
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
      <Link
        href={linkDaFicha(s)}
        className="w-16 text-[14px] font-extrabold transition-colors hover:text-acento"
      >
        {s.ticker}
      </Link>
      <span className="num w-12 text-[12px] font-semibold text-tinta-3">{diaCurto(s.tradeDate)}</span>
      <span className="min-w-0 flex-1 text-[13px] font-semibold text-tinta-2">
        <span className="font-bold">{NOME_DO_SETUP[s.categoria]}</span> ·{" "}
        {rotuloDoEstado(s.estado, s.saidaRegra)}
      </span>
      <span className="num text-right text-[13px] font-bold">
        {s.saidaRegra !== null ? (
          <ResultadoEmR r={resultadoEmR(s)} />
        ) : contra !== null ? (
          <>
            <span className={contra >= 0 ? "text-alta" : "text-baixa"}>{percentual(contra)}</span>
            <span className="text-[11px] font-semibold text-tinta-3"> em 20 pregões, contra o mercado</span>
          </>
        ) : (
          <span className="text-tinta-3">—</span>
        )}
      </span>
    </li>
  );
}
