"use client";

/**
 * A linha do patrimonio em dolar, no lightweight-charts (o mesmo da ficha). Uma
 * serie so, na cor de acento; a linha tracejada marca o capital inicial. Verde e
 * vermelho ficam para o texto do resultado: aqui a linha nao muda de cor.
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
import { data as fmtData, numero } from "@/lib/formato";
import type { PontoDoPatrimonio } from "@/lib/patrimonio";
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

const dolar = (v: number) => `US$ ${numero(v, 2)}`;

export function CurvaDoPatrimonio({
  curva,
  capital,
}: {
  curva: PontoDoPatrimonio[];
  capital: number;
}) {
  const { tema } = useTema();
  const alvo = useRef<HTMLDivElement>(null);
  const grafico = useRef<IChartApi | null>(null);
  const serie = useRef<ISeriesApi<"Line"> | null>(null);
  const linhaDoCapital = useRef<IPriceLine | null>(null);
  const [sobMouse, setSobMouse] = useState<PontoDoPatrimonio | null>(null);
  const porDia = useMemo(() => new Map(curva.map((p) => [p.dia, p])), [curva]);

  useEffect(() => {
    const el = alvo.current;
    if (!el || curva.length === 0) return;
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
      timeScale: { borderColor: c.grade, rightOffset: 1, fixLeftEdge: true, fixRightEdge: true },
      crosshair: {
        vertLine: { color: c.texto, width: 1, style: 3, labelBackgroundColor: c.rotulo },
        horzLine: { color: c.texto, width: 1, style: 3, labelBackgroundColor: c.rotulo },
      },
      localization: { locale: "pt-BR", dateFormat: "dd/MM/yyyy", priceFormatter: dolar },
      // Arrastar na vertical com o dedo rola a PAGINA; na horizontal move o grafico.
      handleScroll: { vertTouchDrag: false },
      autoSize: true,
    });
    const s = g.addSeries(LineSeries, {
      color: c.acento,
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerRadius: 4,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    s.setData(curva.map((p) => ({ time: p.dia as Time, value: p.patrimonio })));
    linhaDoCapital.current = s.createPriceLine({
      price: capital,
      color: c.neutra,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      // o titulo so aparece junto com a etiqueta do eixo
      axisLabelVisible: true,
      title: "Capital inicial",
    });
    const aoMover = (e: MouseEventParams) => {
      setSobMouse(typeof e.time === "string" ? (porDia.get(e.time) ?? null) : null);
    };
    g.subscribeCrosshairMove(aoMover);
    g.timeScale().fitContent();
    grafico.current = g;
    serie.current = s;
    return () => {
      g.unsubscribeCrosshairMove(aoMover);
      g.remove();
      grafico.current = null;
      serie.current = null;
      linhaDoCapital.current = null;
    };
  }, [curva, capital, porDia]);

  // Tema: troca as cores sem recriar (recriar perderia o zoom de quem olha).
  useEffect(() => {
    const g = grafico.current;
    if (!g) return;
    const c = cores();
    g.applyOptions({
      layout: { background: { type: ColorType.Solid, color: c.fundo }, textColor: c.texto },
      grid: { horzLines: { color: c.grade } },
      rightPriceScale: { borderColor: c.grade },
      timeScale: { borderColor: c.grade },
      crosshair: {
        vertLine: { color: c.texto, labelBackgroundColor: c.rotulo },
        horzLine: { color: c.texto, labelBackgroundColor: c.rotulo },
      },
    });
    serie.current?.applyOptions({ color: c.acento });
    linhaDoCapital.current?.applyOptions({ color: c.neutra });
  }, [tema]);

  const ponto = sobMouse ?? curva.at(-1) ?? null;

  return (
    <div className="flex flex-col gap-2">
      {ponto && (
        <p className="num flex flex-wrap gap-x-4 gap-y-0.5 text-[12px] font-semibold text-tinta-3">
          <span>{fmtData(ponto.dia)}</span>
          <span className="font-extrabold text-tinta">{dolar(ponto.patrimonio)}</span>
          <span>realizado {dolar(ponto.realizado)}</span>
          <span>em aberto {dolar(ponto.aberto)}</span>
        </p>
      )}
      <div
        ref={alvo}
        role="img"
        aria-label={`Evolução do patrimônio em dólar, de ${fmtData(curva[0].dia)} a ${fmtData(curva[curva.length - 1].dia)}`}
        className="h-[280px] w-full md:h-[400px]"
      />
    </div>
  );
}
