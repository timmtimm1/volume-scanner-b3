"use client";

/**
 * Registrar um trade clicando no grafico (pedido de 18/11/2026).
 *
 * Com o botao "Trade" ligado, a camada cobre o grafico. O clique pega o DIA do
 * candle (a coluna clicada; a direita do ultimo candle, hoje) e o PRECO (a
 * altura), e abre um rascunho: a linha do preco e, quando a operacao abre um
 * trade, a linha do stop -- as duas de arrastar, como a linha do alerta --, mais
 * um balao com Comprar ou Vender, a quantidade e o Confirmar. Clicar em outro
 * ponto muda o rascunho de lugar; Esc ou o ✕ cancelam.
 *
 * O stop comeca na minima do candle clicado (na compra) ou na maxima (na venda),
 * e a quantidade sugerida sai do perfil de risco (`/api/perfil`), como no
 * "Entrei" dos setups. Depois de mexer na quantidade a mao, ela nao muda mais
 * sozinha.
 *
 * As linhas sao desenhadas aqui (HTML por cima do canvas), na altura que
 * `priceToCoordinate` da; o grafico avisa cada redesenho por `aoRedesenhar` e a
 * camada remede no quadro seguinte -- o mesmo esquema de `CamadaDeAlertas`.
 */

import type { IChartApi, ISeriesApi, Logical } from "lightweight-charts";
import type { PointerEvent as EventoDePonteiro, RefObject } from "react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { data as fmtData, percentual } from "@/lib/formato";
import { loteNoMercado, numeroDoTexto, type Perfil } from "@/lib/lote";
import {
  nivelDoAlerta,
  preco as fmtPreco,
  precoParaCampo,
  quantidadeParaCampo,
  regrasDoDiario,
  sufixoDoMercado,
  valor,
  type Mercado,
} from "@/lib/mercado";
import type { LadoDoTrade, TipoDeOperacao } from "@/lib/posicao";
import type { Barra } from "@/lib/types";
import type { EntradaDeRegistro } from "@/lib/useTradesDoPapel";

/** Altura da faixa que pega o mouse em volta de cada linha, em pixels. */
const FAIXA = 12;
/** Largura do balao; a altura varia, e o encaixe usa uma estimativa folgada. */
const LARGURA_DO_BALAO = 252;
const ALTURA_DO_BALAO = 236;
/**
 * Abaixo desta largura de grafico (celular), o balao cobriria as linhas que se
 * arrastam: ele vai para baixo do grafico (`lugarDoBalao`).
 */
const LARGURA_ESTREITA = 560;

export type RegistroDeTrade = {
  /** O trade aberto do ativo (posicao negativa = vendido), ou null. */
  aberto: { lado: LadoDoTrade; quantidade: number } | null;
  registrar: (entrada: EntradaDeRegistro) => Promise<unknown>;
  salvando: boolean;
  erro: string | null;
  /** O dia de hoje no mercado (`diaDoMercado`): o do clique a direita do ultimo candle. */
  hoje: string;
};

type Props = RegistroDeTrade & {
  chart: RefObject<IChartApi | null>;
  serie: RefObject<ISeriesApi<"Candlestick"> | null>;
  /** Registra quem quer saber de cada redesenho do grafico; devolve o cancelamento. */
  aoRedesenhar: (ouvinte: () => void) => () => void;
  /** As barras do grafico, na ordem: o indice logico de cada uma e a posicao aqui. */
  barras: Barra[];
  mercado: Mercado;
  cores: { compra: string; venda: string; stop: string };
  /** Sai do modo: depois de confirmar, ou ao cancelar. */
  aoTerminar: () => void;
  /** Onde o balao vai no grafico estreito (um elemento logo abaixo dele). */
  lugarDoBalao: HTMLElement | null;
};

type Rascunho = {
  tipo: TipoDeOperacao;
  dia: string;
  /** Indice logico do candle clicado (pode passar do ultimo: hoje). */
  indice: number;
  preco: number;
  /** So quando a operacao abre um trade; null nas outras. */
  stop: number | null;
  /** O que foi digitado; so vale com `quantidadeManual`. */
  quantidade: string;
  /** A quantidade foi digitada: a sugestao do perfil para de valer. */
  quantidadeManual: boolean;
};

type Geometria = {
  largura: number;
  eixo: number;
  altura: number;
  yPreco: number | null;
  yStop: number | null;
  xDia: number | null;
};

