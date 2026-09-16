"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { diaNaB3, type CandleDeHoje } from "@/lib/candle-de-hoje";
import { data as fmtData, numero, percentual, reais } from "@/lib/formato";
import { marcarAgora } from "@/lib/posicao";
import { precoDeAgora } from "@/lib/preco-de-agora";
import type { EstadoDosTrades } from "@/lib/useTradesDoPapel";

type Props = {
  estado: EstadoDosTrades;
  /** O candle de hoje que `FichaDoPapel` ja busca -- este cartao nao pede cotacao de novo. */
  hoje: CandleDeHoje | null;
};

type FormAberto = "compra" | "venda" | null;

/**
 * "Seu trade": posicao aberta neste papel e como ela esta marcada a mercado
 * agora, com o formulario para registrar compra ou venda.
 *
 * Dado pessoal: enquanto a sessao nao resolveu ou nao ha sessao, nao renderiza
 * nada -- nem um convite para entrar, ao contrario do painel de alerta. Um
 * visitante nao pode nem saber que a posicao existe.
 */
export function PainelDeTrade({ estado, hoje }: Props) {
  const id = useId();
  const { autenticado, tradeAberto, salvando, erro, registrar } = estado;
  const [formAberto, setFormAberto] = useState<FormAberto>(null);
  const [dataForm, setDataForm] = useState(() => diaNaB3(new Date()));
  const [quantidadeForm, setQuantidadeForm] = useState("");
  const [precoForm, setPrecoForm] = useState("");

  if (autenticado !== true) return null;

  const precoInfo = tradeAberto ? precoDeAgora(hoje, tradeAberto.ultimoSnapshot) : null;
  const marca = tradeAberto ? marcarAgora(tradeAberto, precoInfo?.preco ?? null) : null;
  const emAberto = marca && tradeAberto ? marca.resultado - tradeAberto.realizado : null;

  function abrirForm(tipo: "compra" | "venda") {
    setFormAberto(tipo);
    setDataForm(diaNaB3(new Date()));
    setQuantidadeForm("");
    setPrecoForm(precoInfo ? precoInfo.preco.toFixed(2) : "");
  }

  async function enviar() {
    if (!formAberto) return;
    const quantidade = Number(quantidadeForm);
    const preco = Number(precoForm.replace(",", "."));
    try {
      await registrar({ tipo: formAberto, data: dataForm, quantidade, preco });
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
            href={`/trades/${tradeAberto.id}`}
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
              <span className="text-[12px] font-bold text-tinta-3">Quantidade</span>
              <span className="num text-[18px] font-extrabold">
                {numero(tradeAberto.quantidade, 0)}
              </span>
            </div>
            <div className="flex flex-col gap-1 rounded-2xl bg-painel-2 p-3">
              <span className="text-[12px] font-bold text-tinta-3">Preço médio</span>
              <span className="num text-[18px] font-extrabold">
                {reais(tradeAberto.precoMedio)}
              </span>
            </div>
          </div>

          {precoInfo && (
            <div className="flex items-center justify-between rounded-xl bg-painel-2 px-3.5 py-2.5">
              <span className="num text-[12px] font-bold text-tinta-3">{precoInfo.rotulo}</span>
              <span className="num text-[15px] font-extrabold">{reais(precoInfo.preco)}</span>
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
                  {reais(marca.resultado)}{" "}
                  <span className="text-[13px] font-bold">{percentual(marca.resultadoPct)}</span>
                </span>
              </div>
              <div className="flex items-center justify-between text-[12px] font-semibold text-tinta-3">
                <span>
                  realizado <strong className="num text-tinta-2">{reais(tradeAberto.realizado)}</strong>
                </span>
                <span>
                  em aberto <strong className="num text-tinta-2">{reais(emAberto)}</strong>
                </span>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => abrirForm("compra")}
              className="toque h-11 rounded-full bg-primario text-[13px] font-bold text-primario-tinta"
            >
              Comprar mais
            </button>
            <button
              type="button"
              onClick={() => abrirForm("venda")}
              className="toque h-11 rounded-full border border-linha-2 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
            >
              Vender
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="text-[13px] leading-relaxed text-tinta-2">
            Nenhuma posição aberta neste papel.
          </p>
          <button
            type="button"
            onClick={() => abrirForm("compra")}
            className="toque h-11 rounded-full bg-primario text-[13px] font-bold text-primario-tinta"
          >
            Registrar compra
          </button>
        </>
      )}

      {formAberto && (
        <div className="flex flex-col gap-2.5 rounded-2xl bg-painel-2 p-3.5">
          <span className="text-[13px] font-extrabold">
            {formAberto === "compra" ? "Comprar" : "Vender"}
          </span>
          <div className="grid grid-cols-2 gap-2.5">
            <label className="flex flex-col gap-1" htmlFor={`${id}-data`}>
              <span className="rotulo">Data</span>
              <input
                id={`${id}-data`}
                type="date"
                value={dataForm}
                max={diaNaB3(new Date())}
                onChange={(e) => setDataForm(e.target.value)}
                className="num toque h-10 rounded-xl border border-linha-2 bg-painel px-2.5 text-[13px] font-bold outline-none focus:border-acento"
              />
            </label>
            <label className="flex flex-col gap-1" htmlFor={`${id}-qtd`}>
              <span className="rotulo">Quantidade</span>
              <input
                id={`${id}-qtd`}
                type="text"
                inputMode="numeric"
                value={quantidadeForm}
                onChange={(e) => setQuantidadeForm(e.target.value)}
                placeholder="100"
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
          </div>
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
            {dataForm && `pregão de ${fmtData(dataForm)}`}
          </span>
        </div>
      )}

      {erro && <p className="text-[12px] font-semibold text-baixa">{erro}</p>}
    </div>
  );
}
