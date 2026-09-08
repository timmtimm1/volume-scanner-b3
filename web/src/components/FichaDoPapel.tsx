"use client";

import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { Grafico } from "@/components/Grafico";
import { aberturaDaBanda, bollinger } from "@/lib/indicadores";
import {
  data as fmtData,
  dinheiro,
  leituraDaFaixa,
  leituraDoTicket,
  multiplo,
  numero,
  percentual,
  proporcao,
  reais,
} from "@/lib/formato";
import type { Barra, Evento } from "@/lib/types";

type Props = { ticker: string; barras: Barra[]; eventos: Evento[] };

function Metrica({
  rotulo,
  valor,
  nota,
  destaque,
}: {
  rotulo: string;
  valor: string;
  nota?: string;
  destaque?: boolean;
}) {
  return (
    <div className="bg-fundo px-4 py-3">
      <div className="rotulo">{rotulo}</div>
      <div
        className={`num mt-0.5 text-[20px] font-semibold md:text-[22px] ${
          destaque ? "text-ambar" : ""
        }`}
      >
        {valor}
      </div>
      {nota && <div className="num text-[10px] text-tinta-3">{nota}</div>}
    </div>
  );
}

function Linha({
  rotulo,
  valor,
  cor,
  forte,
}: {
  rotulo: string;
  valor: string;
  cor?: string;
  forte?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between border-b border-linha py-2.5 last:border-b-0">
      <span
        className={`text-[12px] ${forte ? "font-semibold text-tinta" : "text-tinta-2"}`}
      >
        {rotulo}
      </span>
      <span
        className={`num text-[13px] ${forte ? "text-[15px] font-semibold" : ""} ${cor ?? ""}`}
      >
        {valor}
      </span>
    </div>
  );
}

