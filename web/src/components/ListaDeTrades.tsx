"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { fmtR } from "@/lib/backtest-tela";
import type { CandleDeHoje } from "@/lib/candle-de-hoje";
import { resultadoEmRDoTrade } from "@/lib/diario";
import { data as fmtData, percentual } from "@/lib/formato";
import {
  diaDoMercado,
  linkDoTrade,
  preco,
  quantidade,
  sufixoDoMercado,
  valor,
  type Mercado,
} from "@/lib/mercado";
import { marcarAgora } from "@/lib/posicao";
import { precoDeAgora } from "@/lib/preco-de-agora";
import { NOME_NO_DIARIO } from "@/lib/setups-tela";
import type { TradeResumo } from "@/lib/trades";
import { ArranjoDaPagina, GradeDeCaixas } from "./OrganizarCaixas";

/**
 * A lista de trades: em aberto (com marcacao a mercado de agora) e encerrados,
 * dos dois mercados. `trades` ja chega filtrado pelo filtro da pagina; cada
 * linha fala na moeda do proprio trade (reais ou dolares).
 *
 * A lista inicial vem pre-carregada do servidor (`listarTrades`), atras do
 * portao de login da propria pagina -- essa parte fica sem novo pedido. O que
 * so existe no navegador e a cotacao de agora de cada trade aberto: brapi ou
 * Yahoo para acao (cache de 5 minutos, o mesmo da ficha), Binance para cripto.
 */

/** O R de um trade em texto colorido; "—" sem stop, com a dica onde ha espaco. */
function EmR({ r }: { r: number | null }) {
  if (r === null) {
    return (
      <span className="num text-[12px] font-semibold text-tinta-3" title="Defina o stop no trade para ver em R">
        — em R
      </span>
    );
  }
  return (
    <span className={`num text-[12px] font-bold ${r >= 0 ? "text-alta" : "text-baixa"}`}>{fmtR(r)}</span>
  );
}

/** O setup do trade como etiqueta; nada quando nao tem. */
function EtiquetaDoSetup({ trade }: { trade: TradeResumo }) {
  if (!trade.categoriaSetup) return null;
  return (
    <span className="rounded-md bg-painel px-2 py-0.5 text-[11px] font-bold text-tinta-2">
      {NOME_NO_DIARIO[trade.categoriaSetup]}
    </span>
  );
}

/** "cripto" ao lado do ticker, so quando a lista mistura os dois mercados. */
function EtiquetaDoMercado({ mercado, mostrar }: { mercado: Mercado; mostrar: boolean }) {
  if (!mostrar || mercado === "b3") return null;
  return (
    <span className="rounded-md bg-selecao px-1.5 py-0.5 text-[10px] font-extrabold uppercase text-acento">
      cripto
    </span>
  );
}

const chave = (t: { mercado: Mercado; ticker: string }) => `${t.mercado}:${t.ticker}`;

