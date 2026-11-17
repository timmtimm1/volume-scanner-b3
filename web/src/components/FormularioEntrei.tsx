"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import {
  diaDoMercado,
  gatilhoNoMercado,
  linkDoTrade,
  stopNoMercado,
  type Mercado,
} from "@/lib/mercado";
import type { SinalDoEstudo } from "@/lib/sinais-estudo";
import {
  CATEGORIA_DO_SINAL,
  type ContextoDoDiario,
  NOME_DO_SETUP,
  NOME_NO_DIARIO,
  type Setup,
} from "@/lib/setups-tela";
import type { TradeDetalhe } from "@/lib/trades";
import { FormularioDeCompra } from "./FormularioDeCompra";

/**
 * O botao "Entrei" e o que ele abre. Igual para o setup da aba e para o sinal
 * do estudo de cripto: se a origem ja virou trade, o botao e "Você entrou" e
 * leva ao trade; se o ativo ja tem trade aberto, a compra nao abriria um trade
 * novo (e e so ao abrir que a origem e o stop sao gravados), entao o formulario
 * avisa e manda para o trade, em vez de registrar uma compra que perderia a
 * ligacao.
 */
function Entrei({
  mercado,
  ticker,
  titulo,
  tradeDaOrigem,
  tradeAberto,
  children,
}: {
  mercado: Mercado;
  ticker: string;
  titulo: string;
  tradeDaOrigem: number | null;
  tradeAberto: number | null;
  children: (fechar: () => void) => ReactNode;
}) {
  const [aberto, setAberto] = useState(false);

  if (tradeDaOrigem !== null) {
    return (
      <Link
        href={linkDoTrade(mercado, tradeDaOrigem)}
        className="toque inline-flex h-9 items-center rounded-full bg-selecao px-3.5 text-[12px] font-bold text-acento"
      >
        Você entrou
      </Link>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        className="toque h-9 rounded-full bg-primario px-3.5 text-[12px] font-bold text-primario-tinta"
      >
        Entrei
      </button>

      {aberto && (
        <div className="flex basis-full flex-col gap-2.5 rounded-2xl bg-painel-2 p-3.5">
          <span className="text-[13px] font-extrabold">{titulo}</span>
          {tradeAberto !== null ? (
            <p className="text-[13px] font-semibold text-tinta-2">
              Você já tem um trade aberto de {ticker}. Registre a compra por lá.{" "}
              <Link
                href={linkDoTrade(mercado, tradeAberto)}
                className="font-bold text-acento hover:underline"
              >
                Abrir o trade
              </Link>
            </p>
          ) : (
            children(() => setAberto(false))
          )}
        </div>
      )}
    </>
  );
}

/**
 * "Entrei" num setup da aba (B3 ou cripto): data, entrada, lote e stop que o
 * setup diz. Entrada e stop sao um passo acima da maxima e abaixo da minima no
 * passo do mercado: o centavo na B3 (as contas de `gatilho` e `stopDoSetup`), a
 * quinta casa significativa em cripto.
 */
export function BotaoEntrei({ s, diario }: { s: Setup; diario: ContextoDoDiario }) {
  const router = useRouter();
  const mercado = diario.mercado ?? "b3";
  const [tradeNovo, setTradeNovo] = useState<number | null>(null);
  const tradeDoSetup = diario.tradePorSetup[s.id] ?? tradeNovo;

  return (
    <Entrei
      mercado={mercado}
      ticker={s.ticker}
      titulo={`Registrar a compra de ${s.ticker} · ${NOME_DO_SETUP[s.categoria]}`}
      tradeDaOrigem={tradeDoSetup}
      tradeAberto={diario.abertoPorTicker[s.ticker] ?? null}
    >
      {(fechar) => (
        <FormularioDeCompra
          mercado={mercado}
          ticker={s.ticker}
          inicial={{
            data: s.confirmadoEm ?? diaDoMercado(mercado, new Date()),
            preco: s.entrada ?? gatilhoNoMercado(mercado, s.maxima),
            stop: stopNoMercado(mercado, s.minima),
          }}
          perfil={diario.perfil}
          origem={{ setupId: s.id, categoriaSetup: s.categoria }}
          stopObrigatorio
          conferir={(t: TradeDetalhe) =>
            t.setupId !== s.id
              ? "o ativo já tinha um trade aberto: a compra entrou nele, sem ligar ao setup"
              : null
          }
          aoSalvar={(t) => {
            setTradeNovo(t.id);
            fechar();
            router.refresh();
          }}
          aoCancelar={fechar}
        />
      )}
    </Entrei>
  );
}

/**
 * "Entrei" no sinal de compra do estudo de cripto (reversao no RSI). A entrada
 * do estudo e a abertura do candle seguinte ao sinal; enquanto ela nao existe,
 * o formulario sugere o fechamento do sinal. Sinal de venda nao tem botao: o
 * diario so tem compra.
 */
export function BotaoEntreiNoSinal({ s, diario }: { s: SinalDoEstudo; diario: ContextoDoDiario }) {
  const router = useRouter();
  const [tradeNovo, setTradeNovo] = useState<number | null>(null);
  const categoria = CATEGORIA_DO_SINAL[s.setup];
  if (s.lado !== "compra" || !categoria) return null;
  const mercado = diario.mercado ?? "cripto";
  const tradeDoSinal = diario.tradePorSinal?.[s.id] ?? tradeNovo;

  return (
    <Entrei
      mercado={mercado}
      ticker={s.moeda}
      titulo={`Registrar a compra de ${s.moeda} · ${NOME_NO_DIARIO[categoria]}`}
      tradeDaOrigem={tradeDoSinal}
      tradeAberto={diario.abertoPorTicker[s.moeda] ?? null}
    >
      {(fechar) => (
        <FormularioDeCompra
          mercado={mercado}
          ticker={s.moeda}
          inicial={{
            data: diaDoMercado(mercado, new Date()),
            preco: s.entrada ?? s.fechamento,
            stop: s.stop,
          }}
          perfil={diario.perfil}
          origem={{ sinalId: s.id }}
          stopObrigatorio
          conferir={(t: TradeDetalhe) =>
            t.sinalEstudoId !== s.id
              ? "a moeda já tinha um trade aberto: a compra entrou nele, sem ligar ao sinal"
              : null
          }
          aoSalvar={(t) => {
            setTradeNovo(t.id);
            fechar();
            router.refresh();
          }}
          aoCancelar={fechar}
        />
      )}
    </Entrei>
  );
}
