"use client";

import Link from "next/link";
import { useMemo, useState, useSyncExternalStore } from "react";
import { diaCurto, percentual } from "@/lib/formato";
import { linkDaFichaNoMercado, preco, textos, type Mercado } from "@/lib/mercado";
import {
  ESTADOS,
  INCLINACAO,
  PERIODOS,
  alternar,
  classificar,
  contar,
  escolhaDoTexto,
  nomeDaEscolha,
  type EscolhaDeMedias,
  type Estado,
} from "@/lib/tendencia";
import type { LinhaDeTendencia } from "@/lib/tendencias";

const NOME_DO_ESTADO: Record<Estado, string> = { alta: "Alta", lateral: "Lateral", baixa: "Baixa" };
const POR_PAGINA = 40;

// A escolha guardada por mercado. A memoria vale quando o navegador nao deixa
// gravar (aba anonima, previa): a escolha so nao sobrevive ao recarregar.
const memoria = new Map<string, string>();
const assinantes = new Set<() => void>();

function assinar(avisar: () => void): () => void {
  assinantes.add(avisar);
  return () => {
    assinantes.delete(avisar);
  };
}

function lerGuardado(chave: string): string | null {
  if (memoria.has(chave)) return memoria.get(chave) ?? null;
  try {
    return window.localStorage.getItem(chave);
  } catch {
    return null;
  }
}

function gravar(chave: string, texto: string): void {
  memoria.set(chave, texto);
  try {
    window.localStorage.setItem(chave, texto);
  } catch {
    // fica so na memoria
  }
  for (const avisar of assinantes) avisar();
}

type Props = {
  mercado: Mercado;
  dia: string | null;
  linhas: LinhaDeTendencia[];
  /** Nome de cada ativo, quando ha. */
  nomes: Record<string, string>;
};

/**
 * Os ativos em alta, lateral ou baixa pelas medias que o usuario escolher (pedido
 * de 17/11/2026), no scanner e na aba Cripto. A conta de cada media vem pronta
 * do pipeline; aqui so a combinacao, que muda na hora. A escolha fica guardada
 * no navegador, por mercado.
 */
export function PainelDeTendencia({ mercado, dia, linhas, nomes }: Props) {
  const chave = `tendencia:${mercado}`;
  // No servidor e na hidratacao nao ha escolha guardada: o HTML sai com o
  // padrao (MME 20 + 80, alta) e a guardada entra logo depois, sem erro de hidratacao.
  const texto = useSyncExternalStore(assinar, () => lerGuardado(chave), () => null);
  const { escolha, estado } = useMemo(() => escolhaDoTexto(texto), [texto]);
  const [todos, setTodos] = useState(false);

  function guardar(e: EscolhaDeMedias, s: Estado) {
    setTodos(false);
    gravar(chave, JSON.stringify({ ...e, estado: s }));
  }

  const t = textos(mercado);
  const contagem = contar(linhas, escolha);
  const doEstado = linhas.filter((l) => classificar(l.inclinacoes, escolha) === estado);
  const visiveis = todos ? doEstado : doEstado.slice(0, POR_PAGINA);

  return (
    <section className="cartao flex min-w-0 flex-col gap-3 p-4 md:p-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-[18px] font-extrabold">Tendência</h2>
        {dia && (
          <span className="num text-[12px] font-semibold text-tinta-3">
            {t.dia[0]} de {diaCurto(dia)} · pela {nomeDaEscolha(escolha)}
          </span>
        )}
      </div>

      {linhas.length === 0 ? (
        <p className="text-[13px] font-semibold text-tinta-3">
          A tendência aparece depois da próxima rodada da noite.
        </p>
      ) : (
        <>
          <div role="group" aria-label="Tendência" className="grid grid-cols-3 rounded-full border border-linha-2 p-0.5">
            {ESTADOS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => guardar(escolha, s)}
                aria-pressed={estado === s}
                className={`toque h-9 rounded-full text-[13px] font-bold transition-colors ${
                  estado === s ? "bg-painel text-acento shadow-sm" : "text-tinta-3 hover:text-tinta"
                }`}
              >
                {NOME_DO_ESTADO[s]} <span className="num font-semibold">{contagem[s]}</span>
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rotulo mr-1">Médias</span>
            {PERIODOS.map((p) => {
              const ligada = escolha.periodos.includes(p);
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => guardar(alternar(escolha, p), estado)}
                  aria-pressed={ligada}
                  className={`num toque h-8 min-w-10 rounded-full border px-2.5 text-[12px] font-bold transition-colors ${
                    ligada
                      ? "border-acento bg-selecao text-acento"
                      : "border-linha-2 text-tinta-3 hover:text-tinta"
                  }`}
                >
                  {p}
                </button>
              );
            })}
            <div role="group" aria-label="Tipo de média" className="ml-auto flex rounded-xl border border-linha-2 p-0.5">
              {(["MME", "MMA"] as const).map((tipo) => (
                <button
                  key={tipo}
                  type="button"
                  onClick={() => guardar({ ...escolha, tipo }, estado)}
                  aria-pressed={escolha.tipo === tipo}
                  title={tipo === "MME" ? "média exponencial" : "média simples"}
                  className={`toque h-7 rounded-[10px] px-2.5 text-[11px] font-bold transition-colors ${
                    escolha.tipo === tipo ? "bg-painel text-acento shadow-sm" : "text-tinta-3"
                  }`}
                >
                  {tipo}
                </button>
              ))}
            </div>
          </div>

          {doEstado.length === 0 ? (
            <p className="text-[13px] font-semibold text-tinta-3">
              Nenhum ativo em {NOME_DO_ESTADO[estado].toLowerCase()} com essas médias.
            </p>
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
                  <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-tinta-3">
                    {nomes[l.ticker] ?? ""}
                    {!l.liquido && (
                      <span className="ml-1.5 whitespace-nowrap rounded-md bg-painel-2 px-1.5 py-0.5 text-[10px] font-bold text-tinta-3">
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
          {!todos && doEstado.length > POR_PAGINA && (
            <button
              type="button"
              onClick={() => setTodos(true)}
              className="toque h-9 self-start rounded-full px-1 text-[13px] font-bold text-acento hover:underline"
            >
              Ver todos ({doEstado.length})
            </button>
          )}

          <p className="text-[12px] font-semibold leading-relaxed text-tinta-3">
            Alta: todas as médias marcadas subindo; baixa: todas caindo; lateral: elas discordam.
            Subindo é acima do valor de alguns {t.dia[1]} atrás (
            {PERIODOS.map((p) => `${p}: ${INCLINACAO[p]}`).join(", ")}). Mostra a direção das médias
            no último fechamento, não para onde o preço vai. {t.universoDaTendencia}
            {contagem.sem > 0 && ` ${contagem.sem} ficam de fora por não terem histórico para essas médias.`}
          </p>
        </>
      )}
    </section>
  );
}