export function ListaDeTrades({
  trades,
  misturado,
  vazio,
}: {
  trades: TradeResumo[];
  /** A lista tem os dois mercados (filtro "Tudo"): marca as linhas de cripto. */
  misturado: boolean;
  /** O texto de quando nao ha trade nenhum. */
  vazio: string;
}) {
  const abertos = trades.filter((t) => t.encerradoEm === null);
  const encerrados = trades.filter((t) => t.encerradoEm !== null);

  const [cotacoes, setCotacoes] = useState<Record<string, CandleDeHoje | null>>({});

  // Cada ativo aberto e pedido uma vez so (trocar o filtro nao repete), e cada
  // cotacao entra na tela quando chega: a da Binance responde em milissegundos e
  // nao fica esperando a brapi/Yahoo de uma acao.
  const pedidas = useRef(new Set<string>());
  const montada = useRef(true);
  useEffect(() => {
    montada.current = true;
    return () => {
      montada.current = false;
    };
  }, []);
  const todas = [...new Set(abertos.map(chave))].join(",");
  useEffect(() => {
    for (const k of todas.split(",")) {
      if (k === "" || pedidas.current.has(k)) continue;
      pedidas.current.add(k);
      const [mercado, ticker] = k.split(":") as [Mercado, string];
      fetch(`/api/cotacao/${ticker}/${sufixoDoMercado(mercado)}`)
        .then(async (r) => (r.ok ? ((await r.json()) as { candle: CandleDeHoje | null }).candle : null))
        .catch(() => null)
        .then((candle) => {
          if (montada.current) setCotacoes((atuais) => ({ ...atuais, [k]: candle }));
        });
    }
  }, [todas]);

  if (trades.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-linha-2 p-8 text-center text-[13px] font-semibold text-tinta-3">
        {vazio}
      </div>
    );
  }

  const agora = new Date();
  const marcados = abertos.map((t) => {
    const info = precoDeAgora(cotacoes[chave(t)] ?? null, t.ultimoSnapshot, diaDoMercado(t.mercado, agora));
    const marca = marcarAgora(t, info?.preco ?? null);
    return { trade: t, info, marca };
  });

  // Reais e dolares nao se somam: um total por moeda.
  const totais = (["b3", "cripto"] as const)
    .map((mercado) => {
      const doMercado = marcados.filter((m) => m.trade.mercado === mercado);
      const custo = doMercado.reduce((soma, m) => soma + m.trade.custoComprado, 0);
      const resultado = doMercado.reduce((soma, m) => soma + m.marca.resultado, 0);
      return { mercado, n: doMercado.length, resultado, pct: custo > 0 ? resultado / custo : null };
    })
    .filter((t) => t.n > 0);

  const caixaAbertos = abertos.length > 0 && (
    <section className="cartao flex flex-col gap-3 p-4 md:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[16px] font-extrabold">Em aberto</h2>
        <span className="flex flex-wrap items-center justify-end gap-x-3 gap-y-0.5">
          {totais.map((t) => (
            <span
              key={t.mercado}
              className={`num flex items-center gap-1.5 text-[14px] font-extrabold ${
                t.resultado >= 0 ? "text-alta" : "text-baixa"
              }`}
            >
              {valor(t.mercado, t.resultado)}
              <span className="text-[12px] font-bold">{percentual(t.pct)}</span>
            </span>
          ))}
        </span>
      </div>

      <ul className="flex flex-col gap-2">
        {marcados.map(({ trade, info, marca }) => (
          <li
            key={chave(trade) + trade.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-2xl bg-painel-2 px-3.5 py-3"
          >
            <Link
              href={linkDoTrade(trade.mercado, trade.id)}
              className="text-[15px] font-extrabold transition-colors hover:text-acento"
            >
              {trade.ticker}
            </Link>
            <EtiquetaDoMercado mercado={trade.mercado} mostrar={misturado} />
            <EtiquetaDoSetup trade={trade} />
            <span className="num text-[12px] font-semibold text-tinta-3">
              {quantidade(trade.mercado, trade.quantidade, trade.ticker)}
            </span>
            <span
              className={`num ml-auto text-right text-[14px] font-extrabold ${
                marca.resultado >= 0 ? "text-alta" : "text-baixa"
              }`}
            >
              {valor(trade.mercado, marca.resultado)}{" "}
              <span className="text-[12px] font-bold">{percentual(marca.resultadoPct)}</span>
              <span className="block">
                <EmR r={resultadoEmRDoTrade(trade, info?.preco ?? null)} />
              </span>
            </span>

            <span className="num w-full text-[11px] font-semibold text-tinta-3">
              PM {preco(trade.mercado, trade.precoMedio)}
              {info && (
                <>
                  {" → "}
                  {preco(trade.mercado, info.preco)} <span className="text-tinta-3">· {info.rotulo}</span>
                </>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );

  const caixaEncerrados = encerrados.length > 0 && (
    <section className="cartao flex flex-col gap-3 p-4 md:p-5">
      <h2 className="text-[16px] font-extrabold">Encerrados</h2>
      <ul className="flex flex-col gap-2">
        {encerrados.map((t) => (
          <li
            key={chave(t) + t.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-2xl bg-painel-2 px-3.5 py-3"
          >
            <Link
              href={linkDoTrade(t.mercado, t.id)}
              className="text-[15px] font-extrabold transition-colors hover:text-acento"
            >
              {t.ticker}
            </Link>
            <EtiquetaDoMercado mercado={t.mercado} mostrar={misturado} />
            <EtiquetaDoSetup trade={t} />
            <span className="num text-[11px] font-semibold text-tinta-3">
              {fmtData(t.abertoEm)} – {t.encerradoEm && fmtData(t.encerradoEm)}
            </span>
            <span
              className={`num ml-auto text-right text-[14px] font-extrabold ${
                t.realizado >= 0 ? "text-alta" : "text-baixa"
              }`}
            >
              {valor(t.mercado, t.realizado)}{" "}
              <span className="text-[12px] font-bold">
                {percentual(t.custoComprado > 0 ? t.realizado / t.custoComprado : null)}
              </span>
              <span className="block">
                <EmR r={resultadoEmRDoTrade(t, null)} />
              </span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );

  return (
    <ArranjoDaPagina pagina="trades">
      <GradeDeCaixas caixas={{ abertos: caixaAbertos, encerrados: caixaEncerrados }} />
    </ArranjoDaPagina>
  );
}
