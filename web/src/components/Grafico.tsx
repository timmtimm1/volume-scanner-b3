"use client";

/**
 * Candlestick com histograma de volume abaixo, escala compartilhada, marcadores
 * nos eventos anteriores e bandas de Bollinger.
 *
 * E a tela onde a leitura manual acontece -- a secao 6 do plano pede o mesmo
 * cuidado do pipeline. Ver que o papel deu 6 sigma tres vezes em oito meses, e
 * o que o preco fez em cada uma, e o que nenhuma estatistica substitui.
 */

import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import { aberturaDaBanda, bollinger } from "@/lib/indicadores";
import type { Barra, Evento } from "@/lib/types";

const COR = {
  alta: "#26c281",
  baixa: "#ff5c5c",
  ambar: "#ffb020",
  linha: "#1f2937",
  tinta2: "#94a6ba",
  tinta3: "#5d7186",
  fundo: "#0a0e14",
  painel: "#10161f",
  /**
   * Terceiro tom da paleta, so para indicador de grafico. Nao pode ser verde
   * nem vermelho (reservados a direcao) nem ambar (reservado a interface e ao
   * marcador de evento), e precisa destacar sobre os candles.
   */
  banda: "#7d9fe0",
  bandaMedia: "#5c7bb8",
};

type Props = {
  barras: Barra[];
  eventos: Evento[];
  /** Pregao a centralizar e destacar. */
  destaque?: string;
  altura?: number;
};

export function Grafico({ barras, eventos, destaque, altura = 400 }: Props) {
  const alvo = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const [mostrarBandas, setMostrarBandas] = useState(true);
  const bandas = useRef<ISeriesApi<"Line">[]>([]);

  // Quanto a banda abriu contra a media recente: o "abrindo" em numero.
  const abertura = useMemo(() => {
    const ate = destaque ? barras.findIndex((b) => b.tradeDate === destaque) : -1;
    const serie = ate >= 0 ? barras.slice(0, ate + 1) : barras;
    return aberturaDaBanda(bollinger(serie, 20, 2));
  }, [barras, destaque]);

  useEffect(() => {
    if (!alvo.current || barras.length === 0) return;

    const c = createChart(alvo.current, {
      layout: {
        background: { type: ColorType.Solid, color: COR.painel },
        textColor: COR.tinta3,
        fontFamily: "var(--fonte-mono), monospace",
        fontSize: 10,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: COR.linha },
        horzLines: { color: COR.linha },
      },
      rightPriceScale: { borderColor: COR.linha, scaleMargins: { top: 0.06, bottom: 0.3 } },
      timeScale: { borderColor: COR.linha, rightOffset: 3, fixLeftEdge: true },
      crosshair: {
        vertLine: { color: COR.tinta3, width: 1, style: 3, labelBackgroundColor: "#2a3543" },
        horzLine: { color: COR.tinta3, width: 1, style: 3, labelBackgroundColor: "#2a3543" },
      },
      height: altura,
      autoSize: true,
    });
    chart.current = c;

    const candles = c.addSeries(CandlestickSeries, {
      upColor: COR.alta,
      downColor: COR.baixa,
      borderUpColor: COR.alta,
      borderDownColor: COR.baixa,
      wickUpColor: COR.alta,
      wickDownColor: COR.baixa,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    /**
     * O candle do evento fica inteiro ambar -- corpo, borda e pavio -- pareando
     * com a barra de volume daquele dia. E o par de barras douradas que marca o
     * evento, sem seta nem rotulo por cima.
     *
     * O candle perde a cor de direcao, mas ela nao se perde da tela: a variacao
     * do dia esta no cabecalho e no painel de contexto, com sinal e cor.
     */
    const datasDeEvento = new Set(eventos.map((e) => e.tradeDate));
    candles.setData(
      barras.map((b) => {
        const direcao = b.close >= (b.open ?? b.close) ? COR.alta : COR.baixa;
        const cor = datasDeEvento.has(b.tradeDate) ? COR.ambar : direcao;
        return {
          time: b.tradeDate as Time,
          open: b.open ?? b.close,
          high: b.high ?? b.close,
          low: b.low ?? b.close,
          close: b.close,
          color: cor,
          borderColor: cor,
          wickColor: cor,
        };
      }),
    );

    // Volume no mesmo eixo de tempo, ocupando a faixa de baixo.
    const volume = c.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    c.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
    });
    volume.setData(
      barras.map((b) => ({
        time: b.tradeDate as Time,
        value: b.volumeFinancial,
        color: datasDeEvento.has(b.tradeDate)
          ? COR.ambar
          : (b.close >= (b.open ?? b.close) ? COR.alta : COR.baixa) + "80",
      })),
    );

    // Bandas de Bollinger: 20 pregoes, 2 desvios.
    const bb = bollinger(barras, 20, 2);
    const linhas: ISeriesApi<"Line">[] = [];
    const desenhar = (
      pega: (b: (typeof bb)[number]) => number,
      cor: string,
      estilo: 0 | 2,
      largura: 1 | 2,
    ) => {
      const s = c.addSeries(LineSeries, {
        color: cor,
        lineWidth: largura,
        lineStyle: estilo,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      s.setData(bb.map((b) => ({ time: b.tradeDate as Time, value: pega(b) })));
      linhas.push(s);
    };
    desenhar((b) => b.superior, COR.banda, 0, 2);
    desenhar((b) => b.media, COR.bandaMedia, 2, 1);
    desenhar((b) => b.inferior, COR.banda, 0, 2);
    bandas.current = linhas;

    if (destaque) {
      const i = barras.findIndex((b) => b.tradeDate === destaque);
      if (i >= 0) {
        const de = Math.max(0, i - 32);
        const ate = Math.min(barras.length - 1, i + 12);
        c.timeScale().setVisibleRange({
          from: barras[de].tradeDate as Time,
          to: barras[ate].tradeDate as Time,
        });
      } else {
        c.timeScale().fitContent();
      }
    } else {
      c.timeScale().fitContent();
    }

    return () => {
      c.remove();
      chart.current = null;
      bandas.current = [];
    };
  }, [barras, eventos, destaque, altura]);

  useEffect(() => {
    for (const s of bandas.current) {
      s.applyOptions({ visible: mostrarBandas });
    }
  }, [mostrarBandas]);

  if (barras.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-linha-2 p-8 text-center text-[13px] text-tinta-3">
        Sem barras para este papel na janela mantida.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-linha bg-painel">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-linha px-3 py-2">
        <button
          type="button"
          onClick={() => setMostrarBandas((v) => !v)}
          aria-pressed={mostrarBandas}
          className={`toque rounded border px-2.5 py-1 text-[11px] transition-colors ${
            mostrarBandas
              ? "border-linha-2 bg-selecao text-tinta"
              : "border-linha text-tinta-3 hover:text-tinta-2"
          }`}
        >
          Bollinger 20 · 2σ
        </button>
        <span className="flex items-center gap-1.5 text-[10px] text-tinta-2">
          <span className="h-2.5 w-1.5 bg-ambar" />
          candle do evento
        </span>
        <span className="flex items-center gap-1.5 text-[10px] text-tinta-2">
          <span className="h-0.5 w-3" style={{ background: COR.banda }} />
          banda
        </span>
        {abertura !== null && (
          <span className="num text-[10px] text-tinta-2">
            largura {abertura >= 1 ? "+" : "−"}
            {Math.abs((abertura - 1) * 100).toFixed(0).replace(".", ",")}% vs. média
          </span>
        )}
      </div>
      <div ref={alvo} style={{ height: altura }} />
    </div>
  );
}
