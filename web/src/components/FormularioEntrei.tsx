"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { diaNaB3 } from "@/lib/candle-de-hoje";
import { calcularLote, numeroDoTexto } from "@/lib/lote";
import { data as fmtData } from "@/lib/formato";
import {
  type ContextoDoDiario,
  gatilho,
  NOME_DO_SETUP,
  type Setup,
  stopDoSetup,
} from "@/lib/setups-tela";
import type { TradeDetalhe } from "@/lib/trades";
import { LoteDoSetup } from "./LoteDoSetup";

const campo =
  "num toque h-10 w-full min-w-0 rounded-xl border border-linha-2 bg-painel px-2.5 text-[13px] font-bold outline-none focus:border-acento";

/** O numero para o campo de texto, com virgula. */
const paraCampo = (v: number): string => String(v).replace(".", ",");

/**
 * "Entrei" num setup confirmado: o botao da linha e o formulario curto, ja
 * preenchido com o que o setup diz (data da confirmacao, entrada, o lote e o
 * stop). Salvar registra a compra ligada ao setup e ao stop.
 *
 * Se o setup ja virou trade, o botao e "Você entrou" e leva ao trade. Se o
 * papel ja tem um trade aberto, a compra nao abriria um trade novo (e e so ao
 * abrir que o setup e o stop sao gravados): o formulario avisa e manda para o
 * trade, em vez de registrar uma compra que perderia a ligacao.
 */
export function BotaoEntrei({ s, diario }: { s: Setup; diario: ContextoDoDiario }) {
  const id = useId();
  const router = useRouter();
  const { perfil } = diario;
  const entradaDoSetup = s.entrada ?? gatilho(s);
  const stopDoSetupAqui = stopDoSetup(s);

  const [aberto, setAberto] = useState(false);
  const [dataForm, setDataForm] = useState(s.confirmadoEm ?? diaNaB3(new Date()));
  const [preco, setPreco] = useState(paraCampo(entradaDoSetup));
  const [stop, setStop] = useState(paraCampo(stopDoSetupAqui));
  const [quantidade, setQuantidade] = useState(() => {
    const lote = calcularLote({ ...(perfil ?? { capital: null, riscoPct: null }), entrada: entradaDoSetup, stop: stopDoSetupAqui });
    return lote.quantidade > 0 ? String(lote.quantidade) : "";
  });
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [tradeNovo, setTradeNovo] = useState<number | null>(null);

  const tradeDoSetup = diario.tradePorSetup[s.id] ?? tradeNovo;
  const tradeAbertoDoPapel = diario.abertoPorTicker[s.ticker] ?? null;

  if (tradeDoSetup !== null) {
    return (
      <Link
        href={`/trades/${tradeDoSetup}`}
        className="toque inline-flex h-9 items-center rounded-full bg-selecao px-3.5 text-[12px] font-bold text-acento"
      >
        Você entrou
      </Link>
    );
  }

  const precoNum = numeroDoTexto(preco);
  const stopNum = numeroDoTexto(stop);
  const qtdNum = numeroDoTexto(quantidade);

  async function enviar() {
    if (precoNum === null || precoNum <= 0) return setErro("Digite o preço da compra.");
    if (qtdNum === null || !Number.isInteger(qtdNum) || qtdNum <= 0) {
      return setErro("A quantidade tem de ser um número inteiro de ações.");
    }
    if (stopNum === null || stopNum <= 0) return setErro("Digite o stop.");
    if (stopNum >= precoNum) return setErro("O stop precisa estar abaixo do preço da compra.");
    setSalvando(true);
    setErro(null);
    try {
      const r = await fetch("/api/trades/operacoes/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: s.ticker,
          tipo: "compra",
          data: dataForm,
          quantidade: qtdNum,
          preco: precoNum,
          stop: stopNum,
          setupId: s.id,
          categoriaSetup: s.categoria,
        }),
      });
      const corpo = (await r.json().catch(() => null)) as { trade?: TradeDetalhe; erro?: string } | null;
      if (!r.ok || !corpo?.trade) throw new Error(corpo?.erro ?? "não foi possível salvar");
      if (corpo.trade.setupId !== s.id) {
        // Outro trade do papel abriu no meio do caminho: a compra entrou nele.
        throw new Error("o papel já tinha um trade aberto: a compra entrou nele, sem ligar ao setup");
      }
      setTradeNovo(corpo.trade.id);
      setAberto(false);
      router.refresh();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "algo deu errado");
    } finally {
      setSalvando(false);
    }
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
          <span className="text-[13px] font-extrabold">
            Registrar a compra de {s.ticker} · {NOME_DO_SETUP[s.categoria]}
          </span>

          {tradeAbertoDoPapel !== null ? (
            <p className="text-[13px] font-semibold text-tinta-2">
              Você já tem um trade aberto de {s.ticker}. Registre a compra por lá.{" "}
              <Link href={`/trades/${tradeAbertoDoPapel}`} className="font-bold text-acento hover:underline">
                Abrir o trade
              </Link>
            </p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2.5">
                <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-data`}>
                  <span className="rotulo">Data</span>
                  <input
                    id={`${id}-data`}
                    type="date"
                    value={dataForm}
                    max={diaNaB3(new Date())}
                    onChange={(e) => setDataForm(e.target.value)}
                    className={campo}
                  />
                </label>
                <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-preco`}>
                  <span className="rotulo">Preço</span>
                  <input
                    id={`${id}-preco`}
                    type="text"
                    inputMode="decimal"
                    value={preco}
                    onChange={(e) => setPreco(e.target.value)}
                    className={campo}
                  />
                </label>
                <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-qtd`}>
                  <span className="rotulo">Quantidade</span>
                  <input
                    id={`${id}-qtd`}
                    type="text"
                    inputMode="numeric"
                    value={quantidade}
                    onChange={(e) => setQuantidade(e.target.value)}
                    placeholder="100"
                    className={campo}
                  />
                </label>
                <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-stop`}>
                  <span className="rotulo">Stop</span>
                  <input
                    id={`${id}-stop`}
                    type="text"
                    inputMode="decimal"
                    value={stop}
                    onChange={(e) => setStop(e.target.value)}
                    className={campo}
                  />
                </label>
              </div>

              <LoteDoSetup perfil={perfil} entrada={precoNum} stop={stopNum} />

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={enviar}
                  disabled={salvando}
                  className="toque h-10 flex-1 rounded-full bg-primario text-[13px] font-bold text-primario-tinta disabled:opacity-40"
                >
                  {salvando ? "Salvando…" : "Confirmar"}
                </button>
                <button
                  type="button"
                  onClick={() => setAberto(false)}
                  className="toque h-10 rounded-full px-4 text-[13px] font-bold text-tinta-3 hover:text-tinta"
                >
                  Cancelar
                </button>
              </div>
              <span className="text-[11px] font-semibold text-tinta-3">
                {dataForm && `pregão de ${fmtData(dataForm)}`}
              </span>
            </>
          )}

          {erro && (
            <p role="alert" className="text-[12px] font-bold text-baixa">
              {erro}
            </p>
          )}
        </div>
      )}
    </>
  );
}
