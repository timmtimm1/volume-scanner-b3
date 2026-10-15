"use client";

/**
 * Os alertas editaveis no proprio grafico, so no computador.
 *
 * O lightweight-charts desenha a linha de cada alerta (tracejada, com o preco
 * no eixo), mas nao deixa arrasta-la nem clicar nela. Esta camada fica por
 * cima do canvas, na mesma posicao de cada linha, e da a ela:
 *
 * - uma faixa fina e invisivel ao longo da linha, que pega o mouse e arrasta;
 * - uma etiqueta na ponta direita, com a direcao, o nivel, a distancia do preco
 *   de agora e o ✕ de apagar.
 *
 * No modo de criar, a camada cobre o grafico: uma linha fantasma segue o mouse
 * mostrando o nivel e a direcao que o alerta vai ter, e o clique cria.
 *
 * A posicao das faixas sai de `priceToCoordinate`, e muda sempre que o grafico
 * e reenquadrado (rolar, dar zoom, autoescala, redimensionar). O grafico avisa
 * cada redesenho por `aoRedesenhar`; a camada remede no quadro seguinte. Sem
 * laco rodando quando nada se mexe.
 */

import type { IChartApi, ISeriesApi } from "lightweight-charts";
import type { PointerEvent as EventoDePonteiro, RefObject } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Alerta, Direcao } from "@/lib/alertas";
import { percentual, reais } from "@/lib/formato";
import { direcaoDoNivel, nivelEmCentavos } from "@/lib/nivel-do-alerta";

/** Altura da faixa que pega o mouse em volta da linha, em pixels. */
const FAIXA = 10;

type Props = {
  chart: RefObject<IChartApi | null>;
  serie: RefObject<ISeriesApi<"Candlestick"> | null>;
  /** Registra quem quer saber de cada redesenho do grafico; devolve o cancelamento. */
  aoRedesenhar: (ouvinte: () => void) => () => void;
  /** So os que estao vigiando: o disparado nao aparece no grafico do computador. */
  alertas: Alerta[];
  /** O preco de agora, que decide a direcao. Null num papel sem barra. */
  referencia: number | null;
  criando: boolean;
  aoCriar: (preco: number) => void;
  aoMover: (id: number, preco: number) => void;
  aoApagar: (id: number) => void;
  /** Move a linha desenhada no canvas durante o arrasto, antes de salvar. */
  moverLinha: (id: number, preco: number) => void;
  cor: string;
};

type Geometria = {
  /** Largura da area dos candles, sem o eixo de preco. */
  largura: number;
  /** Largura do eixo de preco, a direita. */
  eixo: number;
  /** Altura da area dos candles, sem o eixo de tempo. */
  altura: number;
  /** Altura de cada alerta na tela, ou null se o nivel esta fora da vista. */
  ys: Record<number, number | null>;
};

type Arrasto = { id: number; inicial: number; preco: number };

function seta(direcao: Direcao): string {
  return direcao === "acima" ? "▲" : "▼";
}

