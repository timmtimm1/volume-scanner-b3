"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { data as fmtData, dinheiro, multiplo, numero, percentual, reais } from "@/lib/formato";
import type { Evento } from "@/lib/types";

type Props = {
  eventos: Evento[];
  notificados: number;
  de?: string;
  ate?: string;
  limiarDoAlerta: number;
  minimo: number;
};

/** Serve para revisitar eventos e ir construindo repertorio de padroes. */
export function TabelaDoHistorico({
  eventos,
  notificados,
  de,
  ate,
  limiarDoAlerta,
  minimo,
}: Props) {
  const [corte, setCorte] = useState(minimo);
  const [busca, setBusca] = useState("");
  const [soNotificados, setSoNotificados] = useState(false);

  const visiveis = useMemo(() => {
    const alvo = busca.trim().toUpperCase();
    return eventos.filter(
      (e) =>
        e.zLog >= corte &&
        (!alvo || e.ticker.includes(alvo)) &&
        (!soNotificados || e.notificado),
    );
  }, [eventos, corte, busca, soNotificados]);

  return (
    <>
      <header className="flex flex-wrap items-center gap-4 border-b border-linha bg-painel px-4 py-3.5 md:px-6">
        <div>
          <h1 className="text-[17px] font-bold">Histórico de eventos</h1>
          <p className="num mt-0.5 text-[11px] text-tinta-3">
            {de && ate ? `${fmtData(de)} a ${fmtData(ate)}` : "sem eventos no período"}
          </p>
        </div>
        <div className="flex-1" />
        <div className="flex items-baseline gap-2">
          <span className="num text-[22px] font-semibold text-ambar">{notificados}</span>
          <span className="text-[11px] leading-tight text-tinta-2">
            acima de
            <br />
            {numero(limiarDoAlerta, 0)}σ
          </span>
        </div>
      </header>

      <div className="flex flex-wrap items-end gap-4 border-b border-linha bg-painel-2 px-4 py-3 md:px-6">
        <label className="block">
          <span className="rotulo mb-1.5 block">Papel</span>
          <input
            type="text"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="todos"
            className="toque w-36 rounded border border-linha-2 bg-painel px-2.5 py-1.5 text-[12px] outline-none placeholder:text-tinta-3 focus:border-ambar"
          />
        </label>

        <div className="min-w-[180px] flex-1 md:max-w-[280px]">
          <div className="mb-1.5 flex justify-between">
            <span className="rotulo">z mínimo</span>
            <span className="num text-[11px] font-semibold text-ambar">
              {numero(corte, 1)}σ
            </span>
          </div>
          <input
            type="range"
            min={minimo}
            max={8}
            step={0.1}
            value={corte}
            onChange={(e) => setCorte(Number(e.target.value))}
            aria-label="z mínimo"
            className="h-6 w-full cursor-pointer bg-transparent"
          />
        </div>

        <button
          type="button"
          onClick={() => setSoNotificados((v) => !v)}
          aria-pressed={soNotificados}
          className={`toque self-end rounded border px-3 py-1.5 text-[11px] transition-colors ${
            soNotificados
              ? "border-ambar bg-selecao text-ambar"
              : "border-linha-2 text-tinta-2 hover:text-tinta"
          }`}
        >
          só notificados
        </button>

        <span className="num self-end text-[11px] text-tinta-3">
          {visiveis.length} de {eventos.length}
        </span>
      </div>

      <div className="p-4 md:p-6">
        {visiveis.length === 0 ? (
          <div className="rounded-md border border-dashed border-linha-2 p-8 text-center text-[13px] text-tinta-3">
            Nenhum evento com esses filtros.
          </div>
        ) : (
          <div className="overflow-hidden rounded-md border border-linha bg-painel">
            <div className="hidden grid-cols-[96px_88px_68px_74px_82px_92px_110px_1fr] border-b border-linha bg-painel-2 px-3.5 py-2 md:grid">
              <span className="rotulo">Pregão</span>
              <span className="rotulo">Papel</span>
              <span className="rotulo text-right">z</span>
              <span className="rotulo text-right">rvol</span>
              <span className="rotulo text-right">Var.</span>
              <span className="rotulo text-right">z líquido</span>
              <span className="rotulo text-right">Ticket</span>
              <span className="rotulo text-right">Volume</span>
            </div>

            {visiveis.map((e) => (
              <Link
                key={`${e.ticker}-${e.tradeDate}`}
                href={`/papel/${e.ticker}?data=${e.tradeDate}`}
                className="toque flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-linha px-3.5 py-2.5 transition-colors last:border-b-0 hover:bg-painel-2 md:grid md:grid-cols-[96px_88px_68px_74px_82px_92px_110px_1fr] md:gap-0 md:py-2"
              >
                <span className="num order-2 text-[11px] text-tinta-3 md:order-none md:text-[12px] md:text-tinta-2">
                  {fmtData(e.tradeDate)}
                </span>
                <span className="order-1 text-[14px] font-semibold md:order-none md:text-[13px]">
                  {e.ticker}
                  {e.notificado && (
                    <span className="num ml-1.5 text-[9px] text-ambar md:hidden">●</span>
                  )}
                </span>
                <span
                  className={`num order-1 ml-auto text-right text-[15px] font-semibold md:order-none md:ml-0 md:text-[13px] ${
                    e.notificado ? "text-ambar" : ""
                  }`}
                >
                  {numero(e.zLog)}
                </span>
                <span className="num order-3 text-right text-[11px] text-tinta-2 md:order-none md:text-[12px]">
                  {multiplo(e.rvol)}
                </span>
                <span
                  className={`num order-3 text-right text-[11px] font-semibold md:order-none md:text-[12px] ${
                    (e.retDay ?? 0) >= 0 ? "text-alta" : "text-baixa"
                  }`}
                >
                  {percentual(e.retDay)}
                </span>
                <span className="num order-4 hidden text-right text-[12px] md:order-none md:block">
                  {numero(e.zExcess)}
                </span>
                <span className="num order-4 hidden text-right text-[12px] text-tinta-2 md:order-none md:block">
                  {reais(e.avgTicket, 0)}
                </span>
                <span className="num order-3 ml-auto text-right text-[11px] md:order-none md:ml-0 md:text-[12px]">
                  {dinheiro(e.volumeFinancial)}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
