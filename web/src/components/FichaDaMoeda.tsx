"use client";

import Link from "next/link";
import { useMemo } from "react";
import { Grafico } from "@/components/Grafico";
import { fmtR } from "@/lib/backtest-tela";
import { data, diaCurto, percentual } from "@/lib/formato";
import { casasDoPreco, gatilhoNoMercado, preco, stopNoMercado } from "@/lib/mercado";
import { NOME_DO_SETUP, resultadoEmR, rotuloDoEstado, type Setup } from "@/lib/setups-tela";
import type { Barra, NivelDoGrafico } from "@/lib/types";
import { paraMarca } from "@/lib/useSetupsDoPapel";

const MERCADO = "cripto" as const;

type Props = {
  ticker: string;
  nome: string | null;
  posicao: number | null;
  barras: Barra[];
  /** Dias em que o volume cruzou o limiar: o candle fica dourado. */
  eventos: { tradeDate: string }[];
  niveis: NivelDoGrafico[];
  setups: Setup[];
  /** Dia a destacar no grafico (vem do cartao da entrada). */
  foco: string | null;
};

function volumeCurto(v: number): string {
  const f = (n: number, casas: number) =>
    new Intl.NumberFormat("pt-BR", { maximumFractionDigits: casas }).format(n);
  if (v >= 1e9) return `US$ ${f(v / 1e9, 1)} bi`;
  if (v >= 1e6) return `US$ ${f(v / 1e6, 1)} mi`;
  return `US$ ${f(v / 1e3, 0)} mil`;
}

/**
 * A ficha de uma criptomoeda: o grafico diario com suportes, resistencias e os
 * setups que armaram nela, e a lista desses setups. E a ficha do papel sem o
 * que so existe para acao (fundamentos, proventos, noticias, alertas de preco
 * e diario de trades, que em cripto sao outra fase).
 */
export function FichaDaMoeda({ ticker, nome, posicao, barras, eventos, niveis, setups, foco }: Props) {
  const ultima = barras[barras.length - 1];
  const anterior = barras[barras.length - 2];
  const variacao = anterior && anterior.close > 0 ? ultima.close / anterior.close - 1 : null;
  // As casas do eixo saem do preco de hoje: 0 para o BTC, 10 para uma moeda de 0,000004.
  const casas = casasDoPreco(ultima.close);
  const marcas = useMemo(() => setups.map(paraMarca), [setups]);
  const armados = setups.filter((s) => s.estado === "armado");

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-wrap items-end gap-x-6 gap-y-3 p-5">
        <div className="flex min-w-0 flex-col gap-0.5">
          <Link href="/cripto" className="text-[12px] font-bold text-tinta-3 hover:text-acento">
            ‹ Cripto
          </Link>
          <h1 className="text-[26px] font-extrabold tracking-tight">
            {ticker}
            {nome && <span className="ml-2 text-[15px] font-bold text-tinta-3">{nome}</span>}
          </h1>
          {posicao !== null && (
            <span className="text-[12px] font-semibold text-tinta-3">
              {posicao}ª maior por valor de mercado
            </span>
          )}
        </div>
        <div className="flex-1" />
        <div className="flex flex-col items-end">
          <span className="num text-[24px] font-extrabold">{preco(MERCADO, ultima.close)}</span>
          <span className="num text-[12px] font-semibold text-tinta-3">
            <span className={variacao === null ? "" : variacao >= 0 ? "text-alta" : "text-baixa"}>
              {percentual(variacao)}
            </span>{" "}
            no candle de {data(ultima.tradeDate)} · volume {volumeCurto(ultima.volumeFinancial)}
          </span>
        </div>
      </section>

      <section className="cartao p-2 md:p-3">
        <Grafico
          barras={barras}
          eventos={eventos}
          destaque={foco ?? undefined}
          niveis={niveis}
          setups={marcas}
          casasDoPreco={casas}
          classeDeAltura="h-[320px] md:h-[440px] lg:h-[560px]"
        />
        <p className="px-2 pt-2 text-[12px] font-semibold text-tinta-3">
          Candle diário da Binance, par {ticker}/USDT. Cada candle vai das 21h às 21h de Brasília.
          As linhas são suportes e resistências de 2 ou mais toques; candle dourado é dia de
          volume muito acima do normal.
        </p>
      </section>

      {armados.length > 0 && (
        <section className="cartao flex flex-col gap-2 p-4 md:p-5">
          <h2 className="text-[16px] font-extrabold">Armado agora</h2>
          <ul className="flex flex-col divide-y divide-linha">
            {armados.map((s) => (
              <li key={s.id} className="num flex flex-wrap items-baseline gap-x-4 gap-y-1 py-2 text-[13px] font-semibold">
                <span className="font-extrabold">{NOME_DO_SETUP[s.categoria]}</span>
                <span className="text-tinta-2">
                  compra acima de{" "}
                  <span className="font-extrabold text-acento">
                    {preco(MERCADO, gatilhoNoMercado(MERCADO, s.maxima))}
                  </span>
                </span>
                <span className="text-tinta-2">
                  stop {preco(MERCADO, stopNoMercado(MERCADO, s.minima))}
                </span>
                <span className="text-tinta-3">candle de {diaCurto(s.tradeDate)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="cartao flex flex-col gap-2 p-4 md:p-5">
        <h2 className="text-[16px] font-extrabold">
          Setups nesta moeda
          <span className="num ml-2 text-[13px] font-bold text-tinta-3">{setups.length}</span>
        </h2>
        {setups.length === 0 ? (
          <p className="text-[13px] font-semibold text-tinta-3">
            Nenhum setup armou nesta moeda no período do gráfico.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-linha">
            {setups.map((s) => {
              const r = resultadoEmR(s);
              return (
                <li key={s.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                  <span className="num w-12 text-[12px] font-semibold text-tinta-3">
                    {diaCurto(s.tradeDate)}
                  </span>
                  <span className="min-w-0 flex-1 text-[13px] font-semibold text-tinta-2">
                    <span className="font-bold">{NOME_DO_SETUP[s.categoria]}</span> ·{" "}
                    {rotuloDoEstado(s.estado, s.saidaRegra)}
                  </span>
                  <span className="num text-[13px] font-bold">
                    {r === null ? (
                      <span className="text-tinta-3">—</span>
                    ) : (
                      <span className={r >= 0 ? "text-alta" : "text-baixa"}>{fmtR(r)}</span>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
