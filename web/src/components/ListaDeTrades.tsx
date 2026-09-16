"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { CandleDeHoje } from "@/lib/candle-de-hoje";
import { data as fmtData, numero, percentual, reais } from "@/lib/formato";
import { marcarAgora } from "@/lib/posicao";
import { precoDeAgora } from "@/lib/preco-de-agora";
import type { TradeResumo } from "@/lib/trades";

/**
 * A lista de trades: em aberto (com marcacao a mercado de agora) e encerrados.
 *
 * A lista inicial vem pre-carregada do servidor (`listarTrades`), atras do
 * portao de login da propria pagina -- essa parte fica sem novo pedido. O que
 * so existe no navegador e a cotacao de agora de cada trade aberto, com o
 * mesmo cache de 5 minutos que a ficha do papel usa.
 */
export function ListaDeTrades({ iniciais }: { iniciais: TradeResumo[] }) {
  const abertos = iniciais.filter((t) => t.encerradoEm === null);
  const encerrados = iniciais.filter((t) => t.encerradoEm !== null);

  const [cotacoes, setCotacoes] = useState<Record<string, CandleDeHoje | null>>({});

  useEffect(() => {
    let cancelado = false;
    const tickers = [...new Set(abertos.map((t) => t.ticker))];
    Promise.all(
      tickers.map(async (ticker) => {
        try {
          const r = await fetch(`/api/cotacao/${ticker}/`);
          if (!r.ok) return [ticker, null] as const;
          const { candle } = (await r.json()) as { candle: CandleDeHoje | null };
          return [ticker, candle] as const;
        } catch {
          return [ticker, null] as const;
        }
      }),
    ).then((pares) => {
      if (cancelado) return;
      setCotacoes(Object.fromEntries(pares));
    });
    return () => {
      cancelado = true;
    };
    // Os tickers de `abertos` nao mudam nesta tela sem um novo carregamento de
    // pagina -- so os trades encerrados/apagados na propria ficha do papel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [iniciais]);

  if (iniciais.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-linha-2 p-8 text-center text-[13px] font-semibold text-tinta-3">
        Nenhum trade ainda. Registre a compra na ficha do papel.
      </div>
    );
  }

  const marcados = abertos.map((t) => {
    const info = precoDeAgora(cotacoes[t.ticker] ?? null, t.ultimoSnapshot);
    const marca = marcarAgora(t, info?.preco ?? null);
    return { trade: t, info, marca };
  });
  const custoTotal = abertos.reduce((soma, t) => soma + t.custoComprado, 0);
  const resultadoTotal = marcados.reduce((soma, m) => soma + m.marca.resultado, 0);
  const pctTotal = custoTotal > 0 ? resultadoTotal / custoTotal : null;

  return (
    <div className="flex flex-col gap-4">
      {abertos.length > 0 && (
        <section className="cartao flex flex-col gap-3 p-4 md:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-[16px] font-extrabold">Em aberto</h2>
            <span
              className={`num flex items-center gap-1.5 text-[14px] font-extrabold ${
                resultadoTotal >= 0 ? "text-alta" : "text-baixa"
              }`}
            >
              {reais(resultadoTotal)}
              <span className="text-[12px] font-bold">{percentual(pctTotal)}</span>
            </span>
          </div>

          <ul className="flex flex-col gap-2">
            {marcados.map(({ trade, info, marca }) => (
              <li
                key={trade.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-2xl bg-painel-2 px-3.5 py-3"
              >
                <Link
                  href={`/trades/${trade.id}`}
                  className="text-[15px] font-extrabold transition-colors hover:text-acento"
                >
                  {trade.ticker}
                </Link>
                <span className="num text-[12px] font-semibold text-tinta-3">
                  {numero(trade.quantidade, 0)} ações
                </span>
                <span
                  className={`num ml-auto text-[14px] font-extrabold ${
                    marca.resultado >= 0 ? "text-alta" : "text-baixa"
                  }`}
                >
                  {reais(marca.resultado)}{" "}
                  <span className="text-[12px] font-bold">{percentual(marca.resultadoPct)}</span>
                </span>

                <span className="num w-full text-[11px] font-semibold text-tinta-3">
                  PM {reais(trade.precoMedio)}
                  {info && (
                    <>
                      {" → "}
                      {reais(info.preco)} <span className="text-tinta-3">· {info.rotulo}</span>
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {encerrados.length > 0 && (
        <section className="cartao flex flex-col gap-3 p-4 md:p-5">
          <h2 className="text-[16px] font-extrabold">Encerrados</h2>
          <ul className="flex flex-col gap-2">
            {encerrados.map((t) => (
              <li
                key={t.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-2xl bg-painel-2 px-3.5 py-3"
              >
                <Link
                  href={`/trades/${t.id}`}
                  className="text-[15px] font-extrabold transition-colors hover:text-acento"
                >
                  {t.ticker}
                </Link>
                <span className="num text-[11px] font-semibold text-tinta-3">
                  {fmtData(t.abertoEm)} – {t.encerradoEm && fmtData(t.encerradoEm)}
                </span>
                <span
                  className={`num ml-auto text-[14px] font-extrabold ${
                    t.realizado >= 0 ? "text-alta" : "text-baixa"
                  }`}
                >
                  {reais(t.realizado)}{" "}
                  <span className="text-[12px] font-bold">
                    {percentual(t.custoComprado > 0 ? t.realizado / t.custoComprado : null)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
