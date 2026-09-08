"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  dinheiro,
  leituraDoTicket,
  multiplo,
  numero,
  percentual,
  proporcao,
  reais,
} from "@/lib/formato";
import type { Evento } from "@/lib/types";

/**
 * Lista do pregao com filtro de z.
 *
 * O filtro muda so o que a tela mostra. O alerta do Telegram continua saindo
 * pelo `alert.threshold` do config.yaml -- por isso a marca de "notificado"
 * fica no evento, e nao depende de onde o controle esta.
 */

type Props = {
  eventos: Evento[];
  /** Limiar do config.yaml, so para marcar onde o Telegram corta. */
  limiarDoAlerta: number;
  minimo: number;
};

export function ListaDeEventos({ eventos, limiarDoAlerta, minimo }: Props) {
  /**
   * Abre no limiar do alerta -- e o que o Telegram mandou, e o que interessa
   * primeiro. Em pregao calmo isso da lista vazia, entao o corte comeca no piso
   * do site e a tela diz por que.
   */
  const houveAlerta = eventos.some((e) => e.zLog >= limiarDoAlerta);
  const [corte, setCorte] = useState(houveAlerta ? limiarDoAlerta : minimo);

  const visiveis = useMemo(
    () => eventos.filter((e) => e.zLog >= corte),
    [eventos, corte],
  );

  const maiorRvol = useMemo(
    () => Math.max(1, ...eventos.map((e) => e.rvol ?? 0)),
    [eventos],
  );

  return (
    <>
      <div className="flex flex-col gap-4 px-4 py-4 md:flex-row md:items-center md:gap-6 md:px-6">
        <div className="w-full md:max-w-[520px]">
          <div className="mb-2 flex items-baseline justify-between">
            <span className="rotulo">Mostrar a partir de</span>
            <span className="num text-[13px] font-semibold text-ambar">
              {numero(corte, 1)} σ
            </span>
          </div>
          <input
            type="range"
            min={minimo}
            max={8}
            step={0.1}
            value={corte}
            onChange={(e) => setCorte(Number(e.target.value))}
            aria-label="Limiar de z-score exibido"
            className="h-6 w-full cursor-pointer bg-transparent"
          />
          <div className="mt-0.5 flex justify-between">
            <span className="num text-[10px] text-tinta-3">{numero(minimo, 0)}σ</span>
            <span className="num text-[10px] text-tinta-3">
              alerta em {numero(limiarDoAlerta, 0)}σ
            </span>
            <span className="num text-[10px] text-tinta-3">8σ</span>
          </div>
        </div>

        <div className="flex items-center gap-2.5 rounded-md border border-linha bg-painel px-3 py-2">
          <span className="num text-[19px] font-semibold">{visiveis.length}</span>
          <span className="text-[11px] leading-tight text-tinta-2">
            eventos
            <br />
            na tela
          </span>
        </div>

        <p className="max-w-[250px] text-[11px] leading-snug text-tinta-3">
          {houveAlerta ? (
            <>
              O Telegram avisa acima de {numero(limiarDoAlerta, 0)}σ. Este controle muda
              só o que você vê aqui.
            </>
          ) : (
            <>
              Nenhum papel cruzou {numero(limiarDoAlerta, 0)}σ neste pregão, então a lista
              abre no piso. Nada foi notificado.
            </>
          )}
        </p>
      </div>

      {visiveis.length === 0 ? (
        <div className="mx-4 rounded-md border border-dashed border-linha-2 p-8 text-center text-[13px] text-tinta-3 md:mx-6">
          Nenhum papel acima de {numero(corte, 1)}σ neste pregão.
        </div>
      ) : (
        <>
          {/* Desktop: tabela densa */}
          <div className="mx-6 hidden overflow-hidden rounded-md border border-linha bg-painel md:block">
            <div className="grid grid-cols-[96px_74px_96px_82px_86px_108px_120px_1fr] border-b border-linha bg-painel-2 px-3.5 py-2">
              <span className="rotulo">Papel</span>
              <span className="rotulo text-right">z</span>
              <span className="rotulo pl-3">rvol</span>
              <span className="rotulo text-right">Fech.</span>
              <span className="rotulo text-right">Var.</span>
              <span className="rotulo text-right">CLV</span>
              <span className="rotulo text-right">Ticket médio</span>
              <span className="rotulo text-right">Volume</span>
            </div>
            {visiveis.map((e) => (
              <Link
                key={`${e.ticker}-${e.tradeDate}`}
                href={`/papel/${e.ticker}?data=${e.tradeDate}`}
                className="grid grid-cols-[96px_74px_96px_82px_86px_108px_120px_1fr] items-center border-b border-linha px-3.5 py-2.5 transition-colors last:border-b-0 hover:bg-painel-2"
              >
                <span>
                  <span className="block text-[13px] font-semibold">{e.ticker}</span>
                  {e.notificado && (
                    <span className="num text-[10px] text-ambar">notificado</span>
                  )}
                </span>
                <span className="num text-right text-[15px] font-semibold text-ambar">
                  {numero(e.zLog)}
                </span>
                <span className="pl-3">
                  <span className="num mb-1 block text-[12px] text-tinta-2">
                    {multiplo(e.rvol)}
                  </span>
                  <span className="block h-[3px] overflow-hidden rounded-sm bg-linha-2">
                    <span
                      className="block h-full bg-ambar"
                      style={{ width: `${((e.rvol ?? 0) / maiorRvol) * 100}%` }}
                    />
                  </span>
                </span>
                <span className="num text-right text-[13px]">{numero(e.close)}</span>
                <span
                  className={`num text-right text-[13px] font-semibold ${
                    (e.retDay ?? 0) >= 0 ? "text-alta" : "text-baixa"
                  }`}
                >
                  {percentual(e.retDay)}
                </span>
                <span className="flex items-center justify-end gap-2">
                  <span className="block h-1 w-9 overflow-hidden rounded-sm bg-linha-2">
                    <span
                      className="block h-full bg-tinta-2"
                      style={{ width: `${(e.clv ?? 0) * 100}%` }}
                    />
                  </span>
                  <span className="num w-8 text-right text-[11px] text-tinta-2">
                    {proporcao(e.clv)}
                  </span>
                </span>
                <span className="text-right">
                  <span className="num block text-[13px]">{reais(e.avgTicket, 0)}</span>
                  <span className="num block text-[10px] text-tinta-3">
                    z {numero(e.ticketZ, 1)}
                  </span>
                </span>
                <span className="text-right">
                  <span className="num block text-[13px]">
                    {dinheiro(e.volumeFinancial)}
                  </span>
                  <span className="num block text-[10px] text-tinta-3">
                    z líq. {numero(e.zExcess)}
                  </span>
                </span>
              </Link>
            ))}
          </div>

          {/* Celular: cartoes, com ticker, z e variacao em destaque */}
          <div className="flex flex-col gap-2.5 px-4 md:hidden">
            {visiveis.map((e) => {
              const leitura = leituraDoTicket(e.avgTicket, e.ticketZ, e.tradesCount);
              return (
                <Link
                  key={`${e.ticker}-${e.tradeDate}`}
                  href={`/papel/${e.ticker}?data=${e.tradeDate}`}
                  className={`toque rounded-lg border bg-painel p-3.5 ${
                    e.notificado ? "border-l-2 border-l-ambar border-linha" : "border-linha"
                  }`}
                >
                  <div className="flex items-baseline gap-2.5">
                    <span className="text-[17px] font-bold">{e.ticker}</span>
                    <span
                      className={`num text-[15px] font-semibold ${
                        (e.retDay ?? 0) >= 0 ? "text-alta" : "text-baixa"
                      }`}
                    >
                      {percentual(e.retDay)}
                    </span>
                    <span className="flex-1" />
                    <span className="num text-[19px] font-semibold text-ambar">
                      {numero(e.zLog)}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-3.5">
                    <span className="num text-[12px] text-tinta-2">
                      {multiplo(e.rvol)} o normal
                    </span>
                    <span className="num text-[12px] text-tinta-2">
                      {dinheiro(e.volumeFinancial)}
                    </span>
                    <span className="flex-1" />
                    <span className="num text-[11px] text-tinta-3">
                      ticket {numero(e.avgTicket, 0)}
                    </span>
                  </div>
                  {leitura && (
                    <div className="mt-1.5 text-[11px] text-tinta-3">{leitura}</div>
                  )}
                </Link>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
