"use client";

/**
 * Juros no Brasil ao longo do tempo: um ponto por semana, desde 2016.
 *
 * Linhas no lightweight-charts, o mesmo do candle da ficha: arrasta, da zoom
 * (roda, pinca) e abre mostrando tudo. As sete series ficam em chips que ligam e
 * desligam cada uma e mostram o valor sob o cursor; ao abrir, so quatro.
 *
 * Cores: as das series acompanham o acento do tema (prefixados) e o azul de
 * indicador do design (juro real); a Selic e neutra. Nada de verde, vermelho ou
 * ambar -- esses tem outro significado no app.
 */

import {
  ColorType,
  createChart,
  LineSeries,
  LineStyle,
  LineType,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import { data as fmtData, numero } from "@/lib/formato";
import {
  CHAVE_DAS_SERIES,
  coresDasSeries,
  type IdDaSerie,
  lerEscolha,
  SERIES,
  trechos,
  valoresNaSemana,
} from "@/lib/juros";
import { useTema } from "@/lib/tema";
import type { HistoricoDeJuros } from "@/lib/types";

const lerVariavel = (nome: string, reserva: string) => {
  const v = getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  return v || reserva;
};

function superficie() {
  return {
    fundo: lerVariavel("--painel", "#ffffff"),
    texto: lerVariavel("--tinta-3", "#666985"),
    grade: lerVariavel("--linha", "#e6e7f0"),
    rotulo: lerVariavel("--primario", "#26235f"),
    acento: lerVariavel("--acento", "#4f46e5"),
    neutra: lerVariavel("--tinta-2", "#4a4d6a"),
  };
}

const taxa = (v: number | null) => (v === null ? "—" : `${numero(v, 2)}%`);

export function GraficoDeJuros({ historico }: { historico: HistoricoDeJuros }) {
  const { tema } = useTema();
  const alvo = useRef<HTMLDivElement>(null);
  const grafico = useRef<IChartApi | null>(null);
  // Uma serie pode ter varios trechos (linhas): o grafico nao liga o que tem buraco no meio.
  const linhasDoGrafico = useRef(new Map<IdDaSerie, ISeriesApi<"Line">[]>());
  const [ligadas, setLigadas] = useState<Set<IdDaSerie>>(() => lerEscolha(null));
  const [cursor, setCursor] = useState<string | null>(null);
  // As cores dos chips, as mesmas das linhas. Lidas do CSS no cliente; antes
  // disso (e no servidor) valem as do tema claro.
  const [cores, setCores] = useState(() => coresDasSeries("#4f46e5", "#4a4d6a"));

  const semanas = historico.semanas;
  const ultima = semanas[semanas.length - 1] ?? null;
  // Sem cursor, a leitura mostra a ultima semana.
  const semanaLida = cursor ?? ultima;
  const valores = useMemo(
    () => (semanaLida === null ? null : valoresNaSemana(historico, semanaLida)),
    [historico, semanaLida],
  );

  // A escolha guardada so e lida depois de montar: no servidor vale o padrao.
  useEffect(() => {
    try {
      const bruto = localStorage.getItem(CHAVE_DAS_SERIES);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- leitura de armazenamento externo, so no cliente
      if (bruto !== null) setLigadas(lerEscolha(bruto));
    } catch {
      // Armazenamento bloqueado: vale o padrao.
    }
  }, []);

  // Cria o grafico. Recriado so se os dados mudarem (outra edicao).
  useEffect(() => {
    const el = alvo.current;
    if (!el || historico.semanas.length === 0) return;
    const sup = superficie();
    const paleta = coresDasSeries(sup.acento, sup.neutra);
    const c = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: sup.fundo },
        textColor: sup.texto,
        fontFamily: "var(--fonte-sans), system-ui, sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { color: sup.grade }, horzLines: { color: sup.grade } },
      rightPriceScale: { borderColor: sup.grade, scaleMargins: { top: 0.08, bottom: 0.08 } },
      timeScale: { borderColor: sup.grade, rightOffset: 1, fixLeftEdge: true, fixRightEdge: true },
      crosshair: {
        vertLine: { color: sup.texto, width: 1, style: 3, labelBackgroundColor: sup.rotulo },
        horzLine: { color: sup.texto, width: 1, style: 3, labelBackgroundColor: sup.rotulo },
      },
      localization: {
        locale: "pt-BR",
        dateFormat: "dd/MM/yyyy",
        priceFormatter: (p: number) => `${numero(p, 2)}%`,
      },
      // Arrastar na vertical com o dedo rola a PAGINA; na horizontal move o grafico.
      handleScroll: { vertTouchDrag: false },
      autoSize: true,
    });
    grafico.current = c;

    for (const s of SERIES) {
      const doTrecho = trechos(historico, s.id).map((trecho) => {
        const linha = c.addSeries(LineSeries, {
          color: paleta[s.id],
          lineWidth: 2,
          lineType: s.id === "selic" ? LineType.WithSteps : LineType.Simple,
          // Tracejada: no tema claro a Selic e o Pre 10a tem quase a mesma cor.
          lineStyle: s.id === "selic" ? LineStyle.Dashed : LineStyle.Solid,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerRadius: 4,
          priceFormat: { type: "price", precision: 2, minMove: 0.01 },
        });
        linha.setData(trecho.map((p) => ({ ...p, time: p.time as Time })));
        return linha;
      });
      linhasDoGrafico.current.set(s.id, doTrecho);
    }

    c.subscribeCrosshairMove((param) => {
      setCursor(typeof param.time === "string" ? param.time : null);
    });
    c.timeScale().fitContent();

    const mapa = linhasDoGrafico.current;
    return () => {
      c.remove();
      grafico.current = null;
      mapa.clear();
    };
  }, [historico]);

  // Liga e desliga as linhas. O eixo de preco reajusta so ao que esta visivel.
  useEffect(() => {
    for (const [id, doTrecho] of linhasDoGrafico.current) {
      for (const linha of doTrecho) linha.applyOptions({ visible: ligadas.has(id) });
    }
  }, [ligadas, historico]);

  // Tema: troca fundo, grade, texto e as cores das series, sem recriar o grafico
  // (recriar perderia o zoom de quem esta olhando).
  useEffect(() => {
    const c = grafico.current;
    if (!c) return;
    const sup = superficie();
    const paleta = coresDasSeries(sup.acento, sup.neutra);
    setCores(paleta);
    c.applyOptions({
      layout: { background: { type: ColorType.Solid, color: sup.fundo }, textColor: sup.texto },
      grid: { vertLines: { color: sup.grade }, horzLines: { color: sup.grade } },
      rightPriceScale: { borderColor: sup.grade },
      timeScale: { borderColor: sup.grade },
      crosshair: {
        vertLine: { color: sup.texto, labelBackgroundColor: sup.rotulo },
        horzLine: { color: sup.texto, labelBackgroundColor: sup.rotulo },
      },
    });
    for (const [id, doTrecho] of linhasDoGrafico.current) {
      for (const linha of doTrecho) linha.applyOptions({ color: paleta[id] });
    }
  }, [tema, historico]);

  function alternar(id: IdDaSerie) {
    setLigadas((antes) => {
      const depois = new Set(antes);
      if (depois.has(id)) depois.delete(id);
      else depois.add(id);
      try {
        localStorage.setItem(CHAVE_DAS_SERIES, JSON.stringify([...depois]));
      } catch {
        // Sem armazenamento a escolha vale so nesta visita.
      }
      return depois;
    });
  }

  if (semanas.length === 0) return null;

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center justify-between gap-3">
        <p className="num text-[12px] font-semibold text-tinta-3">
          {semanaLida === null ? "" : `Semana de ${fmtData(semanaLida)}`}
          {cursor === null ? " (desta edição)" : ""}
        </p>
        <button
          type="button"
          onClick={() => grafico.current?.timeScale().fitContent()}
          className="h-8 rounded-full border border-linha-2 px-3 text-[12px] font-bold text-tinta-2 transition-colors hover:border-acento hover:text-acento"
        >
          Ver tudo
        </button>
      </div>

      <div
        ref={alvo}
        role="img"
        aria-label={`Juros no Brasil por semana, de ${fmtData(semanas[0])} a ${fmtData(semanas[semanas.length - 1])}: Selic meta, prefixados de 1, 2, 5 e 10 anos e IPCA+ de 5 e 10 anos. Arraste para mover e use a pinça ou a roda para dar zoom.`}
        className="h-[280px] w-full md:h-[360px]"
      />

      <ul className="grid grid-cols-2 gap-1.5 md:grid-cols-3">
        {SERIES.map((s) => {
          const ligada = ligadas.has(s.id);
          const valor = valores?.[s.id] ?? null;
          return (
            <li key={s.id} className="min-w-0">
              <button
                type="button"
                aria-pressed={ligada}
                onClick={() => alternar(s.id)}
                className={`flex min-h-10 w-full items-center gap-2 rounded-xl border px-2.5 py-1.5 text-left text-[12px] font-bold transition-colors ${
                  ligada
                    ? "border-linha-2 bg-painel-2 text-tinta"
                    : "border-linha text-tinta-3 opacity-70"
                }`}
              >
                {s.id === "selic" ? (
                  <span
                    aria-hidden
                    className="h-0 w-4 shrink-0"
                    style={{ borderTop: `3px dashed ${cores[s.id]}`, opacity: ligada ? 1 : 0.45 }}
                  />
                ) : (
                  <span
                    aria-hidden
                    className="h-1 w-4 shrink-0 rounded-full"
                    style={{ background: cores[s.id], opacity: ligada ? 1 : 0.45 }}
                  />
                )}
                <span className="min-w-0 flex-1 truncate">{s.rotulo}</span>
                <span className="num shrink-0 text-[12px] font-extrabold">
                  {ligada ? taxa(valor) : ""}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
