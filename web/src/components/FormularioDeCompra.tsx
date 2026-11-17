"use client";

import { useId, useState } from "react";
import { data as fmtData } from "@/lib/formato";
import { loteNoMercado, numeroDoTexto, type Perfil } from "@/lib/lote";
import {
  diaDoMercado,
  precoParaCampo,
  quantidadeExata,
  quantidadeParaCampo,
  regrasDoDiario,
  sufixoDoMercado,
  textos,
  tickerValido,
  valor,
  type Mercado,
} from "@/lib/mercado";
import { NOME_NO_DIARIO, ordemNoDiario } from "@/lib/setups-tela";
import type { TradeDetalhe } from "@/lib/trades";
import { LoteDoSetup } from "./LoteDoSetup";

const campo =
  "num toque h-10 w-full min-w-0 rounded-xl border border-linha-2 bg-painel px-2.5 text-[13px] font-bold outline-none focus:border-acento";

type Props = {
  mercado: Mercado;
  /** O ativo, fixo (botao "Entrei"); null = a pessoa digita (compra a mao). */
  ticker: string | null;
  /** Data, preco e stop que o setup sugere; a compra a mao comeca vazia. */
  inicial?: { data?: string; preco?: number | null; stop?: number | null };
  /** Capital e risco, para sugerir a quantidade e mostrar o lote; null sem perfil. */
  perfil: Perfil | null;
  /** O que liga o trade a origem: `{ setupId, categoriaSetup }` ou `{ sinalId }`. */
  origem?: Record<string, unknown>;
  /** No "Entrei" o stop e obrigatorio (e o que faz o R); na compra a mao, opcional. */
  stopObrigatorio: boolean;
  /** Mostra a escolha do setup (compra a mao). */
  escolherSetup?: boolean;
  aoSalvar: (trade: TradeDetalhe) => void;
  aoCancelar: () => void;
  /** Recusa o trade gravado com uma mensagem (ex.: a compra caiu noutro trade aberto). */
  conferir?: (trade: TradeDetalhe) => string | null;
};

/**
 * O formulario curto de uma compra que abre trade: data, preco, quantidade e
 * stop. Em cripto a quantidade e fracionada, o dia e o UTC do candle e a linha
 * de baixo mostra quanto fica na conta depois da taxa da Binance -- o numero que
 * tem de bater com o saldo de la.
 */
