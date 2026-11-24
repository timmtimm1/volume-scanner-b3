"use client";

/**
 * O mapa mes a mes de uma moeda: anos nas linhas, jan a dez nas colunas, e no
 * fim duas linhas de resumo (a mediana de cada mes e quantas vezes ganhou). As
 * contas moram em `lib/analise.ts`.
 */

import { useMemo, useState } from "react";
import {
  corDaCelula,
  mapaMensal,
  pctCurto,
  sazonalidade,
  type LinhaAnual,
  type LinhaMensal,
} from "@/lib/analise";
import { data } from "@/lib/formato";

type Modo = "relativo" | "retorno";

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

function dica(m: LinhaMensal | LinhaAnual, moeda: string): string {
  return `de ${data(m.inicio)} a ${data(m.fim)} · ${moeda} ${pctCurto(m.retorno)} · BTC ${pctCurto(m.retornoBtc)}${
    m.parcial ? " · período incompleto" : ""
  }`;
}

function Celula({
  v,
  parcial,
  titulo,
}: {
  v: number | null | undefined;
  parcial?: boolean;
  titulo?: string;
}) {
  if (v === null || v === undefined) {
    return <td className="px-1.5 py-1.5 text-center font-semibold text-tinta-3">—</td>;
  }
  return (
    <td
      title={titulo}
      style={{ background: corDaCelula(v, "mes") }}
      className={`num whitespace-nowrap px-1.5 py-1.5 text-center font-semibold ${parcial ? "italic" : ""}`}
    >
      {pctCurto(v)}
      {parcial && "*"}
    </td>
  );
}

export function MapaMensalDaAnalise({
  moeda,
  mensais,
  anuais,
}: {
  moeda: string;
  mensais: LinhaMensal[];
  anuais: LinhaAnual[];
}) {
  const eBtc = moeda === "BTC";
  const [modo, setModo] = useState<Modo>(eBtc ? "retorno" : "relativo");
  const mapa = useMemo(() => mapaMensal(mensais), [mensais]);
  const saz = useMemo(() => sazonalidade(mensais, modo), [mensais, modo]);
  const doAno = useMemo(() => new Map(anuais.filter((a) => a.ano !== 0).map((a) => [a.ano, a])), [anuais]);

  if (mapa.anos.length === 0) {
    return <p className="text-[13px] font-semibold text-tinta-3">Sem meses para mostrar.</p>;
  }

  const rotuloDaBase = modo === "relativo" ? "Ganhou do BTC" : "Subiu";
  const fixa = "sticky left-0 z-10 bg-painel px-3 py-1.5 text-left font-extrabold md:px-4";

  return (
    <div className="flex flex-col gap-3">
      {!eBtc && (
        <div role="group" aria-label="O que mostrar" className="flex gap-1.5">
          {(
            [
              ["relativo", "Contra o BTC"],
              ["retorno", "Em dólar"],
            ] as const
          ).map(([valor, nome]) => (
            <button
              key={valor}
              type="button"
              onClick={() => setModo(valor)}
              aria-pressed={modo === valor}
              className={`toque h-9 rounded-full border px-3.5 text-[13px] font-bold transition-colors ${
                modo === valor
                  ? "border-acento bg-selecao text-acento"
                  : "border-linha-2 text-tinta-3 hover:text-tinta"
              }`}
            >
              {nome}
            </button>
          ))}
        </div>
      )}

      <div className="-mx-4 overflow-x-auto md:-mx-5">
        <table className="w-full border-collapse text-[12px] md:text-[13px]">
          <thead>
            <tr className="border-b border-linha text-tinta-3">
              <th scope="col" className="sticky left-0 z-10 bg-painel px-3 py-1.5 text-left font-bold md:px-4">
                Ano
              </th>
              {MESES.map((m) => (
                <th key={m} scope="col" className="px-1.5 py-1.5 text-center font-bold">
                  {m}
                </th>
              ))}
              <th scope="col" className="px-2 py-1.5 text-center font-bold">
                Ano
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-linha">
            {mapa.anos.map((ano) => {
              const a = doAno.get(ano);
              return (
                <tr key={ano}>
                  <th scope="row" className={`num ${fixa}`}>
                    {ano}
                  </th>
                  {MESES.map((_, i) => {
                    const m = mapa.celula(ano, i + 1);
                    return (
                      <Celula
                        key={i}
                        v={m?.[modo]}
                        parcial={m?.parcial}
                        titulo={m ? dica(m, moeda) : undefined}
                      />
                    );
                  })}
                  <Celula v={a?.[modo]} parcial={a?.parcial} titulo={a ? dica(a, moeda) : undefined} />
                </tr>
              );
            })}
          </tbody>
          <tfoot className="border-t-2 border-linha">
            <tr>
              <th scope="row" className={fixa}>
                Mediana
              </th>
              {saz.map((s) => (
                <Celula key={s.mes} v={s.mediana} />
              ))}
              <td />
            </tr>
            <tr className="border-t border-linha">
              <th scope="row" className={`${fixa} whitespace-nowrap`}>
                {rotuloDaBase}
              </th>
              {saz.map((s) => (
                <td key={s.mes} className="num whitespace-nowrap px-1.5 py-1.5 text-center font-semibold text-tinta-2">
                  {s.meses === 0 ? <span className="text-tinta-3">—</span> : `${s.positivos} de ${s.meses}`}
                </td>
              ))}
              <td />
            </tr>
          </tfoot>
        </table>
      </div>

      <p className="text-[12px] font-semibold leading-relaxed text-tinta-3">
        Sazonalidade: a mediana é o mês do meio de todos os anos — um ano maluco não puxa a conta.
        Meses incompletos ficam fora da mediana.
      </p>
    </div>
  );
}
