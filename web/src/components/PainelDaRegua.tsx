"use client";

import { useState } from "react";
import type { Direcao } from "@/lib/alertas";
import { percentual } from "@/lib/formato";
import { preco, valorComSinal, type Mercado } from "@/lib/mercado";
import { medirNivel, type TradeDaRegua } from "@/lib/regua";

type Props = {
  /** Preco do ponto final da medicao fixada. */
  nivel: number;
  agora: number;
  trade?: TradeDaRegua | null;
  criarAlerta: (preco: number, direcao: Direcao) => Promise<void>;
  /** Ausente = B3. */
  mercado?: Mercado;
};

/** Verde/vermelho de direcao de preco -- mesma leitura do resto da ficha. */
function corDaVariacao(v: number): string {
  return v >= 0 ? "text-alta" : "text-baixa";
}

/**
 * O painel da regua: so aparece com a medicao FIXADA (inicio e fim marcados)
 * e para quem esta logado -- deslogado, o rotulo desenhado no proprio grafico
 * ja basta, sem espaco para o botao de criar alerta mesmo.
 *
 * Fica sempre abaixo do grafico, nunca por cima dos candles -- em 390px nao
 * ha espaco para um popup flutuante.
 */
export function PainelDaRegua({ nivel, agora, trade = null, criarAlerta, mercado = "b3" }: Props) {
  const [criando, setCriando] = useState(false);
  const [criado, setCriado] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const r = medirNivel({ agora, nivel, trade });

  async function aoClicarCriarAlerta() {
    setCriando(true);
    setErro(null);
    try {
      await criarAlerta(nivel, r.direcao);
      setCriado(nivel);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "não foi possível criar o alerta");
    } finally {
      setCriando(false);
    }
  }

  return (
    <div className="flex flex-col gap-2.5 rounded-2xl bg-painel-2 p-3.5">
      <span className="num text-[15px] font-extrabold">no ponto final {preco(mercado, nivel)}</span>

      {r.trade && (
        <span className="text-[12px] font-semibold text-tinta-2">
          seu trade nesse preço:{" "}
          <strong className={`num ${corDaVariacao(r.trade.inteiro.resultado)}`}>
            {valorComSinal(mercado, r.trade.inteiro.resultado)} ({percentual(r.trade.inteiro.resultadoPct, 2)})
          </strong>
        </span>
      )}

      <div className="flex flex-col gap-1.5">
        {criado === nivel ? (
          <span className="text-[12px] font-bold text-acento">
            Alerta criado em {preco(mercado, nivel)}.
          </span>
        ) : (
          <button
            type="button"
            onClick={aoClicarCriarAlerta}
            disabled={criando}
            className="toque h-10 self-start rounded-full bg-primario px-4 text-[12px] font-bold text-primario-tinta transition-opacity disabled:opacity-40"
          >
            {criando ? "Criando…" : `Criar alerta em ${preco(mercado, nivel)}`}
          </button>
        )}
        {erro && <span className="text-[11px] font-semibold text-baixa">{erro}</span>}
      </div>
    </div>
  );
}
