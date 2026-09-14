"use client";

import Link from "next/link";
import { useState } from "react";
import type { Alerta } from "@/lib/alertas";
import { data as fmtData, reais } from "@/lib/formato";

/**
 * A lista, com apagar e religar.
 *
 * O estado vive aqui e nao no servidor: apagar um alerta nao deve custar um
 * recarregamento de pagina inteiro. A lista inicial vem pre-carregada pelo
 * componente de servidor, entao a primeira pintura ja tem conteudo.
 *
 * As chamadas vao com barra no fim de proposito. O `trailingSlash: true` do
 * next.config faz `/api/alertas` responder 308 para `/api/alertas/`; o 308
 * preserva metodo e corpo (diferente do 302), entao funcionaria de qualquer
 * jeito -- mas custaria uma ida e volta a mais em toda chamada.
 */
export function ListaDeAlertas({ iniciais }: { iniciais: Alerta[] }) {
  const [alertas, setAlertas] = useState(iniciais);
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function apagar(id: number) {
    setOcupado(id);
    setErro(null);
    try {
      const r = await fetch(`/api/alertas/${id}/`, { method: "DELETE" });
      if (!r.ok) throw new Error("não foi possível apagar");
      setAlertas((atual) => atual.filter((a) => a.id !== id));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "algo deu errado");
    } finally {
      setOcupado(null);
    }
  }

  async function religar(id: number) {
    setOcupado(id);
    setErro(null);
    try {
      const r = await fetch(`/api/alertas/${id}/`, { method: "PATCH" });
      if (!r.ok) throw new Error("não foi possível religar");
      const { alerta } = (await r.json()) as { alerta: Alerta };
      setAlertas((atual) => atual.map((a) => (a.id === id ? alerta : a)));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "algo deu errado");
    } finally {
      setOcupado(null);
    }
  }

  if (alertas.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-linha-2 p-8 text-center text-[13px] font-semibold text-tinta-3">
        Nenhum alerta ainda. Abra a ficha de um papel e escolha um nível no gráfico.
      </div>
    );
  }

  const ativos = alertas.filter((a) => a.ativo).length;
  const disparados = alertas.length - ativos;

  return (
    <section className="cartao flex flex-col gap-3 p-4 md:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="num inline-flex h-8 items-center rounded-full bg-selecao px-3 text-[12px] font-bold text-acento">
          {ativos === 1 ? "1 vigiando" : `${ativos} vigiando`}
        </span>
        {disparados > 0 && (
          <span className="num inline-flex h-8 items-center rounded-full bg-painel-2 px-3 text-[12px] font-bold text-tinta-2">
            {disparados === 1 ? "1 já disparou" : `${disparados} já dispararam`}
          </span>
        )}
      </div>

      {erro && (
        <p className="rounded-xl bg-baixa-fundo px-3 py-2 text-[13px] font-semibold text-baixa">{erro}</p>
      )}

      <div className="hidden grid-cols-[100px_100px_120px_minmax(0,1fr)_170px] gap-2 px-3 md:grid">
        <span className="rotulo">Papel</span>
        <span className="rotulo">Direção</span>
        <span className="rotulo text-right">Nível</span>
        <span className="rotulo pl-4">Situação</span>
        <span className="rotulo text-right">Ações</span>
      </div>

      <ul className="flex flex-col gap-2 md:gap-0.5">
        {alertas.map((a) => (
          <li
            key={a.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl bg-painel-2 px-3.5 py-3 md:grid md:grid-cols-[100px_100px_120px_minmax(0,1fr)_170px] md:gap-2 md:bg-transparent md:py-2.5 md:hover:bg-painel-2"
          >
            <Link
              href={`/papel/${a.ticker}?data=${a.tradeDate}`}
              className="text-[15px] font-extrabold transition-colors hover:text-acento md:text-[14px]"
            >
              {a.ticker}
            </Link>
            <span className="text-[13px] font-semibold text-tinta-2">
              {a.direcao === "acima" ? "Subir até" : "Cair até"}
            </span>
            <span className="num text-[14px] font-extrabold md:text-right">{reais(a.preco)}</span>
            <span className="w-full text-[13px] font-semibold text-tinta-2 md:w-auto md:pl-4">
              {a.ativo ? (
                <span className="inline-flex items-center gap-2 text-acento">
                  <span className="h-2 w-2 rounded-full bg-acento" />
                  vigiando
                </span>
              ) : (
                <>
                  disparou a <span className="num font-extrabold text-tinta">{reais(a.precoDisparo)}</span>
                  {a.fonteDisparo && <span className="text-tinta-3"> · {a.fonteDisparo}</span>}
                </>
              )}
              <span className="num block text-[11px] text-tinta-3 md:hidden">
                criado em {fmtData(a.criadoEm.slice(0, 10))}
              </span>
            </span>
            <span className="ml-auto flex gap-2 md:ml-0 md:justify-end">
              {!a.ativo && (
                <button
                  type="button"
                  onClick={() => religar(a.id)}
                  disabled={ocupado === a.id}
                  className="toque h-9 rounded-full border border-linha-2 px-3.5 text-[12px] font-bold text-tinta-2 transition-colors hover:border-acento hover:text-acento disabled:opacity-40"
                >
                  Religar
                </button>
              )}
              <button
                type="button"
                onClick={() => apagar(a.id)}
                disabled={ocupado === a.id}
                className="toque h-9 rounded-full border border-linha-2 px-3.5 text-[12px] font-bold text-tinta-2 transition-colors hover:border-baixa hover:text-baixa disabled:opacity-40"
              >
                Apagar
              </button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