/** O perfil de risco do mercado, lido uma vez quando o modo liga. */
function usePerfil(mercado: Mercado): Perfil | null {
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  useEffect(() => {
    let cancelado = false;
    fetch(`/api/perfil/${sufixoDoMercado(mercado)}`)
      .then(async (r) => {
        if (!r.ok) return;
        const corpo = (await r.json()) as { perfil: Perfil | null };
        if (!cancelado) setPerfil(corpo.perfil);
      })
      .catch(() => {
        // Sem perfil, so nao ha quantidade sugerida.
      });
    return () => {
      cancelado = true;
    };
  }, [mercado]);
  return perfil;
}

/**
 * O lote pelo risco. A conta de `lote.ts` e a da compra (stop abaixo); na venda
 * o stop esta acima, e o espelho dele do outro lado do preco tem a mesma
 * distancia -- logo o mesmo lote.
 */
function loteSugerido(
  mercado: Mercado,
  perfil: Perfil | null,
  tipo: TipoDeOperacao,
  preco: number,
  stop: number | null,
): number | null {
  if (!perfil || stop === null) return null;
  const stopDaConta = tipo === "compra" ? stop : 2 * preco - stop;
  const lote = loteNoMercado(mercado, { ...perfil, entrada: preco, stop: stopDaConta });
  return lote.quantidade > 0 ? lote.quantidade : null;
}