export function FichaDoPapel({ ticker, barras, eventos }: Props) {
  const params = useSearchParams();
  const pedido = params.get("data");

  const evento = useMemo(() => {
    if (pedido) {
      const achado = eventos.find((e) => e.tradeDate === pedido);
      if (achado) return achado;
    }
    return eventos[0] ?? null;
  }, [eventos, pedido]);

  const barra = useMemo(
    () => barras.find((b) => b.tradeDate === evento?.tradeDate) ?? null,
    [barras, evento],
  );

  const abertura = useMemo(() => {
    if (!evento) return null;
    const ate = barras.findIndex((b) => b.tradeDate === evento.tradeDate);
    if (ate < 0) return null;
    return aberturaDaBanda(bollinger(barras.slice(0, ate + 1), 20, 2));
  }, [barras, evento]);

  const faixa = leituraDaFaixa(evento?.pos252 ?? null);
  const ticket = leituraDoTicket(
    evento?.avgTicket ?? null,
    evento?.ticketZ ?? null,
    evento?.tradesCount ?? null,
  );
  const janelas = Object.keys(evento?.zByWindow ?? {})
    .map(Number)
    .sort((a, b) => a - b);
  const maiorZ = Math.max(1, ...janelas.map((j) => evento?.zByWindow[j] ?? 0));

  return (
    <>
      <header className="border-b border-linha bg-painel px-4 py-3.5 md:px-6">
        <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-linha-2 bg-selecao">
            <span className="num text-[14px] font-semibold text-ambar">
              {ticker.slice(0, 2)}
            </span>
          </div>
          <div className="min-w-0">
            <h1 className="text-[20px] font-bold tracking-tight md:text-[22px]">
              {ticker}
            </h1>
            <p className="num text-[11px] text-tinta-3">
              {evento ? `Pregão de ${fmtData(evento.tradeDate)}` : "sem evento no período"}
            </p>
          </div>
          <div className="flex-1" />
          {barra && (
            <div className="text-right">
              <div className="flex items-baseline justify-end gap-2.5">
                <span className="num text-[22px] font-semibold md:text-[24px]">
                  {reais(barra.close)}
                </span>
                <span
                  className={`num text-[15px] font-semibold ${
                    (evento?.retDay ?? 0) >= 0 ? "text-alta" : "text-baixa"
                  }`}
                >
                  {percentual(evento?.retDay ?? null)}
                </span>
              </div>
              {evento?.notificado && (
                <span className="num text-[10px] text-ambar">notificado no Telegram</span>
              )}
            </div>
          )}
        </div>
      </header>

      {evento && (
        <div className="grid grid-cols-2 gap-px border-b border-linha bg-linha md:grid-cols-4">
          <Metrica
            rotulo={`z_log · ${janelas[0] ?? 30}d`}
            valor={numero(evento.zLog)}
            nota={janelas
              .slice(1)
              .map((j) => `${j}d ${numero(evento.zByWindow[j])}`)
              .join(" · ")}
            destaque
          />
          <Metrica
            rotulo="Volume relativo"
            valor={multiplo(evento.rvol)}
            nota={`mediana de ${janelas[0] ?? 30} pregões`}
          />
          <Metrica
            rotulo="Financeiro"
            valor={dinheiro(evento.volumeFinancial)}
            nota={
              evento.tradesCount
                ? `${numero(evento.tradesCount, 0)} negócios`
                : undefined
            }
          />
          <Metrica
            rotulo="Ticket médio"
            valor={reais(evento.avgTicket, 0)}
            nota={ticket ?? `z ${numero(evento.ticketZ, 1)}`}
          />
        </div>
      )}

      <div className="p-4 md:p-6">
        <Grafico
          barras={barras}
          eventos={eventos}
          destaque={evento?.tradeDate}
          altura={380}
        />
      </div>

      {evento && (
        <div className="grid gap-4 px-4 pb-6 md:grid-cols-[1fr_320px] md:px-6">
          <div className="flex flex-col gap-3">
            {ticket && (
              <p className="rounded-r-md border border-l-2 border-linha border-l-ambar bg-painel px-3.5 py-3 text-[12px] leading-relaxed">
                Ticket de <strong className="num">{reais(evento.avgTicket, 0)}</strong>
                {evento.tradesCount ? (
                  <>
                    {" "}
                    com{" "}
                    <strong className="num">{numero(evento.tradesCount, 0)}</strong>{" "}
                    negócios
                  </>
                ) : null}
                : {ticket}.
              </p>
            )}
            {abertura !== null && abertura > 1.15 && (
              <p className="rounded-r-md border border-l-2 border-linha border-l-ambar bg-painel px-3.5 py-3 text-[12px] leading-relaxed">
                Banda de Bollinger{" "}
                <strong className="num">{multiplo(abertura)}</strong> mais larga que a
                média recente do papel — volatilidade expandindo junto com o volume.
              </p>
            )}
            {eventos.length > 1 && (
              <p className="rounded-md border border-linha bg-painel px-3.5 py-3 text-[12px] leading-relaxed text-tinta-2">
                Este papel cruzou o limiar{" "}
                <strong className="num text-tinta">{eventos.length}</strong> vezes no
                período mantido. Cada uma aparece no gráfico com o candle e o volume em âmbar — vale ver o que o
                preço fez depois de cada.
              </p>
            )}
          </div>

          <aside>
            <div className="rotulo mb-1">Contexto do evento</div>
            <p className="mb-3 text-[11px] leading-snug text-tinta-3">
              Os números que o alerta manda. A leitura é sua.
            </p>
            <Linha
              rotulo="Variação do dia"
              valor={percentual(evento.retDay)}
              cor={(evento.retDay ?? 0) >= 0 ? "text-alta" : "text-baixa"}
            />
            <Linha
              rotulo="Gap de abertura"
              valor={percentual(evento.gap)}
              cor={(evento.gap ?? 0) >= 0 ? "text-alta" : "text-baixa"}
            />
            <Linha rotulo="Fechou no range" valor={proporcao(evento.clv)} />
            <Linha rotulo="Amplitude do dia" valor={proporcao(evento.rangeNorm, 1)} />
            <Linha
              rotulo="Faixa de 252 pregões"
              valor={
                faixa
                  ? `${proporcao(evento.pos252)} · ${faixa}`
                  : proporcao(evento.pos252)
              }
            />
            <Linha
              rotulo="20 pregões anteriores"
              valor={percentual(evento.retPrior20)}
              cor={(evento.retPrior20 ?? 0) >= 0 ? "text-alta" : "text-baixa"}
            />
            <Linha rotulo="z do ticket" valor={numero(evento.ticketZ, 1)} />
            <Linha rotulo="z do mercado" valor={numero(evento.mktVolZ)} />
            <Linha
              rotulo="z líquido do mercado"
              valor={numero(evento.zExcess)}
              cor="text-ambar"
              forte
            />

            <div className="mt-4 rounded-md border border-linha bg-painel p-3">
              <div className="rotulo mb-2">z por janela</div>
              <div className="flex flex-col gap-2">
                {janelas.map((j) => (
                  <div key={j} className="flex items-center gap-2.5">
                    <span className="num w-7 text-[11px] text-tinta-3">{j}d</span>
                    <span className="block h-[5px] flex-1 overflow-hidden rounded-sm bg-linha-2">
                      <span
                        className="block h-full bg-ambar"
                        style={{
                          width: `${((evento.zByWindow[j] ?? 0) / maiorZ) * 100}%`,
                        }}
                      />
                    </span>
                    <span className="num w-9 text-right text-[12px]">
                      {numero(evento.zByWindow[j])}
                    </span>
                  </div>
                ))}
              </div>
              {evento.zRobust !== null && (
                <div className="mt-2.5 flex justify-between border-t border-linha pt-2.5">
                  <span className="text-[11px] text-tinta-3">z robusto (MAD)</span>
                  <span className="num text-[12px]">{numero(evento.zRobust)}</span>
                </div>
              )}
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
