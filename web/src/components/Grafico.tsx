"use client";

/**
 * Candlestick com histograma de volume abaixo, escala compartilhada, marcacao
 * dos eventos, bandas de Bollinger e medias moveis escolhidas por quem olha.
 *
 * E a tela onde a leitura manual acontece -- a secao 6 do plano pede o mesmo
 * cuidado do pipeline.
 *
 * Cores: as das SERIES (candle, volume, evento, bandas, medias, alertas) sao as
 * mesmas nos dois temas, para a leitura do grafico nao mudar quando o tema
 * muda. O que acompanha o tema e so a superficie: fundo, grade e texto dos
 * eixos, lidos das variaveis de CSS.
 */

import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { Alerta } from "@/lib/alertas";
import { type CandleDeHoje, candleParcial, horaNaB3 } from "@/lib/candle-de-hoje";
import { diaCurto, numero } from "@/lib/formato";
import { aberturaDaBanda, bollinger, mediaMovel, type TipoDeMedia } from "@/lib/indicadores";
import {
  CORES_DAS_MEDIAS,
  comMedia,
  PERIODO_MAXIMO,
  PERIODO_MINIMO,
  proximaCor,
  rotuloDaMedia,
  semMedia,
} from "@/lib/medias";
import { useTema } from "@/lib/tema";
import type { Barra, Evento } from "@/lib/types";
import { useMedias } from "@/lib/useMedias";

/** Cores das series: fixas nos dois temas. */
const SERIE = {
  alta: "#0E9F6E",
  baixa: "#E0474C",
  evento: "#F0A020",
  volume: "#A9A3F5",
  banda: "#8F88F0",
  bandaMedia: "#B9B4F6",
  alerta: "#6D63F0",
  alertaDisparado: "#8C8EAD",
};

type Props = {
  barras: Barra[];
  eventos: Evento[];
  /** Pregao a centralizar e destacar. */
  destaque?: string;
  /** Altura do grafico, em classes (muda entre celular e computador). */
  classeDeAltura?: string;
  /** Niveis a desenhar como linha horizontal. So do papel desta ficha. */
  alertas?: Alerta[];
  /**
   * Ligado, um clique no grafico devolve o preco daquela altura. Desligado por
   * padrao: sem isso, qualquer clique para dispensar o cursor viraria um nivel
   * escolhido sem querer.
   */
  escolhendoPreco?: boolean;
  aoEscolherPreco?: (preco: number) => void;
  /**
   * A cotacao de agora. Vira um candle vazado depois do ultimo pregao oficial,
   * se for de um pregao que o COTAHIST ainda nao trouxe.
   */
  hoje?: CandleDeHoje | null;
};

function coresDaSuperficie() {
  const estilo = getComputedStyle(document.documentElement);
  const ler = (nome: string, reserva: string) => estilo.getPropertyValue(nome).trim() || reserva;
  return {
    fundo: ler("--painel", "#ffffff"),
    texto: ler("--tinta-3", "#666985"),
    grade: ler("--linha", "#e6e7f0"),
    rotulo: ler("--primario", "#26235f"),
  };
}

