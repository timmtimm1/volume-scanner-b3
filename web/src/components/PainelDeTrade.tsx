"use client";

import Link from "next/link";
import { useId, useState } from "react";
import type { CandleDeHoje } from "@/lib/candle-de-hoje";
import { resultadoEmRDoTrade } from "@/lib/diario";
import { fmtR } from "@/lib/backtest-tela";
import { data as fmtData, percentual } from "@/lib/formato";
import { numeroDoTexto } from "@/lib/lote";
import {
  diaDoMercado,
  linkDoTrade,
  preco,
  precoParaCampo,
  quantidadeExata,
  quantidadeParaCampo,
  regrasDoDiario,
  textos,
  valor,
  type Mercado,
} from "@/lib/mercado";
import { marcarAgora } from "@/lib/posicao";
import { precoDeAgora } from "@/lib/preco-de-agora";
import { NOME_NO_DIARIO, ordemNoDiario } from "@/lib/setups-tela";
import type { EstadoDosTrades } from "@/lib/useTradesDoPapel";

type Props = {
  estado: EstadoDosTrades;
  /**
   * O candle de hoje que a ficha ja tem -- este cartao nao pede cotacao de
   * novo. Na moeda, o candle da Binance lido ao abrir a pagina.
   */
  hoje: CandleDeHoje | null;
  /** Ausente = B3. Em cripto: dolar, quantidade fracionada, dia UTC e a taxa da Binance. */
  mercado?: Mercado;
};

type FormAberto = "compra" | "venda" | null;

/**
 * "Seu trade": posicao aberta neste papel e como ela esta marcada a mercado
 * agora, com o formulario para registrar compra ou venda.
 *
 * Serve as duas fichas, a do papel e a da moeda (pedido de 18/11/2026). O que
 * muda de um mercado para o outro vem de `lib/mercado.ts`: na moeda o dinheiro
 * e em dolar, a quantidade e fracionada, o dia e o UTC do candle e a venda tem
 * o botao "tudo" (a taxa da Binance deixa um resto pequeno na conta).
 *
 * Dado pessoal: enquanto a sessao nao resolveu ou nao ha sessao, nao renderiza
 * nada -- nem um convite para entrar, ao contrario do painel de alerta. Um
 * visitante nao pode nem saber que a posicao existe.
 */
