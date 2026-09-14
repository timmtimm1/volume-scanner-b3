"use client";

import Link from "next/link";
import { useId } from "react";
import { percentual, reais } from "@/lib/formato";
import type { EstadoDosAlertas } from "@/lib/useAlertasDoPapel";

/**
 * Criar e acompanhar os alertas de preco deste papel.
 *
 * O nivel pode ser digitado ou escolhido tocando no grafico. Ao lado do valor
 * vai a distancia do preco de agora, que e o que diz se o alerta e perto ou
 * longe.
 */
export function PainelDeAlerta({ estado }: { estado: EstadoDosAlertas }) {
  const id = useId();
  const {
    alertas,
    autenticado,
    escolhendo,
    setEscolhendo,
    preco,
    setPreco,
    direcao,
    setDirecao,
    salvando,
    erro,
    salvar,
    apagar,
    precoDeReferencia,
  } = estado;

  // Enquanto a sessao nao foi resolvida nao ha nada aqui: piscar um formulario e
  // esconde-lo em seguida seria pior do que aparecer um instante depois.
  if (autenticado === null) return null;

  if (!autenticado) {
    return (
      <div className="cartao flex flex-col gap-3 p-5">
        <span className="text-[16px] font-extrabold">Alerta de preço</span>
        <p className="text-[13px] leading-relaxed text-tinta-2">
          Escolha um nível no gráfico e receba no Telegram quando o preço chegar lá.
        </p>
        <Link
          href="/alertas"
          className="toque flex h-11 items-center justify-center rounded-full bg-primario text-[14px] font-bold text-primario-tinta"
        >
          Entrar para criar alertas
        </Link>
      </div>
    );
  }

  const valor = Number(preco.replace(",", "."));
  const distancia =
    precoDeReferencia !== null && Number.isFinite(valor) && valor > 0
      ? valor / precoDeReferencia - 1
      : null;

  return (
    <div className="cartao flex flex-col gap-4 p-5">
      <div className="flex items-center justify-between">
        <span className="text-[16px] font-extrabold">Alerta de preço</span>
        <span className="text-[12px] font-semibold text-tinta-3">avisa no Telegram</span>
      </div>

      <div className="flex flex-col gap-2">
        <span className="rotulo">Direção</span>
        <div className="grid grid-cols-2 gap-2">
          {(
            [
              ["acima", "Subir até"],
              ["abaixo", "Cair até"],
            ] as const
          ).map(([d, nome]) => (
            <button
              key={d}
              type="button"
              onClick={() => setDirecao(d)}
              aria-pressed={direcao === d}
              className={`h-11 rounded-xl text-[14px] font-bold transition-colors ${
                direcao === d
                  ? "border-[1.5px] border-acento bg-selecao text-acento"
                  : "bg-painel-2 text-tinta-2 hover:text-tinta"
              }`}
            >
              {nome}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor={`${id}-nivel`} className="rotulo">
          Nível
        </label>
        <div className="flex h-12 items-center gap-2 rounded-xl border border-linha bg-painel-2 px-3.5 focus-within:border-acento">
          <span className="text-[14px] font-bold text-tinta-3">R$</span>
          <input
            id={`${id}-nivel`}
            type="text"
            inputMode="decimal"
            value={preco}
            onChange={(e) => setPreco(e.target.value)}
            placeholder="0,00"
            className="num min-w-0 flex-1 bg-transparent text-[18px] font-extrabold outline-none placeholder:text-tinta-3"
          />
          {distancia !== null && (
            <span
              className={`num shrink-0 text-[12px] font-bold ${
                distancia >= 0 ? "text-alta" : "text-baixa"
              }`}
            >
              {percentual(distancia)} de agora
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => setEscolhendo(!escolhendo)}
          aria-pressed={escolhendo}
          className={`self-start text-[12px] font-bold transition-colors ${
            escolhendo ? "text-acento" : "text-tinta-3 hover:text-acento"
          }`}
        >
          {escolhendo ? "Tocando no gráfico… (cancelar)" : "Escolher a altura no gráfico"}
        </button>
      </div>

      <button
        type="button"
        onClick={salvar}
        disabled={salvando || preco.trim() === ""}
        className="toque h-12 rounded-full bg-primario text-[15px] font-extrabold text-primario-tinta transition-opacity disabled:opacity-40"
      >
        {salvando ? "Salvando…" : "Criar alerta"}
      </button>

      {erro && <p className="text-[12px] font-semibold text-baixa">{erro}</p>}

      {alertas.length > 0 && (
        <ul className="flex flex-col gap-2">
          {alertas.map((a) => (
            <li
              key={a.id}
              className="flex items-center gap-2.5 rounded-xl bg-painel-2 px-3.5 py-2.5 text-[13px]"
            >
              <span
                aria-hidden
                className={`h-2.5 w-2.5 shrink-0 rounded-full ${a.ativo ? "bg-acento" : "bg-linha-2"}`}
              />
              <span className="flex-1 font-semibold text-tinta-2">
                {a.direcao === "acima" ? "Subir até" : "Cair até"}{" "}
                <strong className="num text-tinta">{reais(a.preco)}</strong>
                {!a.ativo && (
                  <span className="num block text-[11px] text-tinta-3">
                    disparou a {reais(a.precoDisparo)}
                  </span>
                )}
              </span>
              <span className={`text-[12px] font-bold ${a.ativo ? "text-acento" : "text-tinta-3"}`}>
                {a.ativo ? "vigiando" : "disparou"}
              </span>
              <button
                type="button"
                onClick={() => apagar(a.id)}
                aria-label={`Apagar alerta de ${reais(a.preco)}`}
                className="flex h-8 w-8 items-center justify-center rounded-full text-tinta-3 transition-colors hover:bg-linha hover:text-baixa"
              >
                <svg width="11" height="11" viewBox="0 0 10 10" aria-hidden>
                  <path d="M2 2l6 6M8 2L2 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