export function FormularioDeCompra({
  mercado,
  ticker,
  inicial = {},
  perfil,
  origem = {},
  stopObrigatorio,
  escolherSetup = false,
  aoSalvar,
  aoCancelar,
  conferir,
}: Props) {
  const id = useId();
  const t = textos(mercado);
  const regras = regrasDoDiario(mercado);
  const hoje = diaDoMercado(mercado, new Date());

  const [tickerForm, setTickerForm] = useState("");
  const [dataForm, setDataForm] = useState(inicial.data ?? hoje);
  const [preco, setPreco] = useState(
    inicial.preco ? precoParaCampo(mercado, inicial.preco) : "",
  );
  const [stop, setStop] = useState(inicial.stop ? precoParaCampo(mercado, inicial.stop) : "");
  const [quantidade, setQuantidade] = useState(() => {
    if (!perfil || !inicial.preco || !inicial.stop) return "";
    const lote = loteNoMercado(mercado, { ...perfil, entrada: inicial.preco, stop: inicial.stop });
    return lote.quantidade > 0 ? quantidadeParaCampo(mercado, lote.quantidade) : "";
  });
  const [setup, setSetup] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const ativo = (ticker ?? tickerForm).trim().toUpperCase();
  const precoNum = numeroDoTexto(preco);
  const stopNum = numeroDoTexto(stop);
  const qtdNum = numeroDoTexto(quantidade);
  const fracionada = regras.casasDaQuantidade > 0;

  async function enviar() {
    if (!tickerValido(mercado, ativo)) {
      return setErro(`Digite o código (ex.: ${t.exemploDoAtivo}).`);
    }
    if (precoNum === null || precoNum <= 0) return setErro("Digite o preço da compra.");
    if (qtdNum === null || qtdNum <= 0) return setErro("Digite a quantidade.");
    if (!fracionada && !Number.isInteger(qtdNum)) {
      return setErro("A quantidade tem de ser um número inteiro de ações.");
    }
    if (stopObrigatorio && (stopNum === null || stopNum <= 0)) return setErro("Digite o stop.");
    if (stopNum !== null && stopNum >= precoNum) {
      return setErro("O stop precisa estar abaixo do preço da compra.");
    }
    setSalvando(true);
    setErro(null);
    try {
      const r = await fetch(`/api/trades/operacoes/${sufixoDoMercado(mercado)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: ativo,
          tipo: "compra",
          data: dataForm,
          quantidade: qtdNum,
          preco: precoNum,
          stop: stopNum,
          ...(escolherSetup && setup !== "" ? { categoriaSetup: setup } : {}),
          ...origem,
        }),
      });
      const corpo = (await r.json().catch(() => null)) as { trade?: TradeDetalhe; erro?: string } | null;
      if (!r.ok || !corpo?.trade) throw new Error(corpo?.erro ?? "não foi possível salvar");
      const recusa = conferir?.(corpo.trade) ?? null;
      if (recusa) throw new Error(recusa);
      aoSalvar(corpo.trade);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "algo deu errado");
    } finally {
      setSalvando(false);
    }
  }

  // O que a compra deixa na conta: em cripto, ja sem o 0,1% que sai da moeda.
  const resumo =
    precoNum !== null && qtdNum !== null && precoNum > 0 && qtdNum > 0
      ? {
          custo: valor(mercado, qtdNum * precoNum),
          fica:
            regras.taxa > 0
              ? `${quantidadeExata(mercado, qtdNum * (1 - regras.taxa))} ${ativo}`.trim()
              : null,
        }
      : null;

  return (
    <div className="flex flex-col gap-2.5">
      <div className="grid grid-cols-2 gap-2.5">
        {ticker === null && (
          <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-ativo`}>
            <span className="rotulo">{t.rotuloDoAtivo}</span>
            <input
              id={`${id}-ativo`}
              type="text"
              autoCapitalize="characters"
              value={tickerForm}
              onChange={(e) => setTickerForm(e.target.value)}
              placeholder={t.exemploDoAtivo}
              className={campo}
            />
          </label>
        )}
        <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-data`}>
          <span className="rotulo">Data</span>
          <input
            id={`${id}-data`}
            type="date"
            value={dataForm}
            max={hoje}
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
            placeholder="0,00"
            className={campo}
          />
        </label>
        <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-qtd`}>
          <span className="rotulo">Quantidade</span>
          <input
            id={`${id}-qtd`}
            type="text"
            inputMode={fracionada ? "decimal" : "numeric"}
            value={quantidade}
            onChange={(e) => setQuantidade(e.target.value)}
            placeholder={fracionada ? "0,0153" : "100"}
            className={campo}
          />
        </label>
        <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-stop`}>
          <span className="rotulo">{stopObrigatorio ? "Stop" : "Stop (opcional)"}</span>
          <input
            id={`${id}-stop`}
            type="text"
            inputMode="decimal"
            value={stop}
            onChange={(e) => setStop(e.target.value)}
            className={campo}
          />
        </label>
        {escolherSetup && (
          <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-setup`}>
            <span className="rotulo">Setup</span>
            <select
              id={`${id}-setup`}
              value={setup}
              onChange={(e) => setSetup(e.target.value)}
              className="toque h-10 w-full min-w-0 rounded-xl border border-linha-2 bg-painel px-2.5 text-[13px] font-bold outline-none focus:border-acento"
            >
              <option value="">Sem setup</option>
              {ordemNoDiario(regras.categoriasDoEstudo).map((c) => (
                <option key={c} value={c}>
                  {NOME_NO_DIARIO[c]}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {stopObrigatorio && (
        <LoteDoSetup perfil={perfil} entrada={precoNum} stop={stopNum} mercado={mercado} ticker={ativo} />
      )}

      {resumo && (
        <p className="num text-[12px] font-semibold text-tinta-3">
          custo {resumo.custo}
          {resumo.fica && (
            <>
              {" "}
              · ficam <strong className="text-tinta-2">{resumo.fica}</strong> na conta (a taxa de{" "}
              {(regras.taxa * 100).toLocaleString("pt-BR")}% sai da moeda)
            </>
          )}
        </p>
      )}

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
          onClick={aoCancelar}
          className="toque h-10 rounded-full px-4 text-[13px] font-bold text-tinta-3 hover:text-tinta"
        >
          Cancelar
        </button>
      </div>
      <span className="text-[11px] font-semibold text-tinta-3">
        {dataForm && `${t.dia[0]} de ${fmtData(dataForm)}`}
        {t.notaDaData && ` (${t.notaDaData})`}
      </span>

      {erro && (
        <p role="alert" className="text-[12px] font-bold text-baixa">
          {erro}
        </p>
      )}
    </div>
  );
}