export function CamadaDeAlertas({
  chart,
  serie,
  aoRedesenhar,
  alertas,
  referencia,
  criando,
  aoCriar,
  aoMover,
  aoApagar,
  moverLinha,
  cor,
}: Props) {
  const raiz = useRef<HTMLDivElement>(null);
  const [geometria, setGeometria] = useState<Geometria | null>(null);
  const [arrasto, setArrasto] = useState<Arrasto | null>(null);
  // O nivel sob o mouse no modo de criar, e a altura dele na tela.
  const [fantasma, setFantasma] = useState<{ preco: number; y: number } | null>(null);

  const precoNaTela = useCallback(
    (a: Alerta) => (arrasto?.id === a.id ? arrasto.preco : a.preco),
    [arrasto],
  );

  // A ultima versao de `medir`, para o ouvinte do redesenho (assinado uma vez)
  // usar sempre a lista e o arrasto de agora.
  const medirRef = useRef<() => void>(() => {});

  useLayoutEffect(() => {
    function medir() {
      const c = chart.current;
      const s = serie.current;
      const el = raiz.current;
      if (!c || !s || !el) return;
      const largura = c.timeScale().width();
      const altura = el.clientHeight - c.timeScale().height();
      const ys: Record<number, number | null> = {};
      for (const a of alertas) {
        const y = s.priceToCoordinate(precoNaTela(a));
        ys[a.id] = y === null || y < 0 || y > altura ? null : y;
      }
      const nova: Geometria = { largura, eixo: el.clientWidth - largura, altura, ys };
      // Igual a anterior, nada muda: rolar na horizontal sem a autoescala mexer
      // nao renderiza a camada a cada quadro.
      setGeometria((atual) =>
        atual &&
        atual.largura === nova.largura &&
        atual.eixo === nova.eixo &&
        atual.altura === nova.altura &&
        alertas.every((a) => atual.ys[a.id] === nova.ys[a.id]) &&
        Object.keys(atual.ys).length === alertas.length
          ? atual
          : nova,
      );
    }
    medirRef.current = medir;
    medir();
  }, [chart, serie, alertas, precoNaTela]);

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

  /** O preco (ao centavo) na altura do ponteiro, ou null fora da escala. */
  function precoNoPonteiro(clienteY: number): { preco: number; y: number } | null {
    const s = serie.current;
    const el = raiz.current;
    if (!s || !el) return null;
    const y = clienteY - el.getBoundingClientRect().top;
    const bruto = s.coordinateToPrice(y);
    if (bruto === null) return null;
    const preco = nivelEmCentavos(Number(bruto));
    return preco > 0 ? { preco, y } : null;
  }

  // Esc no meio do arrasto devolve a linha ao lugar, sem salvar.
  useEffect(() => {
    if (!arrasto) return;
    const { id, inicial } = arrasto;
    function aoTeclar(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      moverLinha(id, inicial);
      setArrasto(null);
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [arrasto, moverLinha]);

  function aoPressionar(e: EventoDePonteiro<HTMLElement>, a: Alerta) {
    if (e.button !== 0) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    setArrasto({ id: a.id, inicial: a.preco, preco: a.preco });
  }

  function aoArrastar(e: EventoDePonteiro<HTMLElement>) {
    if (!arrasto) return;
    const ponto = precoNoPonteiro(e.clientY);
    if (!ponto || ponto.preco === arrasto.preco) return;
    moverLinha(arrasto.id, ponto.preco);
    setArrasto({ ...arrasto, preco: ponto.preco });
  }

  function aoSoltar() {
    if (!arrasto) return;
    if (arrasto.preco !== arrasto.inicial) aoMover(arrasto.id, arrasto.preco);
    setArrasto(null);
  }

  const distancia = (preco: number) =>
    referencia !== null && referencia > 0 ? percentual(preco / referencia - 1) : null;

  if (!geometria) return <div ref={raiz} className="pointer-events-none absolute inset-0" />;

  const etiqueta = "absolute flex h-[22px] items-center gap-1.5 rounded-md text-[11px] font-bold leading-none text-white shadow-sm";

  return (
    <div ref={raiz} className="pointer-events-none absolute inset-0 z-10">
      {!criando &&
        alertas.map((a) => {
          const y = geometria.ys[a.id];
          if (y === null || y === undefined) return null;
          const preco = precoNaTela(a);
          const direcao = direcaoDoNivel(preco, referencia, a.direcao);
          const arrastando = arrasto?.id === a.id;
          const longe = distancia(preco);
          return (
            <div key={a.id}>
              {/* A faixa que pega o mouse ao longo da linha. A linha em si e a
                  do canvas, por baixo; aqui so aparece um reforco ao passar o
                  mouse, para mostrar que da para pegar. */}
              <div
                className="group pointer-events-auto absolute left-0 cursor-ns-resize"
                style={{ top: y - FAIXA / 2, height: FAIXA, width: geometria.largura, touchAction: "none" }}
                onPointerDown={(e) => aoPressionar(e, a)}
                onPointerMove={aoArrastar}
                onPointerUp={aoSoltar}
                onPointerCancel={aoSoltar}
                aria-hidden
              >
                <div
                  className={`absolute inset-x-0 top-1/2 h-[2px] -translate-y-1/2 transition-opacity ${
                    arrastando ? "opacity-70" : "opacity-0 group-hover:opacity-50"
                  }`}
                  style={{ background: cor }}
                />
              </div>

              <div
                className={`${etiqueta} pointer-events-auto cursor-ns-resize pl-2 pr-0.5`}
                style={{ top: y - 11, right: geometria.eixo + 6, background: cor, touchAction: "none" }}
                onPointerDown={(e) => aoPressionar(e, a)}
                onPointerMove={aoArrastar}
                onPointerUp={aoSoltar}
                onPointerCancel={aoSoltar}
                title="Arraste para mudar o nível"
              >
                <span className="num whitespace-nowrap">
                  {seta(direcao)} {reais(preco)}
                  {longe && <span className="font-semibold opacity-80"> · {longe}</span>}
                </span>
                <button
                  type="button"
                  // O ✕ nao comeca arrasto: sem isto, o clique nele capturava o
                  // ponteiro pela etiqueta e o alerta nao era apagado.
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={() => aoApagar(a.id)}
                  aria-label={`Apagar alerta de ${reais(a.preco)}`}
                  title="Apagar alerta"
                  className="flex h-[18px] w-[18px] cursor-pointer items-center justify-center rounded text-white/80 transition-colors hover:bg-white/20 hover:text-white"
                >
                  <svg width="8" height="8" viewBox="0 0 10 10" aria-hidden>
                    <path d="M2 2l6 6M8 2L2 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            </div>
          );
        })}

      {criando && (
        <div
          className="pointer-events-auto absolute inset-0 cursor-crosshair"
          style={{ touchAction: "none" }}
          onPointerMove={(e) => setFantasma(precoNoPonteiro(e.clientY))}
          onPointerLeave={() => setFantasma(null)}
          onPointerDown={(e) => {
            if (e.button !== 0) return;
            const ponto = precoNoPonteiro(e.clientY);
            if (ponto && ponto.y <= geometria.altura) aoCriar(ponto.preco);
          }}
        >
          {fantasma && fantasma.y <= geometria.altura && (
            <>
              <div
                className="absolute left-0 border-t border-dashed"
                style={{ top: fantasma.y, width: geometria.largura, borderColor: cor }}
              />
              <div
                className={`${etiqueta} px-2`}
                style={{ top: fantasma.y - 11, right: geometria.eixo + 6, background: cor }}
              >
                <span className="num whitespace-nowrap">
                  {direcaoDoNivel(fantasma.preco, referencia) === "acima" ? "▲ Subir até" : "▼ Cair até"}{" "}
                  {reais(fantasma.preco)}
                  {distancia(fantasma.preco) && (
                    <span className="font-semibold opacity-80"> · {distancia(fantasma.preco)}</span>
                  )}
                </span>
              </div>
            </>
          )}
          <div className="absolute left-2 top-2 rounded-full bg-painel-2/90 px-2.5 py-1 text-[11px] font-semibold text-tinta-3">
            clique na altura do alerta · Esc cancela
          </div>
        </div>
      )}
    </div>
  );
}
