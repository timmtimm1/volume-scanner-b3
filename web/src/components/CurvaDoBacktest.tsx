"use client";

/**
 * A curva do backtest: R acumulado, mes a mes, do setup e do controle.
 *
 * Duas linhas no lightweight-charts, o mesmo da ficha. O setup usa o acento do
 * tema; o controle, a cor neutra e tracejado. Nada de verde nem vermelho: essas
 * cores sao de direcao de preco e aqui nao ha preco.
 */

import {
  ColorType,
  createChart,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import { fmtR, type PontoDaCurva } from "@/lib/backtest-tela";
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

type Pontos = { time: Time; value: number }[];

function serie(curva: PontoDaCurva[], campo: "acumulado" | "controleAcumulado"): Pontos {
  const saida: Pontos = [];
  for (const p of curva) {
    const v = p[campo];
    if (v !== null) saida.push({ time: p.mes as Time, value: v });
  }
  return saida;
}

function ultimo(curva: PontoDaCurva[], campo: "acumulado" | "controleAcumulado"): number | null {
  for (let i = curva.length - 1; i >= 0; i--) {
    const v = curva[i][campo];
    if (v !== null) return v;
  }
  return null;
}

type Props = { curva: PontoDaCurva[]; nomeDoSetup: string };

export function CurvaDoBacktest({ curva, nomeDoSetup }: Props) {
  const { tema } = useTema();
  const alvo = useRef<HTMLDivElement>(null);
  const grafico = useRef<IChartApi | null>(null);
  const linhas = useRef<{ setup: ISeriesApi<"Line">; controle: ISeriesApi<"Line"> } | null>(null);

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
      grid: { vertLines: { color: c.grade }, horzLines: { color: c.grade } },
      rightPriceScale: { borderColor: c.grade, scaleMargins: { top: 0.08, bottom: 0.08 } },
      timeScale: { borderColor: c.grade, rightOffset: 1, fixLeftEdge: true, fixRightEdge: true },
      crosshair: {
        vertLine: { color: c.texto, width: 1, style: 3, labelBackgroundColor: c.rotulo },
        horzLine: { color: c.texto, width: 1, style: 3, labelBackgroundColor: c.rotulo },
      },
      localization: {
        locale: "pt-BR",
        dateFormat: "MM/yyyy",
        priceFormatter: (p: number) => `${numero(p, 0)} R`,
      },
      // Arrastar na vertical com o dedo rola a PAGINA; na horizontal move o grafico.
      handleScroll: { vertTouchDrag: false },
      autoSize: true,
    });
    grafico.current = g;

    const controle = g.addSeries(LineSeries, {
      color: c.neutra,
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerRadius: 3,
      priceFormat: { type: "price", precision: 1, minMove: 0.1 },
    });
    const setup = g.addSeries(LineSeries, {
      color: c.acento,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerRadius: 4,
      priceFormat: { type: "price", precision: 1, minMove: 0.1 },
    });
    controle.setData(serie(curva, "controleAcumulado"));
    setup.setData(serie(curva, "acumulado"));
    linhas.current = { setup, controle };
    g.timeScale().fitContent();

    return () => {
      g.remove();
      grafico.current = null;
      linhas.current = null;
    };
  }, [curva]);

  // Tema: troca as cores sem recriar (recriar perderia o zoom de quem olha).
  useEffect(() => {
    const g = grafico.current;
    const l = linhas.current;
    if (!g || !l) return;
    const c = cores();
    g.applyOptions({
      layout: { background: { type: ColorType.Solid, color: c.fundo }, textColor: c.texto },
      grid: { vertLines: { color: c.grade }, horzLines: { color: c.grade } },
      rightPriceScale: { borderColor: c.grade },
      timeScale: { borderColor: c.grade },
      crosshair: {
        vertLine: { color: c.texto, labelBackgroundColor: c.rotulo },
        horzLine: { color: c.texto, labelBackgroundColor: c.rotulo },
      },
    });
    l.setup.applyOptions({ color: c.acento });
    l.controle.applyOptions({ color: c.neutra });
  }, [tema, curva]);

  if (curva.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-linha-2 p-6 text-center text-[13px] font-semibold text-tinta-3">
        Sem curva para esta combinação.
      </p>
    );
  }

  const primeiro = curva[0].mes;
  const final = curva[curva.length - 1].mes;

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
        <span className="flex items-center gap-2 text-[13px] font-bold">
          <span aria-hidden className="h-1 w-5 rounded-full bg-acento" />
          {nomeDoSetup}
          <span className="num font-extrabold">{fmtR(ultimo(curva, "acumulado"))}</span>
        </span>
        <span className="flex items-center gap-2 text-[13px] font-bold text-tinta-2">
          <span
            aria-hidden
            className="h-0 w-5 border-t-[3px] border-dashed border-tinta-2"
          />
          Controle
          <span className="num font-extrabold">{fmtR(ultimo(curva, "controleAcumulado"))}</span>
        </span>
      </div>
      <div
        ref={alvo}
        role="img"
        aria-label={`R acumulado mês a mês, de ${fmtData(primeiro)} a ${fmtData(final)}: ${nomeDoSetup} termina em ${fmtR(ultimo(curva, "acumulado"))} e o controle em ${fmtR(ultimo(curva, "controleAcumulado"))}.`}
        className="h-[260px] w-full md:h-[340px]"
      />
      <p className="text-[12px] font-semibold text-tinta-3">
        Soma de R mês a mês, 1R por trade, sem juros compostos: mostra onde o setup ganhou e onde
        devolveu, não o saldo de uma conta.
      </p>
    </div>
  );
}
