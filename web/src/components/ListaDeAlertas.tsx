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
      <div className="p-4 md:p-6">
        <div className="rounded-md border border-dashed border-linha-2 p-8 text-center text-[13px] text-tinta-3">
          Nenhum alerta ainda. Abra a ficha de um papel e escolha um nível no
          gráfico.
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6">
      {erro && (
        <p className="mb-3 rounded border border-baixa/40 bg-baixa/10 px-3 py-2 text-[12px] text-baixa">
          {erro}
        </p>
      )}

      <div className="overflow-hidden rounded-md border border-linha bg-painel">
        <div className="hidden grid-cols-[88px_86px_110px_1fr_150px] border-b border-linha bg-painel-2 px-3.5 py-2 md:grid">
          <span className="rotulo">Papel</span>
          <span className="rotulo">Direção</span>
          <span className="rotulo text-right">Nível</span>
          <span className="rotulo pl-4">Situação</span>
          <span className="rotulo text-right">Ações</span>
        </div>

        {alertas.map((a) => (
          <div
            key={a.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-linha px-3.5 py-2.5 last:border-b-0 md:grid md:grid-cols-[88px_86px_110px_1fr_150px] md:gap-0 md:py-2"
          >
            <Link
              href={`/papel/${a.ticker}?data=${a.tradeDate}`}
              className="text-[14px] font-semibold hover:text-ambar md:text-[13px]"
            >
              {a.ticker}
            </Link>
            <span className="text-[12px] text-tinta-2">
              {a.direcao === "acima" ? "subir até" : "cair até"}
            </span>
            <span className="num text-right text-[13px] font-semibold">
              {reais(a.preco)}
            </span>
            <span className="text-[12px] text-tinta-2 md:pl-4">
              {a.ativo ? (
                <span className="text-alta">vigiando</span>
              ) : (
                <>
                  disparou a{" "}
                  <span className="num text-ambar">{reais(a.precoDisparo)}</span>
                  {a.fonteDisparo && (
                    <span className="text-tinta-3"> · {a.fonteDisparo}</span>
                  )}
                </>
              )}
            </span>
            <span className="ml-auto flex gap-2 md:ml-0 md:justify-end">
              {!a.ativo && (
                <button
                  type="button"
                  onClick={() => religar(a.id)}
                  disabled={ocupado === a.id}
                  className="toque rounded border border-linha-2 px-2.5 py-1 text-[11px] text-tinta-2 transition-colors hover:text-ambar disabled:opacity-40"
                >
                  religar
                </button>
              )}
              <button
                type="button"
                onClick={() => apagar(a.id)}
                disabled={ocupado === a.id}
                className="toque rounded border border-linha-2 px-2.5 py-1 text-[11px] text-tinta-2 transition-colors hover:text-baixa disabled:opacity-40"
              >
                apagar
              </button>
            </span>
            <span className="num w-full text-[10px] text-tinta-3 md:hidden">
              criado em {fmtData(a.criadoEm.slice(0, 10))}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