export function CamadaDeTrade({
  chart,
  serie,
  aoRedesenhar,
  barras,
  mercado,
  cores,
  aberto,
  registrar,
  salvando,
  erro,
  hoje,
  aoTerminar,
  lugarDoBalao,
}: Props) {
  const raiz = useRef<HTMLDivElement>(null);
  const regras = regrasDoDiario(mercado);
  const perfil = usePerfil(mercado);
  const [geometria, setGeometria] = useState<Geometria | null>(null);
  const [fantasma, setFantasma] = useState<{ preco: number; y: number; dia: string } | null>(null);
  const [rascunho, setRascunho] = useState<Rascunho | null>(null);
  const [arrasto, setArrasto] = useState<"preco" | "stop" | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  // A operacao abre um trade quando nao ha trade aberto. Com um aberto, ela
  // aumenta (mesmo lado) ou reduz (o outro lado) a posicao.
  const abreTrade = aberto === null;
  const ladoQueFecha: TipoDeOperacao | null = aberto
    ? aberto.lado === "compra"
      ? "venda"
      : "compra"
    : null;
  // Vender sem posicao e abrir vendido: so onde o mercado deixa.
  const podeVender = aberto !== null || regras.vendido !== null;

  const medirRef = useRef<() => void>(() => {});
  useLayoutEffect(() => {
    function medir() {
      const c = chart.current;
      const s = serie.current;
      const el = raiz.current;
      if (!c || !s || !el) return;
      const largura = c.timeScale().width();
      const altura = el.clientHeight - c.timeScale().height();
      const naVista = (y: number | null) => (y === null || y < 0 || y > altura ? null : y);
      const nova: Geometria = {
        largura,
        eixo: el.clientWidth - largura,
        altura,
        yPreco: rascunho ? naVista(s.priceToCoordinate(rascunho.preco)) : null,
        yStop:
          rascunho && rascunho.stop !== null ? naVista(s.priceToCoordinate(rascunho.stop)) : null,
        xDia: rascunho ? c.timeScale().logicalToCoordinate(rascunho.indice as Logical) : null,
      };
      setGeometria((atual) =>
        atual &&
        atual.largura === nova.largura &&
        atual.eixo === nova.eixo &&
        atual.altura === nova.altura &&
        atual.yPreco === nova.yPreco &&
        atual.yStop === nova.yStop &&
        atual.xDia === nova.xDia
          ? atual
          : nova,
      );
    }
    medirRef.current = medir;
    medir();
  }, [chart, serie, rascunho]);

  useEffect(() => {
    let quadro = 0;
    const agendar = () => {
      if (quadro) return;
      quadro = window.requestAnimationFrame(() => {
        quadro = 0;
        medirRef.current();
      });
    };
    const cancelar = aoRedesenhar(agendar);
    const observador = new ResizeObserver(agendar);
    if (raiz.current) observador.observe(raiz.current);
    return () => {
      cancelar();
      observador.disconnect();
      if (quadro) window.cancelAnimationFrame(quadro);
    };
  }, [aoRedesenhar]);

  // Esc: no meio de um arrasto so solta; fora dele, cancela o rascunho e o modo.
  useEffect(() => {
    function aoTeclar(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      if (arrasto) setArrasto(null);
      else aoTerminar();
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [arrasto, aoTerminar]);

  /** O preco na altura do ponteiro, ja nas casas do mercado; null fora da escala. */
  function precoNoPonteiro(clienteY: number): { preco: number; y: number } | null {
    const s = serie.current;
    const el = raiz.current;
    if (!s || !el) return null;
    const y = clienteY - el.getBoundingClientRect().top;
    const bruto = s.coordinateToPrice(y);
    if (bruto === null) return null;
    const p = nivelDoAlerta(mercado, Number(bruto));
    return p > 0 ? { preco: p, y } : null;
  }

  /** O candle na coluna do ponteiro: o indice e o dia (a direita do ultimo, hoje). */
  function diaNoPonteiro(clienteX: number): { indice: number; dia: string } | null {
    const c = chart.current;
    const el = raiz.current;
    if (!c || !el || barras.length === 0) return null;
    const x = clienteX - el.getBoundingClientRect().left;
    const logico = c.timeScale().coordinateToLogical(x);
    if (logico === null) return null;
    const indice = Math.max(0, Math.round(Number(logico)));
    if (indice >= barras.length) return { indice: barras.length, dia: hoje };
    // Um candle de hoje que ja esta nas barras (cripto ao vivo) e o proprio hoje.
    return { indice, dia: barras[indice].tradeDate > hoje ? hoje : barras[indice].tradeDate };
  }

  /** O stop que o rascunho propoe: alem da minima (compra) ou da maxima (venda) do candle. */
  function stopInicial(tipo: TipoDeOperacao, indice: number, preco: number): number {
    const candle = barras[Math.min(indice, barras.length - 1)];
    if (tipo === "compra") {
      const minima = candle?.low ?? null;
      return nivelDoAlerta(mercado, minima !== null && minima < preco ? minima : preco * 0.98);
    }
    const maxima = candle?.high ?? null;
    return nivelDoAlerta(mercado, maxima !== null && maxima > preco ? maxima : preco * 1.02);
  }

  /**
   * A quantidade no campo: a digitada, ou a sugerida pelo perfil. Calculada na
   * hora, e nao guardada: o perfil pode chegar depois do primeiro clique, e
   * arrastar o preco ou o stop refaz a sugestao sem mais nada.
   */
  function quantidadeNaTela(r: Rascunho): string {
    if (r.quantidadeManual) return r.quantidade;
    const q = loteSugerido(mercado, perfil, r.tipo, r.preco, r.stop);
    return q === null ? "" : quantidadeParaCampo(mercado, q);
  }

  function colocar(clienteX: number, clienteY: number) {
    const ponto = precoNoPonteiro(clienteY);
    const coluna = diaNoPonteiro(clienteX);
    if (!ponto || !coluna || !geometria || ponto.y > geometria.altura) return;
    setAviso(null);
    setRascunho((atual) => {
      // O tipo escolhido continua ao mudar de lugar; o primeiro clique propoe o
      // que faz sentido: sem trade, comprar; com trade, a operacao que o reduz.
      const tipo = atual?.tipo ?? ladoQueFecha ?? "compra";
      return {
        tipo,
        dia: coluna.dia,
        indice: coluna.indice,
        preco: ponto.preco,
        stop: abreTrade ? stopInicial(tipo, coluna.indice, ponto.preco) : null,
        quantidade: atual?.quantidade ?? "",
        quantidadeManual: atual?.quantidadeManual ?? false,
      };
    });
  }

  function trocarTipo(tipo: TipoDeOperacao) {
    setAviso(null);
    setRascunho((r) => {
      if (!r || r.tipo === tipo) return r;
      // O stop vai para o outro lado do preco, na mesma distancia.
      const stop =
        r.stop === null ? null : nivelDoAlerta(mercado, Math.max(2 * r.preco - r.stop, 0));
      return { ...r, tipo, stop: stop !== null && stop > 0 ? stop : null };
    });
  }

  function aoPressionar(e: EventoDePonteiro<HTMLElement>, qual: "preco" | "stop") {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    setArrasto(qual);
  }

  function aoArrastar(e: EventoDePonteiro<HTMLElement>) {
    if (!arrasto) return;
    const ponto = precoNoPonteiro(e.clientY);
    if (!ponto) return;
    setRascunho((r) => {
      if (!r) return r;
      return arrasto === "preco" ? { ...r, preco: ponto.preco } : { ...r, stop: ponto.preco };
    });
  }

  async function confirmar() {
    if (!rascunho) return;
    const quantidade = numeroDoTexto(quantidadeNaTela(rascunho));
    if (quantidade === null || quantidade <= 0) return setAviso("Digite a quantidade.");
    if (regras.casasDaQuantidade === 0 && !Number.isInteger(quantidade)) {
      return setAviso("A quantidade tem de ser um número inteiro de ações.");
    }
    const { tipo, preco, stop } = rascunho;
    if (abreTrade && stop !== null) {
      if (tipo === "compra" && !(stop < preco)) return setAviso("O stop precisa estar abaixo do preço da compra.");
      if (tipo === "venda" && !(stop > preco)) return setAviso("O stop precisa estar acima do preço da venda.");
    }
    if (aberto && tipo === ladoQueFecha && quantidade > Math.abs(aberto.quantidade) * (1 + 1e-9)) {
      return setAviso(`A posição é de ${quantidadeParaCampo(mercado, Math.abs(aberto.quantidade))}.`);
    }
    try {
      await registrar({
        tipo,
        data: rascunho.dia,
        quantidade,
        preco,
        ...(abreTrade && stop !== null ? { stop } : {}),
      });
      aoTerminar();
    } catch {
      // A mensagem do servidor chega em `erro` e aparece no balao.
    }
  }

  const etiqueta =
    "absolute flex h-[22px] items-center gap-1.5 rounded-md px-2 text-[11px] font-bold leading-none text-white shadow-sm";

  if (!geometria) return <div ref={raiz} className="pointer-events-none absolute inset-0" />;

  const corDoTipo = (t: TipoDeOperacao) => (t === "compra" ? cores.compra : cores.venda);
  const nomeDoTipo = (t: TipoDeOperacao): string => {
    if (aberto === null) return t === "compra" ? "Comprar" : "Vender";
    if (t === ladoQueFecha) return aberto.lado === "compra" ? "Vender" : "Recomprar";
    return aberto.lado === "compra" ? "Comprar mais" : "Vender mais";
  };

  // O risco do rascunho que abre trade: quantidade x distancia ate o stop.
  const qtdNaTela = rascunho ? quantidadeNaTela(rascunho) : "";
  const qtdNum = numeroDoTexto(qtdNaTela);
  const risco =
    rascunho && rascunho.stop !== null && qtdNum !== null && qtdNum > 0
      ? qtdNum * Math.abs(rascunho.preco - rascunho.stop)
      : null;

  // O balao fica ao lado da coluna clicada, dentro da area dos candles.
  const xBase = geometria.xDia ?? geometria.largura / 2;
  const cabeADireita = xBase + 14 + LARGURA_DO_BALAO <= geometria.largura - 4;
  const esquerda = Math.max(
    4,
    Math.min(cabeADireita ? xBase + 14 : xBase - 14 - LARGURA_DO_BALAO, geometria.largura - LARGURA_DO_BALAO - 4),
  );
  const yRef = geometria.yPreco ?? geometria.altura / 2;
  const topo = Math.max(
    4,
    Math.min(yRef > geometria.altura / 2 ? yRef - ALTURA_DO_BALAO - 10 : yRef + 14, geometria.altura - ALTURA_DO_BALAO),
  );

  // A faixa ao longo da linha e a etiqueta na ponta sao desenhadas em duas
  // passadas (todas as faixas, depois todas as etiquetas): com o preco e o stop
  // perto, a faixa de uma linha cobriria a etiqueta da outra. E as etiquetas
  // ficam em pontas opostas (preco a direita, stop a esquerda): com as linhas a
  // poucos pixels, uma etiqueta em cima da outra faria o arrasto pegar a errada.
  const faixa = (y: number, cor: string, qual: "preco" | "stop") => (
      <div
        key={`f${qual}`}
        className="pointer-events-auto absolute left-0 cursor-ns-resize"
        style={{ top: y - FAIXA / 2, height: FAIXA, width: geometria.largura, touchAction: "none" }}
        onPointerDown={(e) => aoPressionar(e, qual)}
        onPointerMove={aoArrastar}
        onPointerUp={() => setArrasto(null)}
        onPointerCancel={() => setArrasto(null)}
        aria-hidden
      >
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 border-t-2 border-dashed" style={{ borderColor: cor }} />
      </div>
  );
  const etiquetaDaLinha = (y: number, cor: string, rotulo: string, qual: "preco" | "stop") => (
      <div
        key={`e${qual}`}
        className={`${etiqueta} pointer-events-auto cursor-ns-resize`}
        style={{
          top: y - 11,
          ...(qual === "stop" ? { left: 6 } : { right: geometria.eixo + 6 }),
          background: cor,
          touchAction: "none",
        }}
        onPointerDown={(e) => aoPressionar(e, qual)}
        onPointerMove={aoArrastar}
        onPointerUp={() => setArrasto(null)}
        onPointerCancel={() => setArrasto(null)}
        title={qual === "stop" ? "Arraste para mudar o stop" : "Arraste para mudar o preço"}
      >
        <span className="num whitespace-nowrap">{rotulo}</span>
      </div>
  );

  const campo =
    "num h-8 w-full min-w-0 rounded-lg border border-linha-2 bg-painel px-2 text-[12px] font-bold outline-none focus:border-acento";

  const foraDoGrafico = geometria.largura < LARGURA_ESTREITA;
  const balao = rascunho && (
    <div
      className={`flex flex-col gap-2 rounded-2xl border border-linha-2 bg-painel p-3 ${
        foraDoGrafico ? "mt-2 w-full" : "absolute shadow-lg"
      }`}
      style={foraDoGrafico ? undefined : { left: esquerda, top: topo, width: LARGURA_DO_BALAO }}
      onPointerDown={(e) => e.stopPropagation()}
    >
            <div className="flex items-center justify-between gap-2">
              <span className="num text-[12px] font-extrabold">
                {fmtData(rascunho.dia)}
                {rascunho.dia === hoje && <span className="font-semibold text-tinta-3"> · hoje</span>}
              </span>
              <button
                type="button"
                onClick={aoTerminar}
                aria-label="Cancelar"
                className="flex h-6 w-6 items-center justify-center rounded-full text-tinta-3 hover:bg-painel-2 hover:text-tinta"
              >
                <svg width="9" height="9" viewBox="0 0 10 10" aria-hidden>
                  <path d="M2 2l6 6M8 2L2 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              </button>
            </div>

            <div className="flex rounded-xl border border-linha-2 p-0.5">
              {(["compra", "venda"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  disabled={t === "venda" && !podeVender}
                  title={t === "venda" && !podeVender ? "Na B3 o diário não registra venda a descoberto." : undefined}
                  onClick={() => trocarTipo(t)}
                  aria-pressed={rascunho.tipo === t}
                  className={`h-8 flex-1 rounded-[10px] text-[12px] font-bold transition-colors disabled:opacity-35 ${
                    rascunho.tipo === t ? "text-white shadow-sm" : "text-tinta-3"
                  }`}
                  style={rascunho.tipo === t ? { background: corDoTipo(t) } : undefined}
                >
                  {nomeDoTipo(t)}
                </button>
              ))}
            </div>

            <div className="grid grid-cols-2 items-end gap-2">
              <label className="flex min-w-0 flex-col gap-0.5">
                <span className="rotulo">Preço</span>
                <input
                  type="text"
                  inputMode="decimal"
                  // Chave pelo preco: arrastar a linha reescreve o campo.
                  key={`p${rascunho.preco}`}
                  defaultValue={precoParaCampo(mercado, rascunho.preco)}
                  onBlur={(e) => {
                    const v = numeroDoTexto(e.target.value);
                    if (v !== null && v > 0) setRascunho((r) => (r ? { ...r, preco: v } : r));
                  }}
                  className={campo}
                />
              </label>
              <label className="flex min-w-0 flex-col gap-0.5">
                <span className="flex items-center justify-between">
                  <span className="rotulo">Quantidade</span>
                  {aberto && rascunho.tipo === ladoQueFecha && (
                    <button
                      type="button"
                      onClick={() =>
                        setRascunho((r) =>
                          r
                            ? {
                                ...r,
                                quantidade: quantidadeParaCampo(mercado, Math.abs(aberto.quantidade)),
                                quantidadeManual: true,
                              }
                            : r,
                        )
                      }
                      className="text-[11px] font-bold text-acento hover:underline"
                    >
                      tudo
                    </button>
                  )}
                </span>
                <input
                  type="text"
                  inputMode={regras.casasDaQuantidade > 0 ? "decimal" : "numeric"}
                  value={qtdNaTela}
                  placeholder={regras.casasDaQuantidade > 0 ? "0,0153" : "100"}
                  onChange={(e) =>
                    setRascunho((r) => (r ? { ...r, quantidade: e.target.value, quantidadeManual: true } : r))
                  }
                  className={campo}
                />
              </label>
            </div>

            {rascunho.stop !== null && (
              <div className="flex flex-col gap-0.5 text-[11px] font-semibold text-tinta-3">
                <span>
                  stop <strong className="num text-tinta-2">{fmtPreco(mercado, rascunho.stop)}</strong>{" "}
                  (arraste a linha vermelha)
                </span>
                {risco !== null && (
                  <span>
                    risco <strong className="num text-tinta-2">{valor(mercado, risco)}</strong>
                    {perfil && perfil.capital > 0 && (
                      <> · {percentual(risco / perfil.capital, 1).replace("+", "")} do capital</>
                    )}
                  </span>
                )}
                {!perfil && <span>sem perfil de risco: digite a quantidade</span>}
              </div>
            )}

            {(aviso || erro) && <p className="text-[11px] font-semibold text-baixa">{aviso ?? erro}</p>}

            <button
              type="button"
              onClick={() => void confirmar()}
              disabled={salvando || qtdNaTela.trim() === ""}
              className="h-9 rounded-full text-[12px] font-extrabold text-white transition-opacity disabled:opacity-40"
              style={{ background: corDoTipo(rascunho.tipo) }}
            >
              {salvando ? "Salvando…" : `Confirmar ${nomeDoTipo(rascunho.tipo).toLowerCase()}`}
            </button>
    </div>
  );

  return (
    <div ref={raiz} className="absolute inset-0 z-20">
      {/* O fundo pega o clique: coloca (ou muda de lugar) o rascunho. */}
      <div
        className="absolute inset-0 cursor-crosshair"
        style={{ touchAction: "none" }}
        onPointerMove={(e) => {
          if (arrasto) return;
          const ponto = precoNoPonteiro(e.clientY);
          const coluna = diaNoPonteiro(e.clientX);
          setFantasma(ponto && coluna ? { ...ponto, dia: coluna.dia } : null);
        }}
        onPointerLeave={() => setFantasma(null)}
        onPointerDown={(e) => {
          if (e.button !== 0) return;
          colocar(e.clientX, e.clientY);
        }}
      />

      {!rascunho && fantasma && fantasma.y <= geometria.altura && (
        <>
          <div
            className="pointer-events-none absolute left-0 border-t border-dashed"
            style={{ top: fantasma.y, width: geometria.largura, borderColor: cores.compra }}
          />
          <div
            className={`${etiqueta} pointer-events-none`}
            style={{ top: fantasma.y - 11, right: geometria.eixo + 6, background: cores.compra }}
          >
            <span className="num whitespace-nowrap">
              {fmtData(fantasma.dia).slice(0, 5)} · {fmtPreco(mercado, fantasma.preco)}
            </span>
          </div>
        </>
      )}

      {!rascunho && (
        <div className="pointer-events-none absolute left-2 top-2 rounded-full bg-painel-2/90 px-2.5 py-1 text-[11px] font-semibold text-tinta-3">
          clique no candle, na altura do preço · Esc cancela
        </div>
      )}

      {rascunho && (
        <>
          {geometria.xDia !== null && (
            <div
              className="pointer-events-none absolute top-0 border-l border-dotted"
              style={{ left: geometria.xDia, height: geometria.altura, borderColor: corDoTipo(rascunho.tipo) }}
            />
          )}
          {geometria.yStop !== null && rascunho.stop !== null && faixa(geometria.yStop, cores.stop, "stop")}
          {geometria.yPreco !== null && faixa(geometria.yPreco, corDoTipo(rascunho.tipo), "preco")}
          {geometria.yStop !== null &&
            rascunho.stop !== null &&
            etiquetaDaLinha(
              geometria.yStop,
              cores.stop,
              `Stop ${fmtPreco(mercado, rascunho.stop)} · ${percentual(rascunho.stop / rascunho.preco - 1)}`,
              "stop",
            )}
          {geometria.yPreco !== null &&
            etiquetaDaLinha(
              geometria.yPreco,
              corDoTipo(rascunho.tipo),
              `${nomeDoTipo(rascunho.tipo)} ${fmtPreco(mercado, rascunho.preco)}`,
              "preco",
            )}

          {foraDoGrafico && lugarDoBalao ? createPortal(balao, lugarDoBalao) : balao}
        </>
      )}
    </div>
  );
}
