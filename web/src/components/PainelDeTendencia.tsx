"use client";

import Link from "next/link";
import { useState } from "react";
import { diaCurto, percentual } from "@/lib/formato";
import { linkDaFichaNoMercado, preco, textos, type Mercado } from "@/lib/mercado";
import { INCLINACAO, PERIODOS, classificar, contar, nomeDaEscolha, passaNoFiltro } from "@/lib/tendencia";
import type { LinhaDeTendencia } from "@/lib/tendencias";
import { EtiquetaDeTendencia, SeletorDeTendencia, useFiltroDeTendencia } from "./SeletorDeTendencia";

const POR_PAGINA = 50;

type Props = {
  mercado: Mercado;
  dia: string | null;
  linhas: LinhaDeTendencia[];
  /** Nome de cada ativo, quando ha. */
  nomes: Record<string, string>;
};

/**
 * As moedas da aba Cripto com o filtro de tendencia (pedido de 17/11/2026):
 * Todas / Alta / Lateral / Baixa pelas medias que o usuario escolher, com a
 * etiqueta em cada uma. A conta de cada media vem pronta do pipeline; aqui so
 * a combinacao, que muda na hora. Nas acoes o mesmo filtro fica na tabela do
 * Historico.
 */
export function PainelDeTendencia({ mercado, dia, linhas, nomes }: Props) {
  const { escolha, filtro, mudar } = useFiltroDeTendencia(mercado);
  const [todos, setTodos] = useState(false);

  const t = textos(mercado);
  const n = contar(linhas, escolha);
  const contagem = { todas: linhas.length, alta: n.alta, lateral: n.lateral, baixa: n.baixa };
  const comEstado = linhas.map((l) => ({ ...l, estado: classificar(l.inclinacoes, escolha) }));
  const doFiltro = comEstado.filter((l) => passaNoFiltro(l.estado, filtro));
  const visiveis = todos ? doFiltro : doFiltro.slice(0, POR_PAGINA);

  return (
    <section className="cartao flex min-w-0 flex-col gap-3 p-4 md:p-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-[18px] font-extrabold">Moedas por tendência</h2>
        {dia && (
          <span className="num text-[12px] font-semibold text-tinta-3">
            {t.dia[0]} de {diaCurto(dia)} · pela {nomeDaEscolha(escolha)}
          </span>
        )}
      </div>

      {linhas.length === 0 ? (
        <p className="text-[13px] font-semibold text-tinta-3">
          A tendência é calculada na rodada da noite (21h10) e aparece aqui depois dela.
        </p>
      ) : (
        <>
          <SeletorDeTendencia
            escolha={escolha}
            filtro={filtro}
            contagem={contagem}
            mudar={(e, f) => {
              setTodos(false);
              mudar(e, f);
            }}
          />

          {doFiltro.length === 0 ? (
            <p className="text-[13px] font-semibold text-tinta-3">Nenhuma moeda nessa tendência com essas médias.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-linha">
              {visiveis.map((l) => (
                <li key={l.ticker} className="flex items-center gap-3 py-2">
                  <Link
                    href={linkDaFichaNoMercado(mercado, l.ticker)}
                    className="w-16 shrink-0 text-[14px] font-extrabold transition-colors hover:text-acento"
                  >
                    {l.ticker}
                  </Link>
                  <span className="flex min-w-0 flex-1 items-center gap-1.5">
                    <EtiquetaDeTendencia estado={l.estado} />
                    <span className="min-w-0 truncate text-[12px] font-semibold text-tinta-3">
                      {nomes[l.ticker] ?? ""}
                    </span>
                    {!l.liquido && (
                      <span className="whitespace-nowrap rounded-md bg-painel-2 px-1.5 py-0.5 text-[10px] font-bold text-tinta-3">
                        pouca liquidez
                      </span>
                    )}
                  </span>
                  <span className="num shrink-0 text-right text-[13px] font-semibold text-tinta-2">
                    {preco(mercado, l.fechamento)}
                  </span>
                  <span
                    className={`num w-14 shrink-0 text-right text-[13px] font-bold ${
                      l.variacao === null ? "text-tinta-3" : l.variacao >= 0 ? "text-alta" : "text-baixa"
                    }`}
                  >
                    {percentual(l.variacao)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {!todos && doFiltro.length > POR_PAGINA && (
            <button
              type="button"
              onClick={() => setTodos(true)}
              className="toque h-9 self-start rounded-full px-1 text-[13px] font-bold text-acento hover:underline"
            >
              Ver todas ({doFiltro.length})
            </button>
          )}

          <p className="text-[12px] font-semibold leading-relaxed text-tinta-3">
            Alta: todas as médias marcadas subindo; baixa: todas caindo; lateral: elas discordam.
            Subindo é acima do valor de alguns {t.dia[1]} atrás (
            {PERIODOS.map((p) => `${p}: ${INCLINACAO[p]}`).join(", ")}). Mostra a direção das médias
            no último fechamento, não para onde o preço vai. {t.universoDaTendencia}
            {n.sem > 0 && ` ${n.sem} sem histórico para essas médias ficam só em Todas.`}
          </p>
        </>
      )}
    </section>
  );
}