export function PainelDeTrade({ estado, hoje, mercado = "b3" }: Props) {
  const id = useId();
  const { autenticado, tradeAberto, salvando, erro, registrar } = estado;
  const regras = regrasDoDiario(mercado);
  const t = textos(mercado);
  const fracionada = regras.casasDaQuantidade > 0;
  const [formAberto, setFormAberto] = useState<FormAberto>(null);
  const [dataForm, setDataForm] = useState(() => diaDoMercado(mercado, new Date()));
  const [quantidadeForm, setQuantidadeForm] = useState("");
  const [precoForm, setPrecoForm] = useState("");
  // So na compra que abre o trade: ele e do trade, nao da operacao.
  const [setupForm, setSetupForm] = useState("");
  const [stopForm, setStopForm] = useState("");

  if (autenticado !== true) return null;

  const diaDeHoje = diaDoMercado(mercado, new Date());
  // Sem trade aberto, o preco de agora ainda serve para preencher a compra.
  const precoInfo = precoDeAgora(hoje, tradeAberto?.ultimoSnapshot ?? null, diaDeHoje);
  const marca = tradeAberto ? marcarAgora(tradeAberto, precoInfo?.preco ?? null) : null;
  const emAberto = marca && tradeAberto ? marca.resultado - tradeAberto.realizado : null;
  const emR = tradeAberto ? resultadoEmRDoTrade(tradeAberto, precoInfo?.preco ?? null) : null;
  // Sem trade aberto, a operacao abre um: compra, ou venda a descoberto onde o
  // mercado deixa (cripto). Com trade aberto, o lado que fecha e o oposto.
  const abreTrade = formAberto !== null && !tradeAberto;
  const vendido = tradeAberto?.lado === "venda";
  const ladoQueFecha = tradeAberto ? (vendido ? "compra" : "venda") : null;
  const taxaDoFuturo = regras.vendido?.taxa ?? null;
  // A operacao do formulario e de um trade vendido (aberto, ou a venda que abre um).
  const operacaoVendida = vendido || (abreTrade && formAberto === "venda");
  const nomeDaOperacao = (tipo: "compra" | "venda"): string =>
    !tradeAberto
      ? tipo === "compra"
        ? "Comprar"
        : "Vender a descoberto"
      : tipo === ladoQueFecha
        ? vendido
          ? "Recomprar"
          : "Vender"
        : vendido
          ? "Vender mais"
          : "Comprar mais";

  function abrirForm(tipo: "compra" | "venda") {
    setFormAberto(tipo);
    setDataForm(diaDeHoje);
    setQuantidadeForm("");
    setPrecoForm(precoInfo ? precoParaCampo(mercado, precoInfo.preco) : "");
    setSetupForm("");
    setStopForm("");
  }

  async function enviar() {
    if (!formAberto) return;
    // "0,0153" e "1.000" viram numero; texto que nao e numero vira NaN e o
    // servidor recusa com a mensagem certa.
    const quantidade = numeroDoTexto(quantidadeForm) ?? Number.NaN;
    const precoNum = numeroDoTexto(precoForm) ?? Number.NaN;
    // Texto que nao e numero segue como esta: o servidor recusa com a mensagem certa.
    const stop = numeroDoTexto(stopForm) ?? stopForm.trim();
    try {
      await registrar({
        tipo: formAberto,
        data: dataForm,
        quantidade,
        preco: precoNum,
        ...(abreTrade && setupForm !== "" ? { categoriaSetup: setupForm } : {}),
        ...(abreTrade && stop !== "" ? { stop } : {}),
      });
      setFormAberto(null);
    } catch {
      // erro ja fica em `estado.erro` e aparece abaixo do formulario.
    }
  }

  return (
    <div className="cartao flex flex-col gap-4 p-5">
      <div className="flex items-center justify-between">
        <span className="text-[16px] font-extrabold">Seu trade</span>
        {tradeAberto && (
          <Link
            href={linkDoTrade(mercado, tradeAberto.id)}
            className="text-[12px] font-bold text-acento hover:underline"
          >
            Ver trade
          </Link>
        )}
      </div>

      {tradeAberto ? (
        <>
          <div className="grid grid-cols-2 gap-2.5">
            <div className="flex flex-col gap-1 rounded-2xl bg-painel-2 p-3">
              <span className="text-[12px] font-bold text-tinta-3">
                {vendido ? "Vendido" : "Quantidade"}
              </span>
              <span className="num text-[18px] font-extrabold">
                {/* A posicao vendida e guardada negativa; aqui, o tamanho. */}
                {quantidadeExata(mercado, Math.abs(tradeAberto.quantidade))}
              </span>
            </div>
            <div className="flex flex-col gap-1 rounded-2xl bg-painel-2 p-3">
              <span className="text-[12px] font-bold text-tinta-3">
                {vendido ? "Preço médio de venda" : "Preço médio"}
              </span>
              <span className="num text-[18px] font-extrabold">
                {preco(mercado, tradeAberto.precoMedio)}
              </span>
            </div>
          </div>

          {precoInfo && (
            <div className="flex items-center justify-between rounded-xl bg-painel-2 px-3.5 py-2.5">
              <span className="num text-[12px] font-bold text-tinta-3">{precoInfo.rotulo}</span>
              <span className="num text-[15px] font-extrabold">{preco(mercado, precoInfo.preco)}</span>
            </div>
          )}

          {marca && (
            <div className="flex flex-col gap-2 border-t border-linha pt-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-semibold text-tinta-2">Resultado</span>
                <span
                  className={`num text-right text-[19px] font-extrabold leading-none ${
                    marca.resultado >= 0 ? "text-alta" : "text-baixa"
                  }`}
                >
                  {valor(mercado, marca.resultado)}{" "}
                  <span className="text-[13px] font-bold">{percentual(marca.resultadoPct)}</span>
                </span>
              </div>
              <div className="flex items-center justify-between text-[12px] font-semibold text-tinta-3">
                <span>
                  em R{" "}
                  {emR === null ? (
                    <strong className="num text-tinta-2">—</strong>
                  ) : (
                    <strong className={`num ${emR >= 0 ? "text-alta" : "text-baixa"}`}>{fmtR(emR)}</strong>
                  )}
                </span>
                {emR === null && <span>defina o stop no trade para ver em R</span>}
              </div>
              <div className="flex items-center justify-between text-[12px] font-semibold text-tinta-3">
                <span>
                  realizado <strong className="num text-tinta-2">{valor(mercado, tradeAberto.realizado)}</strong>
                </span>
                <span>
                  em aberto <strong className="num text-tinta-2">{valor(mercado, emAberto)}</strong>
                </span>
              </div>
            </div>
          )}

          {/* O mesmo lado primeiro (aumentar), o que fecha depois. */}
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => abrirForm(vendido ? "venda" : "compra")}
              className="toque h-11 rounded-full bg-primario text-[13px] font-bold text-primario-tinta"
            >
              {vendido ? "Vender mais" : "Comprar mais"}
            </button>
            <button
              type="button"
              onClick={() => abrirForm(vendido ? "compra" : "venda")}
              className="toque h-11 rounded-full border border-linha-2 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
            >
              {vendido ? "Recomprar" : "Vender"}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="text-[13px] leading-relaxed text-tinta-2">
            Nenhuma posição aberta {t.ativo === "moeda" ? "nesta moeda" : "neste papel"}.
          </p>
          <div className={`grid gap-2 ${regras.vendido ? "grid-cols-2" : "grid-cols-1"}`}>
            <button
              type="button"
              onClick={() => abrirForm("compra")}
              className="toque h-11 rounded-full bg-primario text-[13px] font-bold text-primario-tinta"
            >
              Registrar compra
            </button>
            {regras.vendido && (
              <button
                type="button"
                onClick={() => abrirForm("venda")}
                className="toque h-11 rounded-full border border-linha-2 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
              >
                Registrar venda
              </button>
            )}
          </div>
        </>
      )}

      {formAberto && (
        <div className="flex flex-col gap-2.5 rounded-2xl bg-painel-2 p-3.5">
          <span className="text-[13px] font-extrabold">{nomeDaOperacao(formAberto)}</span>
          {/* `items-end`: o "tudo" da venda deixa o rotulo da quantidade mais alto,
              e os campos da mesma linha ficam alinhados pela base. */}
          <div className="grid grid-cols-2 items-end gap-2.5">
            <label className="flex flex-col gap-1" htmlFor={`${id}-data`}>
              <span className="rotulo">Data</span>
              <input
                id={`${id}-data`}
                type="date"
                value={dataForm}
                max={diaDeHoje}
                onChange={(e) => setDataForm(e.target.value)}
                className="num toque h-10 rounded-xl border border-linha-2 bg-painel px-2.5 text-[13px] font-bold outline-none focus:border-acento"
              />
            </label>
            <label className="flex flex-col gap-1" htmlFor={`${id}-qtd`}>
              <span className="flex items-center justify-between gap-2">
                <span className="rotulo">Quantidade</span>
                {/* A posicao inteira: em cripto a taxa deixa um resto com 8 casas. */}
                {formAberto === ladoQueFecha && tradeAberto && (
                  <button
                    type="button"
                    onClick={() =>
                      setQuantidadeForm(quantidadeParaCampo(mercado, Math.abs(tradeAberto.quantidade)))
                    }
                    className="toque text-[11px] font-bold text-acento hover:underline"
                  >
                    tudo
                  </button>
                )}
              </span>
              <input
                id={`${id}-qtd`}
                type="text"
                inputMode={fracionada ? "decimal" : "numeric"}
                value={quantidadeForm}
                onChange={(e) => setQuantidadeForm(e.target.value)}
                placeholder={fracionada ? "0,0153" : "100"}
                className="num toque h-10 rounded-xl border border-linha-2 bg-painel px-2.5 text-[13px] font-bold outline-none focus:border-acento"
              />
            </label>
            <label className="col-span-2 flex flex-col gap-1" htmlFor={`${id}-preco`}>
              <span className="rotulo">Preço</span>
              <input
                id={`${id}-preco`}
                type="text"
                inputMode="decimal"
                value={precoForm}
                onChange={(e) => setPrecoForm(e.target.value)}
                placeholder="0,00"
                className="num toque h-10 rounded-xl border border-linha-2 bg-painel px-2.5 text-[13px] font-bold outline-none focus:border-acento"
              />
            </label>
            {abreTrade && (
              <>
                <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-setup`}>
                  <span className="rotulo">Setup (opcional)</span>
                  <select
                    id={`${id}-setup`}
                    value={setupForm}
                    onChange={(e) => setSetupForm(e.target.value)}
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
                <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-stop`}>
                  <span className="rotulo">Stop (opcional)</span>
                  <input
                    id={`${id}-stop`}
                    type="text"
                    inputMode="decimal"
                    value={stopForm}
                    onChange={(e) => setStopForm(e.target.value)}
                    placeholder="0,00"
                    className="num toque h-10 rounded-xl border border-linha-2 bg-painel px-2.5 text-[13px] font-bold outline-none focus:border-acento"
                  />
                </label>
              </>
            )}
          </div>
          {operacaoVendida && taxaDoFuturo !== null ? (
            <p className="text-[11px] font-semibold leading-relaxed text-tinta-3">
              Venda a descoberto, como nos futuros: {(taxaDoFuturo * 100).toLocaleString("pt-BR")}% de
              taxa sai em dólar a cada venda e recompra.
              {abreTrade && " O stop, se houver, fica acima do preço da venda."}
            </p>
          ) : regras.taxa > 0 && (
            <p className="text-[11px] font-semibold leading-relaxed text-tinta-3">
              {formAberto === "compra"
                ? `Na compra, ${(regras.taxa * 100).toLocaleString("pt-BR")}% sai das moedas recebidas: digite a quantidade comprada, e o diário desconta a taxa.`
                : `Na venda, ${(regras.taxa * 100).toLocaleString("pt-BR")}% sai dos dólares recebidos. Se sobrar um resto pequeno demais para vender, use “tudo” para fechar o trade.`}
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={enviar}
              disabled={salvando || quantidadeForm.trim() === "" || precoForm.trim() === ""}
              className="toque h-10 flex-1 rounded-full bg-primario text-[13px] font-bold text-primario-tinta transition-opacity disabled:opacity-40"
            >
              {salvando ? "Salvando…" : "Confirmar"}
            </button>
            <button
              type="button"
              onClick={() => setFormAberto(null)}
              className="toque h-10 rounded-full px-4 text-[13px] font-bold text-tinta-3 hover:text-tinta"
            >
              Cancelar
            </button>
          </div>
          <span className="text-[11px] font-semibold text-tinta-3">
            {dataForm && `${t.dia[0]} de ${fmtData(dataForm)}`}
            {t.notaDaData && ` · ${t.notaDaData}`}
          </span>
        </div>
      )}

      {erro && <p className="text-[12px] font-semibold text-baixa">{erro}</p>}
    </div>
  );
}