function Chip({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex h-8 items-center gap-2 rounded-full px-3 text-[12px] font-bold ${className}`}
    >
      {children}
    </span>
  );
}

export function Grafico({
  barras,
  eventos,
  destaque,
  classeDeAltura = "h-[340px] md:h-[500px]",
  alertas = [],
  escolhendoPreco = false,
  aoEscolherPreco,
  hoje = null,
}: Props) {
  const idBase = useId();
  const { tema } = useTema();
  const [medias, salvarMedias] = useMedias();
  const [mostrarBandas, setMostrarBandas] = useState(true);
  const [adicionando, setAdicionando] = useState(false);
  const [tipoNovo, setTipoNovo] = useState<TipoDeMedia>("MMA");
  const [periodoNovo, setPeriodoNovo] = useState("50");
  const [corNova, setCorNova] = useState<string | null>(null);

  const alvo = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const bandas = useRef<ISeriesApi<"Line">[]>([]);
  // A serie de candles precisa sobreviver ao efeito que a cria: e nela que as
  // linhas de alerta sao penduradas e que a altura do clique vira preco.
  const serie = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const serieDeVolume = useRef<ISeriesApi<"Histogram"> | null>(null);
  const linhasDeAlerta = useRef<IPriceLine[]>([]);
  const linhasDeMedia = useRef(new Map<string, ISeriesApi<"Line">>());
  const linhaDoParcial = useRef<IPriceLine | null>(null);

  // Guardados em ref para o clique nao precisar deles nas dependencias -- se
  // precisasse, cada render do pai reassinaria o evento e remontaria o grafico.
  const aoEscolher = useRef(aoEscolherPreco);
  const escolhendo = useRef(escolhendoPreco);
  useEffect(() => {
    aoEscolher.current = aoEscolherPreco;
    escolhendo.current = escolhendoPreco;
  });

  // Quanto a banda abriu contra a media recente: o "abrindo" em numero.
  const abertura = useMemo(() => {
    const ate = destaque ? barras.findIndex((b) => b.tradeDate === destaque) : -1;
    const trecho = ate >= 0 ? barras.slice(0, ate + 1) : barras;
    return aberturaDaBanda(bollinger(trecho, 20, 2));
  }, [barras, destaque]);

  const parcial = useMemo(() => candleParcial(barras, hoje), [barras, hoje]);

  useEffect(() => {
    if (!alvo.current || barras.length === 0) return;

    const sup = coresDaSuperficie();
    const c = createChart(alvo.current, {
      layout: {
        background: { type: ColorType.Solid, color: sup.fundo },
        textColor: sup.texto,
        fontFamily: "var(--fonte-sans), system-ui, sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: sup.grade },
        horzLines: { color: sup.grade },
      },
      rightPriceScale: { borderColor: sup.grade, scaleMargins: { top: 0.06, bottom: 0.28 } },
      timeScale: { borderColor: sup.grade, rightOffset: 3, fixLeftEdge: true },
      crosshair: {
        vertLine: { color: sup.texto, width: 1, style: 3, labelBackgroundColor: sup.rotulo },
        horzLine: { color: sup.texto, width: 1, style: 3, labelBackgroundColor: sup.rotulo },
      },
      autoSize: true,
    });
    chart.current = c;

    const candles = c.addSeries(CandlestickSeries, {
      upColor: SERIE.alta,
      downColor: SERIE.baixa,
      borderUpColor: SERIE.alta,
      borderDownColor: SERIE.baixa,
      wickUpColor: SERIE.alta,
      wickDownColor: SERIE.baixa,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    serie.current = candles;
    /**
     * O candle do evento fica inteiro dourado -- corpo, borda e pavio --
     * pareando com a barra de volume daquele dia. E o par de barras douradas
     * que marca o evento, sem seta nem rotulo por cima.
     */
    const datasDeEvento = new Set(eventos.map((e) => e.tradeDate));
    candles.setData(
      barras.map((b) => {
        const direcao = b.close >= (b.open ?? b.close) ? SERIE.alta : SERIE.baixa;
        const cor = datasDeEvento.has(b.tradeDate) ? SERIE.evento : direcao;
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
      lastValueVisible: false,
      priceLineVisible: false,
    });
    serieDeVolume.current = volume;
    c.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volume.setData(
      barras.map((b) => ({
        time: b.tradeDate as Time,
        value: b.volumeFinancial,
        color: datasDeEvento.has(b.tradeDate) ? SERIE.evento : SERIE.volume,
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
    desenhar((b) => b.superior, SERIE.banda, 0, 1);
    desenhar((b) => b.media, SERIE.bandaMedia, 2, 1);
    desenhar((b) => b.inferior, SERIE.banda, 0, 1);
    bandas.current = linhas;

    if (destaque) {
      const i = barras.findIndex((b) => b.tradeDate === destaque);
      if (i >= 0) {
        const de = Math.max(0, i - 40);
        const ate = Math.min(barras.length - 1, i + 14);
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

    // Um clique com o modo ligado devolve o preco daquela altura. Assinado uma
    // vez: `subscribeClick` nao dispara em arrasto, entao deslocar o grafico nao
    // escolhe nivel nenhum.
    c.subscribeClick((param) => {
      if (!escolhendo.current || !param.point || !serie.current) return;
      const preco = serie.current.coordinateToPrice(param.point.y);
      if (preco !== null) aoEscolher.current?.(Number(preco));
    });

    const mapaDeMedias = linhasDeMedia.current;
    return () => {
      c.remove();
      chart.current = null;
      bandas.current = [];
      serie.current = null;
      serieDeVolume.current = null;
      // As linhas morrem junto com o grafico; zerar as listas evita que os
      // efeitos de alerta e de media mexam num grafico que nao existe mais.
      linhasDeAlerta.current = [];
      linhaDoParcial.current = null;
      mapaDeMedias.clear();
    };
  }, [barras, eventos, destaque]);

  // A superficie acompanha o tema sem reconstruir o grafico (e sem perder zoom).
  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    const sup = coresDaSuperficie();
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
  }, [tema, barras, eventos, destaque]);

  useEffect(() => {
    for (const s of bandas.current) s.applyOptions({ visible: mostrarBandas });
  }, [mostrarBandas, barras, eventos, destaque]);

  /**
   * As medias moveis, sincronizadas com a lista escolhida.
   *
   * So as barras oficiais entram no calculo: o candle parcial de hoje ainda vai
   * mudar, e uma media que o incluisse andaria sozinha a cada cotacao.
   */
  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    const mapa = linhasDeMedia.current;
    const escolhidas = new Set(medias.map((m) => m.id));
    for (const [id, s] of mapa) {
      if (!escolhidas.has(id)) {
        c.removeSeries(s);
        mapa.delete(id);
      }
    }
    for (const m of medias) {
      let s = mapa.get(m.id);
      if (!s) {
        s = c.addSeries(LineSeries, {
          color: m.cor,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        mapa.set(m.id, s);
      } else {
        s.applyOptions({ color: m.cor });
      }
      s.setData(
        mediaMovel(barras, m.tipo, m.periodo).map((p) => ({
          time: p.tradeDate as Time,
          value: p.valor,
        })),
      );
    }
  }, [medias, barras, eventos, destaque]);

  /**
   * O candle do pregao em andamento, por cima do grafico oficial.
   *
   * `update` e nao `setData`: acrescenta ou substitui so a ultima barra, sem
   * reconstruir o grafico. Vazado, so com o contorno na cor da direcao. O volume
   * e aproximado: acoes vezes o preco de agora.
   */
  useEffect(() => {
    const candles = serie.current;
    if (!candles || !parcial) return;

    const cor = parcial.close >= parcial.open ? SERIE.alta : SERIE.baixa;
    candles.update({
      time: parcial.dia as Time,
      open: parcial.open,
      high: parcial.high,
      low: parcial.low,
      close: parcial.close,
      color: "rgba(0, 0, 0, 0)",
      borderColor: cor,
      wickColor: cor,
    });
    // A etiqueta do ultimo preco herdaria o corpo transparente do candle vazado
    // e sairia preta. No lugar dela, uma linha de preco na cor da direcao.
    candles.applyOptions({ lastValueVisible: false });
    if (linhaDoParcial.current) candles.removePriceLine(linhaDoParcial.current);
    linhaDoParcial.current = candles.createPriceLine({
      price: parcial.close,
      color: cor,
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      axisLabelVisible: true,
      title: "",
    });
    if (serieDeVolume.current && parcial.volumeAcoes !== null) {
      serieDeVolume.current.update({
        time: parcial.dia as Time,
        value: parcial.volumeAcoes * parcial.close,
        color: SERIE.volume + "80",
      });
    }
  }, [parcial, barras, eventos, destaque]);

  /**
   * As linhas dos alertas, redesenhadas quando a lista muda. Efeito separado do
   * que monta o grafico: criar um alerta nao pode reconstruir candles e bandas.
   */
  useEffect(() => {
    const s = serie.current;
    if (!s) return;

    for (const linha of linhasDeAlerta.current) s.removePriceLine(linha);
    linhasDeAlerta.current = alertas.map((a) =>
      s.createPriceLine({
        price: a.preco,
        color: a.ativo ? SERIE.alerta : SERIE.alertaDisparado,
        lineWidth: 1,
        lineStyle: a.ativo ? LineStyle.Dashed : LineStyle.Dotted,
        axisLabelVisible: true,
        title: a.ativo ? (a.direcao === "acima" ? "▲" : "▼") : "•",
      }),
    );
  }, [alertas, barras, eventos, destaque]);

  if (barras.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-linha-2 p-8 text-center text-[13px] text-tinta-3">
        Sem barras para este papel na janela mantida.
      </div>
    );
  }

  const periodo = Number(periodoNovo);
  const periodoValido =
    Number.isInteger(periodo) && periodo >= PERIODO_MINIMO && periodo <= PERIODO_MAXIMO;
  const corEscolhida = corNova ?? proximaCor(medias);
  const jaExiste = medias.some((m) => m.tipo === tipoNovo && m.periodo === periodo);

  function adicionar() {
    if (!periodoValido || jaExiste) return;
    salvarMedias(comMedia(medias, { tipo: tipoNovo, periodo, cor: corEscolhida }));
    setAdicionando(false);
    setCorNova(null);
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Chip className="bg-evento-fundo text-evento-tinta">
          <span className="h-3 w-2 rounded-sm bg-evento" />
          Evento
        </Chip>
        {parcial && (
          <Chip className="num bg-painel-2 text-tinta-2">
            <span className="h-3 w-2 rounded-sm border-[1.5px] border-tinta-3" />
            {diaCurto(parcial.dia)} parcial · {horaNaB3(parcial.hora)} · {parcial.fonte}
          </Chip>
        )}
        <button
          type="button"
          onClick={() => setMostrarBandas((v) => !v)}
          aria-pressed={mostrarBandas}
          className={`inline-flex h-8 items-center gap-2 rounded-full px-3 text-[12px] font-bold transition-colors ${
            mostrarBandas ? "bg-selecao text-acento" : "bg-painel-2 text-tinta-3"
          }`}
        >
          <span className="h-0.5 w-3.5" style={{ background: SERIE.banda }} />
          Bollinger 20 · 2σ
          {mostrarBandas && abertura !== null && (
            <span className="num font-semibold text-tinta-3">
              {abertura >= 1 ? "+" : "−"}
              {numero(Math.abs((abertura - 1) * 100), 0)}%
            </span>
          )}
        </button>

        {medias.map((m) => (
          <span
            key={m.id}
            className="num inline-flex h-8 items-center gap-2 rounded-full bg-painel-2 pl-3 pr-1 text-[12px] font-bold text-tinta"
          >
            <span className="h-0.5 w-3.5 rounded-full" style={{ background: m.cor, height: 3 }} />
            {rotuloDaMedia(m)}
            <button
              type="button"
              onClick={() => salvarMedias(semMedia(medias, m.id))}
              aria-label={`Remover ${rotuloDaMedia(m)}`}
              className="flex h-6 w-6 items-center justify-center rounded-full text-tinta-3 transition-colors hover:bg-linha hover:text-tinta"
            >
              <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
                <path d="M2 2l6 6M8 2L2 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </button>
          </span>
        ))}

        <button
          type="button"
          onClick={() => setAdicionando((v) => !v)}
          aria-expanded={adicionando}
          className={`inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[12px] font-bold transition-colors ${
            adicionando
              ? "border-acento bg-selecao text-acento"
              : "border-linha-2 text-tinta-2 hover:border-acento hover:text-acento"
          }`}
        >
          <svg width="11" height="11" viewBox="0 0 10 10" aria-hidden>
            <path d="M5 1.5v7M1.5 5h7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          Média
        </button>
      </div>

      {adicionando && (
        <div className="flex flex-wrap items-end gap-3 rounded-2xl bg-painel-2 p-3">
          <div className="flex flex-col gap-1.5">
            <span className="rotulo">Tipo</span>
            <div className="flex rounded-xl border border-linha-2 p-0.5">
              {(
                [
                  ["MMA", "Aritmética"],
                  ["MME", "Exponencial"],
                ] as const
              ).map(([tipo, nome]) => (
                <button
                  key={tipo}
                  type="button"
                  onClick={() => setTipoNovo(tipo)}
                  aria-pressed={tipoNovo === tipo}
                  className={`toque h-9 rounded-[10px] px-3 text-[12px] font-bold transition-colors ${
                    tipoNovo === tipo ? "bg-painel text-acento shadow-sm" : "text-tinta-3"
                  }`}
                >
                  {nome}
                </button>
              ))}
            </div>
          </div>

          <label className="flex flex-col gap-1.5" htmlFor={`${idBase}-periodo`}>
            <span className="rotulo">Período</span>
            <input
              id={`${idBase}-periodo`}
              type="number"
              inputMode="numeric"
              min={PERIODO_MINIMO}
              max={PERIODO_MAXIMO}
              value={periodoNovo}
              onChange={(e) => setPeriodoNovo(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") adicionar();
              }}
              className="num toque h-10 w-20 rounded-xl border border-linha-2 bg-painel px-3 text-[14px] font-bold outline-none focus:border-acento"
            />
          </label>

          <div className="flex flex-col gap-1.5">
            <span className="rotulo">Cor</span>
            <div className="flex h-10 items-center gap-1.5">
              {CORES_DAS_MEDIAS.map((cor) => (
                <button
                  key={cor}
                  type="button"
                  onClick={() => setCorNova(cor)}
                  aria-label={`Cor ${cor}`}
                  aria-pressed={corEscolhida === cor}
                  className={`h-7 w-7 rounded-full border-2 transition-transform ${
                    corEscolhida === cor ? "scale-110 border-tinta" : "border-transparent"
                  }`}
                  style={{ background: cor }}
                />
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={adicionar}
              disabled={!periodoValido || jaExiste}
              className="toque h-10 rounded-full bg-primario px-4 text-[13px] font-bold text-primario-tinta transition-opacity disabled:opacity-40"
            >
              Adicionar {tipoNovo} {periodoValido ? periodo : ""}
            </button>
            <button
              type="button"
              onClick={() => setAdicionando(false)}
              className="toque h-10 rounded-full px-3 text-[13px] font-bold text-tinta-3 hover:text-tinta"
            >
              Cancelar
            </button>
          </div>
          {(!periodoValido || jaExiste) && (
            <p className="w-full text-[12px] font-semibold text-tinta-3">
              {jaExiste
                ? `${tipoNovo} ${periodo} já está no gráfico.`
                : `Período entre ${PERIODO_MINIMO} e ${PERIODO_MAXIMO} pregões.`}
            </p>
          )}
        </div>
      )}

      {escolhendoPreco && (
        <p className="rounded-xl bg-selecao px-3 py-2 text-[12px] font-semibold text-acento">
          Toque na altura do nível que quer vigiar. Dá para ajustar o valor exato depois.
        </p>
      )}
      <div
        ref={alvo}
        className={`w-full ${classeDeAltura}`}
        style={{ cursor: escolhendoPreco ? "crosshair" : undefined }}
      />
    </div>
  );
}
