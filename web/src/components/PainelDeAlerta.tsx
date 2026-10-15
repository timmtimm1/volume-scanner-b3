"use client";

import Link from "next/link";
import { useId, useRef, useState } from "react";
import type { Alerta } from "@/lib/alertas";
import { percentual, reais } from "@/lib/formato";
import { lerNivelDigitado } from "@/lib/nivel-do-alerta";
import type { EstadoDosAlertas } from "@/lib/useAlertasDoPapel";

/**
 * O nivel de um alerta que vigia, clicavel para digitar o valor exato -- para
 * quando arrastar a linha no grafico nao da a precisao que se quer.
 *
 * Enter ou sair do campo salva; Esc desiste. Valor que nao e preco nao salva:
 * no Enter o campo fica aberto e vermelho, ao sair ele volta ao que era.
 */
function NivelEditavel({
  alerta,
  mover,
}: {
  alerta: Alerta;
  mover: (id: number, preco: number) => Promise<void>;
}) {
  const [texto, setTexto] = useState<string | null>(null);
  // Enter e Esc fecham o campo, e fechar tira o foco: sem esta marca, o
  // `onBlur` que vem junto salvaria de novo -- ou salvaria o que o Esc mandou
  // descartar.
  const fechado = useRef(false);

  if (texto === null) {
    return (
      <button
        type="button"
        onClick={() => {
          fechado.current = false;
          setTexto(alerta.preco.toFixed(2).replace(".", ","));
        }}
        title="Clique para digitar o nível exato"
        className="num rounded-md px-1 font-extrabold text-tinta underline decoration-linha-2 decoration-dashed underline-offset-4 transition-colors hover:bg-linha hover:text-acento"
      >
        {reais(alerta.preco)}
      </button>
    );
  }

  const valor = lerNivelDigitado(texto);
  function salvar(fechandoPorFora: boolean) {
    if (fechado.current) return;
    if (valor === null) {
      if (fechandoPorFora) setTexto(null);
      return;
    }
    fechado.current = true;
    setTexto(null);
    if (valor !== alerta.preco) void mover(alerta.id, valor);
  }

  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-tinta-3">R$</span>
      <input
        autoFocus
        type="text"
        inputMode="decimal"
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        onFocus={(e) => e.currentTarget.select()}
        onKeyDown={(e) => {
          if (e.key === "Enter") salvar(false);
          if (e.key === "Escape") {
            fechado.current = true;
            setTexto(null);
          }
        }}
        onBlur={() => salvar(true)}
        aria-label={`Novo nível do alerta de ${reais(alerta.preco)}`}
        className={`num w-20 rounded-md border bg-painel px-1.5 py-0.5 font-extrabold text-tinta outline-none ${
          valor === null ? "border-baixa" : "border-acento"
        }`}
      />
    </span>
  );
}

/**
 * Criar e acompanhar os alertas de preco deste papel.
 *
 * No celular, o nivel pode ser digitado ou escolhido tocando no grafico, e ao
 * lado do valor vai a distancia do preco de agora. No computador o alerta e
 * criado e arrastado no proprio grafico, e este painel fica so com a lista --
 * onde o valor de cada alerta que vigia pode ser digitado.
 */
export function PainelDeAlerta({
  estado,
  computador = false,
}: {
  estado: EstadoDosAlertas;
  computador?: boolean;
}) {
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
    moverAlerta,
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

  const lista =
    alertas.length > 0 && (
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
              {computador && a.ativo ? (
                <NivelEditavel alerta={a} mover={moverAlerta} />
              ) : (
                <strong className="num text-tinta">{reais(a.preco)}</strong>
              )}
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
    );

  if (computador) {
    return (
      <div className="cartao flex flex-col gap-4 p-5">
        <div className="flex items-center justify-between">
          <span className="text-[16px] font-extrabold">Alerta de preço</span>
          <span className="text-[12px] font-semibold text-tinta-3">avisa no Telegram</span>
        </div>
        <p className="text-[13px] leading-relaxed text-tinta-2">
          Crie pelo botão <strong className="text-tinta">Alerta</strong> do gráfico, com um clique
          na altura do nível. Arraste a linha para mudar o nível, ou clique no valor abaixo para
          digitar o exato.
        </p>
        {erro && <p className="text-[12px] font-semibold text-baixa">{erro}</p>}
        {lista}
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

      {lista}
    </div>
  );
}
