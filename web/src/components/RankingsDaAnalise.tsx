"use client";

/**
 * Os rankings: as 15 moedas com maior beta e as 15 com menor correlacao contra o
 * Bitcoin, em tres periodos (ou, na visao de commodities, so as que houver). As contas moram em `lib/analise.ts`.
 */

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  rankear,
  type CandidatoAoRanking,
  type ItemDoRanking,
  type MetricaDoRanking,
  type Periodo,
} from "@/lib/analise";
import { commodityDe } from "@/lib/commodities";
import { data, numero } from "@/lib/formato";

const TAMANHO = 15;

function Cartao({
  titulo,
  chave,
  itens,
  periodo,
  rotulo,
  commodities,
}: {
  titulo: string;
  chave: MetricaDoRanking;
  itens: ItemDoRanking[];
  periodo: Periodo;
  rotulo: string;
  commodities: boolean;
}) {
  const nomeDoValor = chave === "beta" ? "beta" : "correlação";
  const nomeDoOutro = chave === "beta" ? "correlação" : "beta";
  return (
    <section className="cartao flex min-w-0 flex-col gap-2 p-4 md:p-5">
      <h2 className="text-[16px] font-extrabold tracking-tight">{titulo}</h2>
      {itens.length === 0 ? (
        <p className="py-4 text-[13px] font-semibold text-tinta-3">
          Nenhuma {rotulo} com dado nesse período.
        </p>
      ) : (
        <ol className="divide-y divide-linha">
          {itens.map((item, i) => (
            <li key={item.moeda} className="flex items-baseline gap-3 py-2">
              <span className="num w-6 shrink-0 text-right text-[12px] font-bold text-tinta-3">
                {i + 1}
              </span>
              <Link
                href={`/analise/${encodeURIComponent(item.moeda)}`}
                className="min-w-0 truncate text-[14px] font-extrabold text-tinta hover:text-acento"
              >
                {item.moeda}
                {commodities && (
                  <span className="ml-1.5 text-[11px] font-semibold text-tinta-3">
                    {commodityDe(item.moeda)?.nome}
                  </span>
                )}
              </Link>
              <span className="num ml-auto whitespace-nowrap text-[15px] font-extrabold">
                <span className="mr-1 text-[11px] font-semibold text-tinta-3">{nomeDoValor}</span>
                {numero(item.valor, 2)}
              </span>
              <span className="num whitespace-nowrap text-[11px] font-semibold text-tinta-3">
                {item.outro !== null && `${nomeDoOutro} ${numero(item.outro, 2)}`}
                {periodo !== "90d" && item.dias !== null && (
                  <span className="ml-1.5">{item.dias} dias</span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export function RankingsDaAnalise({
  candidatos,
  ano,
  dia90,
  total,
  commodities = false,
}: {
  candidatos: CandidatoAoRanking[];
  ano: number | null;
  dia90: string | null;
  total: number;
  /** Rankings entre as commodities, e não entre as criptos. */
  commodities?: boolean;
}) {
  const rotulo = commodities ? "commodity" : "moeda";
  // Só 10 commodities: "as 15" seria mentira.
  const tamanhoDoTitulo = commodities ? Math.min(TAMANHO, candidatos.length) : TAMANHO;
  const [periodo, setPeriodo] = useState<Periodo>("90d");

  const PERIODOS: { valor: Periodo; nome: string }[] = [
    { valor: "90d", nome: "Últimos 90 dias" },
    { valor: "ano", nome: ano === null ? "Este ano" : `${ano} até agora` },
    { valor: "total", nome: "Período todo" },
  ];

  const porBeta = useMemo(
    () => rankear(candidatos, periodo, "beta", TAMANHO),
    [candidatos, periodo],
  );
  const porCorrelacao = useMemo(
    () => rankear(candidatos, periodo, "correlacao", TAMANHO),
    [candidatos, periodo],
  );

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <div className="flex flex-col gap-2 text-[13px] leading-relaxed text-tinta-2">
          <p>
            <b className="text-tinta">Beta.</b> Num dia em que o Bitcoin mexe 1%, {commodities ? "a commodity" : "a moeda"} costuma
            mexer beta% no mesmo sentido. Beta alto amplifica o Bitcoin, para cima e para baixo.
          </p>
          <p>
            <b className="text-tinta">Correlação.</b> Vai de −1 a 1 e diz o quanto {commodities ? "a commodity" : "a moeda"} se mexe
            junto com o Bitcoin. Correlação baixa: ela anda por conta própria, o que pode ajudar a
            diversificar, mas muitas vezes quer dizer que o movimento vem de notícia da própria{" "}
            {commodities ? "commodity" : "moeda"}.
          </p>
          <p>
            Entram {commodities ? `as ${total} commodities` : `as ${total} moedas`} negociando hoje com pelo menos US$ 1 milhão por dia, em média,
            nos últimos 12 meses. O BTC fica de fora: é a régua.
            {periodo === "90d" && dia90 !== null && ` Janela de 90 dias até ${data(dia90)}.`}
          </p>
        </div>

        <div role="group" aria-label="Período" className="flex flex-wrap gap-1.5">
          {PERIODOS.map((p) => (
            <button
              key={p.valor}
              type="button"
              onClick={() => setPeriodo(p.valor)}
              aria-pressed={periodo === p.valor}
              className={`toque h-9 rounded-full border px-3.5 text-[12px] font-bold transition-colors md:text-[13px] ${
                periodo === p.valor
                  ? "border-acento bg-selecao text-acento"
                  : "border-linha-2 text-tinta-3 hover:text-tinta"
              }`}
            >
              {p.nome}
            </button>
          ))}
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <Cartao
          titulo={`As ${tamanhoDoTitulo} com maior beta`}
          chave="beta"
          itens={porBeta}
          periodo={periodo}
          rotulo={rotulo}
          commodities={commodities}
        />
        <Cartao
          titulo={`As ${tamanhoDoTitulo} com menor correlação`}
          chave="correlacao"
          itens={porCorrelacao}
          periodo={periodo}
          rotulo={rotulo}
          commodities={commodities}
        />
      </div>
    </div>
  );
}
