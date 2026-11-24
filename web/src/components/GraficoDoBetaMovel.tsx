"use client";

/**
 * Beta e correlacao contra o Bitcoin numa janela de 90 dias, um ponto por
 * semana, no lightweight-charts (o mesmo da ficha). O beta fica na escala da
 * direita, com uma linha tracejada no 1 (anda igual ao Bitcoin); a correlacao,
 * na da esquerda.
 */

import {
  ColorType,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  LineSeries,
  LineStyle,
  type MouseEventParams,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import type { PontoMovel } from "@/lib/analise";
import { data as fmtData, numero } from "@/lib/formato";
import { useTema } from "@/lib/tema";

const lerVariavel = (nome: string, reserva: string) => {
  const v = getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  return v || reserva;
};

function cores() {
  return {
    fundo: lerVariavel("--painel", "#ffffff"),
    texto: lerVariavel("--tinta-3", "#666985"),
    grade: lerVariavel("--linha", "#e6e7f0"),
    rotulo: lerVariavel("--primario", "#26235f"),
    acento: lerVariavel("--acento", "#4f46e5"),
    neutra: lerVariavel("--tinta-2", "#4a4d6a"),
  };
}

export function GraficoDoBetaMovel({ pontos }: { pontos: PontoMovel[] }) {
  const { tema } = useTema();
  const alvo = useRef<HTMLDivElement>(null);
  const grafico = useRef<IChartApi | null>(null);
  const serieBeta = useRef<ISeriesApi<"Line"> | null>(null);
  const serieCorrelacao = useRef<ISeriesApi<"Line"> | null>(null);
  const linhaDoUm = useRef<IPriceLine | null>(null);
  const [sobMouse, setSobMouse] = useState<PontoMovel | null>(null);
  const porDia = useMemo(() => new Map(pontos.map((p) => [p.dia, p])), [pontos]);
  const poucos = pontos.length < 2;

  useEffect(() => {
    const el = alvo.current;
    if (!el || poucos) return;
    const c = cores();
    const g = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: c.fundo },
        textColor: c.texto,
        fontFamily: "var(--fonte-sans), system-ui, sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: c.grade } },
      rightPriceScale: { borderColor: c.grade, scaleMargins: { top: 0.12, bottom: 0.12 } },
      leftPriceScale: { visible: true, borderColor: c.grade, scaleMargins: { top: 0.12, bottom: 0.12 } },
      timeScale: { borderColor: c.grade, rightOffset: 1, fixLeftEdge: true, fixRightEdge: true },
      crosshair: {
        vertLine: { color: c.texto, width: 1, style: 3, labelBackgroundColor: c.rotulo },
        horzLine: { color: c.texto, width: 1, style: 3, labelBackgroundColor: c.rotulo },
      },
      localization: { locale: "pt-BR", dateFormat: "dd/MM/yyyy", priceFormatter: (v: number) => numero(v, 2) },
      // Arrastar na vertical com o dedo rola a PAGINA; na horizontal move o grafico.
      handleScroll: { vertTouchDrag: false },
      autoSize: true,
    });
    const beta = g.addSeries(LineSeries, {
      color: c.acento,
      lineWidth: 2,
      priceScaleId: "right",
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerRadius: 4,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    const correlacao = g.addSeries(LineSeries, {
      color: c.neutra,
      lineWidth: 2,
      priceScaleId: "left",
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerRadius: 4,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    // Ponto sem valor (janela sem dado) fica de fora em vez de virar zero.
    const comValor = (campo: "beta" | "correlacao") =>
      pontos.flatMap((p) => {
        const v = p[campo];
        return v === null || !Number.isFinite(v) ? [] : [{ time: p.dia as Time, value: v }];
      });
    beta.setData(comValor("beta"));
    correlacao.setData(comValor("correlacao"));
    linhaDoUm.current = beta.createPriceLine({
      price: 1,
      color: c.neutra,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "beta 1",
    });
    const aoMover = (e: MouseEventParams) => {
      setSobMouse(typeof e.time === "string" ? (porDia.get(e.time) ?? null) : null);
    };
    g.subscribeCrosshairMove(aoMover);
    g.timeScale().fitContent();
    grafico.current = g;
    serieBeta.current = beta;
    serieCorrelacao.current = correlacao;
    return () => {
      g.unsubscribeCrosshairMove(aoMover);
      g.remove();
      grafico.current = null;
      serieBeta.current = null;
      serieCorrelacao.current = null;
      linhaDoUm.current = null;
    };
  }, [pontos, porDia, poucos]);

  // Tema: troca as cores sem recriar (recriar perderia o zoom de quem olha).
  useEffect(() => {
    const g = grafico.current;
    if (!g) return;
    const c = cores();
    g.applyOptions({
      layout: { background: { type: ColorType.Solid, color: c.fundo }, textColor: c.texto },
      grid: { horzLines: { color: c.grade } },
      rightPriceScale: { borderColor: c.grade },
      leftPriceScale: { borderColor: c.grade },
      timeScale: { borderColor: c.grade },
      crosshair: {
        vertLine: { color: c.texto, labelBackgroundColor: c.rotulo },
        horzLine: { color: c.texto, labelBackgroundColor: c.rotulo },
      },
    });
    serieBeta.current?.applyOptions({ color: c.acento });
    serieCorrelacao.current?.applyOptions({ color: c.neutra });
    linhaDoUm.current?.applyOptions({ color: c.neutra });
  }, [tema]);

  if (poucos) {
    return (
      <p className="rounded-2xl border border-dashed border-linha-2 p-6 text-center text-[13px] font-semibold text-tinta-3">
        Poucos dias para a janela de 90 dias.
      </p>
    );
  }

  const ponto = sobMouse ?? pontos.at(-1) ?? null;

  return (
    <div className="flex flex-col gap-2">
      <p className="num flex flex-wrap items-center gap-x-4 gap-y-0.5 text-[12px] font-semibold text-tinta-3">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-0.5 w-4 rounded-full bg-acento" />
          beta (escala da direita)
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-0.5 w-4 rounded-full bg-tinta-2" />
          correlação (escala da esquerda)
        </span>
      </p>
      {ponto && (
        <p className="num flex flex-wrap gap-x-4 gap-y-0.5 text-[12px] font-semibold text-tinta-3">
          <span>{fmtData(ponto.dia)}</span>
          <span className="font-extrabold text-tinta">beta {numero(ponto.beta, 2)}</span>
          <span className="font-extrabold text-tinta">correlação {numero(ponto.correlacao, 2)}</span>
        </p>
      )}
      <div
        ref={alvo}
        role="img"
        aria-label={`Beta e correlação contra o Bitcoin em janelas de 90 dias, de ${fmtData(pontos[0].dia)} a ${fmtData(pontos[pontos.length - 1].dia)}`}
        className="h-[240px] w-full"
      />
    </div>
  );
}
