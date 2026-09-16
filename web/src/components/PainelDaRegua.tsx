"use client";

import { useState } from "react";
import type { Direcao } from "@/lib/alertas";
import { diaCurto, numero, percentual, reais } from "@/lib/formato";
import { medirMovimento, medirNivel, type PontoDaRegua, type TradeDaRegua } from "@/lib/regua";

type Props = {
  pontos: PontoDaRegua[];
  agora: number;
  /** Pregoes conhecidos do grafico, para contar quantos ha entre os dois pontos. */
  datas: string[];
  trade?: TradeDaRegua | null;
  podeCriarAlerta: boolean;
  criarAlerta: (preco: number, direcao: Direcao) => Promise<void>;
  aoFechar: () => void;
};

/** Verde/vermelho de direcao de preco -- mesma leitura do resto da ficha. */
function corDaVariacao(v: number): string {
  return v >= 0 ? "text-alta" : "text-baixa";
}

/**
 * O que a regua do grafico mostra: a distancia de "agora" ate um nivel
 * tocado, ou o movimento entre dois pontos. Fica logo abaixo do grafico, nao
 * por cima dos candles -- em 390px nao ha espaco para um popup flutuante.
 */
export function PainelDaRegua({
  pontos,
  agora,
  datas,
  trade = null,
  podeCriarAlerta,
  criarAlerta,
  aoFechar,
}: Props) {
  const [criando, setCriando] = useState(false);
  const [criado, setCriado] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function aoClicarCriarAlerta(preco: number, direcao: Direcao) {
    setCriando(true);
    setErro(null);
    try {
      await criarAlerta(preco, direcao);
      setCriado(preco);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "não foi possível criar o alerta");
    } finally {
      setCriando(false);
    }
  }

  const cabecalho = (
    <div className="flex items-center justify-between">
      <span className="text-[13px] font-extrabold">Régua</span>
      <button
        type="button"
        onClick={aoFechar}
        aria-label="Fechar régua"
        className="flex h-7 w-7 items-center justify-center rounded-full text-tinta-3 transition-colors hover:bg-linha hover:text-tinta"
      >
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
          <path d="M2 2l6 6M8 2L2 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  );

  if (pontos.length === 0) {
    return (
      <div className="flex flex-col gap-2 rounded-2xl bg-painel-2 p-3.5">
        {cabecalho}
        <p className="text-[12px] font-semibold text-tinta-3">
          Toque no gráfico para marcar um nível a partir de agora.
        </p>
      </div>
    );
  }

  if (pontos.length === 1) {
    const nivel = pontos[0].preco;
    const r = medirNivel({ agora, nivel, trade });
    return (
      <div className="flex flex-col gap-2.5 rounded-2xl bg-painel-2 p-3.5">
        {cabecalho}
        <div className="flex flex-wrap items-center gap-2">
          <span className="num text-[15px] font-extrabold">
            agora {reais(r.agora)} → {reais(r.nivel)}
          </span>
          <span className={`num text-[13px] font-extrabold ${corDaVariacao(r.porAcao)}`}>
            {percentual(r.variacaoPct, 2)}
          </span>
        </div>
        <span className="num text-[12px] font-semibold text-tinta-3">
          {reais(r.porAcao)} por ação
        </span>

        {r.trade && (
          <div className="flex flex-col gap-1 border-t border-linha pt-2.5 text-[12px] font-semibold text-tinta-2">
            <span>
              seu trade ({numero(trade?.quantidade ?? 0, 0)} ações):{" "}
              <strong className={`num ${corDaVariacao(r.trade.ateLa)}`}>
                {reais(r.trade.ateLa)}
              </strong>{" "}
              até lá
            </span>
            <span>
              trade inteiro nesse preço:{" "}
              <strong className={`num ${corDaVariacao(r.trade.inteiro.resultado)}`}>
                {reais(r.trade.inteiro.resultado)} ({percentual(r.trade.inteiro.resultadoPct, 2)})
              </strong>
            </span>
          </div>
        )}

        {podeCriarAlerta && (
          <div className="flex flex-col gap-1.5 border-t border-linha pt-2.5">
            {criado === nivel ? (
              <span className="text-[12px] font-bold text-acento">
                Alerta criado em {reais(nivel)}.
              </span>
            ) : (
              <button
                type="button"
                onClick={() => aoClicarCriarAlerta(nivel, r.direcao)}
                disabled={criando}
                className="toque h-10 self-start rounded-full bg-primario px-4 text-[12px] font-bold text-primario-tinta transition-opacity disabled:opacity-40"
              >
                {criando ? "Criando…" : `Criar alerta em ${reais(nivel)}`}
              </button>
            )}
            {erro && <span className="text-[11px] font-semibold text-baixa">{erro}</span>}
          </div>
        )}

        <p className="text-[11px] font-semibold text-tinta-3">
          toque outro ponto para medir um movimento
        </p>
      </div>
    );
  }

  const r = medirMovimento({ a: pontos[0], b: pontos[1], datas });
  return (
    <div className="flex flex-col gap-2.5 rounded-2xl bg-painel-2 p-3.5">
      {cabecalho}
      <div className="flex flex-wrap items-center gap-2">
        <span className="num text-[15px] font-extrabold">
          {diaCurto(r.de.data)} {reais(r.de.preco)} → {diaCurto(r.ate.data)} {reais(r.ate.preco)}
        </span>
        <span className={`num text-[13px] font-extrabold ${corDaVariacao(r.porAcao)}`}>
          {percentual(r.variacaoPct, 2)}
        </span>
      </div>
      <span className="num text-[12px] font-semibold text-tinta-3">
        {reais(r.porAcao)} por ação · {r.pregoes} {r.pregoes === 1 ? "pregão" : "pregões"} entre
        eles
      </span>
      <p className="text-[11px] font-semibold text-tinta-3">toque de novo para recomeçar</p>
    </div>
  );
}
