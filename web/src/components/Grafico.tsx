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
  createSeriesMarkers,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type Logical,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import type { PointerEvent as EventoDePonteiro } from "react";
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Alerta, Direcao } from "@/lib/alertas";
import { type CandleDeHoje, candleParcial, horaNaB3 } from "@/lib/candle-de-hoje";
import { diaCurto, numero, percentual, reaisComSinal } from "@/lib/formato";
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
import { medirMovimento, type PontoDaRegua, type TradeDaRegua } from "@/lib/regua";
import { useTema } from "@/lib/tema";
import type { Barra, Evento } from "@/lib/types";
import { useMedias } from "@/lib/useMedias";
import { PainelDaRegua } from "./PainelDaRegua";

/** Cores das series: fixas nos dois temas. */
/** A cor da marca de balanco no candle. A ficha le para montar a legenda. */
export const COR_DO_BALANCO = "#7C8AA5";

const SERIE = {
  alta: "#0E9F6E",
  baixa: "#E0474C",
  evento: "#F0A020",
  volume: "#A9A3F5",
  banda: "#8F88F0",
  bandaMedia: "#B9B4F6",
  alerta: "#6D63F0",
  alertaDisparado: "#8C8EAD",
  // Marcadores de trade: cores proprias, de proposito diferentes de alta/baixa
  // -- aqui nao e direcao de preco, e compra/venda de verdade.
  compra: "#2F6FED",
  venda: "#B45FE0",
  pm: "#64748B",
  // Balanco publicado: cinza-azulado, de proposito sem verde nem vermelho --
  // nao e direcao de preco, e uma data em que a empresa falou.
  balanco: COR_DO_BALANCO,
};

/** Tamanho do rotulo da regua, em pixels -- para ele nao sair da area do grafico. */
const LARGURA_DO_ROTULO_DA_REGUA = 138;
const ALTURA_DO_ROTULO_DA_REGUA = 60;

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
  /** Compras e vendas de TODOS os trades do papel, para os marcadores no candle. */
  operacoes?: { data: string; tipo: "compra" | "venda"; quantidade: number }[];
  /**
   * Dias em que a empresa entregou balanco. Viram uma marca no candle, para
   * dar para ver se o volume anomalo veio logo depois do resultado.
   */
  publicacoes?: { data: string; rotulo: string }[];
  /**
   * O trade aberto do papel, ja marcado a mercado, para a linha tracejada do
   * preco medio. Null sem trade aberto -- sem ela, nao ha linha.
   */
  posicao?: {
    quantidade: number;
    precoMedio: number;
    resultado: number;
    resultadoPct: number | null;
  } | null;
  /**
   * O que a regua de medicao precisa saber para desenhar o painel. Sem esta
   * prop o botao da regua nem aparece -- e o caso de quem monta o Grafico sem
   * saber o preco de agora do papel.
   */
  regua?: {
    /** Close de hoje (candle parcial) quando ha, senao o close da ultima barra. */
    agora: number;
    /** Trade aberto do papel, para medir o efeito do nivel nele. Null sem trade/sessao. */
    trade?: TradeDaRegua | null;
    /** Logado: mostra o botao "Criar alerta em R$". */
    podeCriarAlerta: boolean;
    criarAlerta: (preco: number, direcao: Direcao) => Promise<void>;
  };
};

/**
 * Reserva do tema claro -- usada tanto como fallback de `coresDaSuperficie`
 * quanto como estado inicial de `superficieRegua` antes do primeiro efeito
 * rodar. `getComputedStyle` nao existe no servidor (o componente e "use
 * client", mas ainda ganha uma renderizacao no servidor), entao o estado
 * inicial nao pode chamar `coresDaSuperficie()` -- so uma constante estatica.
 */
const SUPERFICIE_PADRAO = {
  fundo: "#ffffff",
  texto: "#666985",
  grade: "#e6e7f0",
  rotulo: "#26235f",
};

function coresDaSuperficie() {
  const estilo = getComputedStyle(document.documentElement);
  const ler = (nome: string, reserva: string) => estilo.getPropertyValue(nome).trim() || reserva;
  return {
    fundo: ler("--painel", SUPERFICIE_PADRAO.fundo),
    texto: ler("--tinta-3", SUPERFICIE_PADRAO.texto),
    grade: ler("--linha", SUPERFICIE_PADRAO.grade),
    rotulo: ler("--primario", SUPERFICIE_PADRAO.rotulo),
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
  operacoes = [],
  publicacoes = [],
  posicao = null,
  regua,
}: Props) {
  const idBase = useId();
  const { tema } = useTema();
  const [medias, salvarMedias] = useMedias();
  const [mostrarBandas, setMostrarBandas] = useState(true);
  const [adicionando, setAdicionando] = useState(false);
  const [tipoNovo, setTipoNovo] = useState<TipoDeMedia>("MMA");
  const [periodoNovo, setPeriodoNovo] = useState("50");
  const [corNova, setCorNova] = useState<string | null>(null);

  // Estados da regua, estilo Profit: desligada -> ligada sem ponto -> ANCORADA
  // (tem inicio, a ponta segue o cursor/dedo) -> FIXADA (inicio e fim
  // parados). `reguaFixada` distingue as duas ultimas; `inicioDaRegua` null
  // distingue as duas primeiras.
  const [reguaLigada, setReguaLigada] = useState(false);
  const [inicioDaRegua, setInicioDaRegua] = useState<PontoDaRegua | null>(null);
  const [pontaDaRegua, setPontaDaRegua] = useState<PontoDaRegua | null>(null);
  const [reguaFixada, setReguaFixada] = useState(false);
  // Os pixels dos pontos da regua (e do rotulo), recalculados num efeito --
  // nao no render, que nao pode ler refs do grafico (`chart.current`,
  // `serie.current`). Null sem os dois pontos ou fora da area visivel.
  const [pixelsDaRegua, setPixelsDaRegua] = useState<{
    inicio: { x: number; y: number };
    ponta: { x: number; y: number };
    rotuloEsquerda: number;
    rotuloTopo: number;
  } | null>(null);

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
  const marcadoresDeTrade = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const marcadoresDeBalanco = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const linhaDoPM = useRef<IPriceLine | null>(null);
  // Cores da superficie para o rotulo da regua (HTML por cima do canvas, nao
  // desenhado pelo lightweight-charts). Estado, nao ref -- o render le para
  // pintar o rotulo. So muda com o tema ou quando o grafico e reconstruido,
  // nunca a cada pixel arrastado.
  const [superficieRegua, setSuperficieRegua] = useState(SUPERFICIE_PADRAO);

  // Guardados em ref para o clique nao precisar deles nas dependencias -- se
  // precisasse, cada render do pai reassinaria o evento e remontaria o grafico.
  const aoEscolher = useRef(aoEscolherPreco);
  const escolhendo = useRef(escolhendoPreco);
  useEffect(() => {
    aoEscolher.current = aoEscolherPreco;
    escolhendo.current = escolhendoPreco;
  });

  // Tela de toque ou caneta: muda so o texto da dica da regua ("toque e
  // arraste" em vez de "clique no ponto inicial"). Calculado uma vez -- o tipo
  // de ponteiro do aparelho nao muda durante a sessao.
  const [telaDeToque] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches,
  );

  function limparRegua() {
    setInicioDaRegua(null);
    setPontaDaRegua(null);
    setReguaFixada(false);
  }

  // Regua e escolha de nivel do alerta sao exclusivas: ligar a escolha do
  // alerta desliga a regua e limpa o que estava medido. Ajustado durante a
  // renderizacao com o padrao do proprio React para "adjusting state when a
  // prop changes" (estado, nao ref -- refs nao podem ser lidas no render): um
  // `useEffect` so pra isso dispararia uma renderizacao em cascata a toa.
  const [escolhendoAnterior, setEscolhendoAnterior] = useState(escolhendoPreco);
  if (escolhendoPreco !== escolhendoAnterior) {
    setEscolhendoAnterior(escolhendoPreco);
    if (escolhendoPreco) {
      setReguaLigada(false);
      limparRegua();
    }
  }

  function alternarRegua() {
    setReguaLigada((ligada) => {
      const proxima = !ligada;
      if (!proxima) limparRegua();
      return proxima;
    });
  }

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
    setSuperficieRegua(sup);
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

    // Um clique com o modo de escolher nivel ligado devolve o preco daquela
    // altura. Assinado uma vez: `subscribeClick` nao dispara em arrasto,
    // entao deslocar o grafico nao mexe nisso. A regua NAO usa `subscribeClick`
    // -- ele confunde dois cliques rapidos com duplo clique, entao o segundo
    // ponto as vezes nao chegava a marcar nada. Ela tem seu overlay proprio,
    // mais abaixo.
    c.subscribeClick((param) => {
      if (!param.point || !serie.current || !escolhendo.current) return;
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
      // Os marcadores e a linha do PM morrem com o grafico (chart.remove()
      // desfaz os primitivos da serie); so zerar as refs evita usa-las presas
      // a um grafico que ja sumiu.
      marcadoresDeTrade.current = null;
      linhaDoPM.current = null;
      mapaDeMedias.clear();
      // Os indices da regua eram relativos a este grafico (a este `barras`);
      // um novo grafico pode ter outra janela de barras, entao a medicao presa
      // ao antigo perde o sentido.
      limparRegua();
    };
  }, [barras, eventos, destaque]);

  // A superficie acompanha o tema sem reconstruir o grafico (e sem perder zoom).
  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    const sup = coresDaSuperficie();
    setSuperficieRegua(sup);
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

  /**
   * Os marcadores de compra/venda e a linha do preco medio, redesenhados quando
   * o trade muda. Efeito separado do que monta o grafico, igual ao das linhas
   * de alerta: registrar uma operacao nova nao pode reconstruir candles e
   * bandas.
   *
   * A linha do PM, estilo Profit: a cor segue o sinal do resultado (o trade
   * esta ganhando ou perdendo, marcado ao preco de agora) e o titulo mostra
   * quantidade e resultado -- nao so "PM". O rotulo do eixo continua mostrando
   * o preco (e o proprio `createPriceLine` que desenha).
   */
  useEffect(() => {
    const s = serie.current;
    if (!s) return;

    marcadoresDeTrade.current?.detach();
    // So operacoes em dia que o grafico tem candle: a de hoje ainda nao tem
    // barra (o COTAHIST chega a noite) e uma antiga pode estar fora da janela
    // carregada. Marcador em data sem candle nao tem onde ancorar.
    const diasDoGrafico = new Set(barras.map((b) => b.tradeDate));
    const marcadores: SeriesMarker<Time>[] = operacoes
      .filter((o) => diasDoGrafico.has(o.data))
      .map((o) => ({
      time: o.data as Time,
      position: o.tipo === "compra" ? "belowBar" : "aboveBar",
      shape: o.tipo === "compra" ? "arrowUp" : "arrowDown",
      color: o.tipo === "compra" ? SERIE.compra : SERIE.venda,
      text: `${o.tipo === "compra" ? "C" : "V"} ${o.quantidade}`,
    }));
    marcadoresDeTrade.current = createSeriesMarkers(s, marcadores);

    if (linhaDoPM.current) {
      s.removePriceLine(linhaDoPM.current);
      linhaDoPM.current = null;
    }
    if (posicao) {
      const cor =
        posicao.resultado > 0 ? SERIE.alta : posicao.resultado < 0 ? SERIE.baixa : SERIE.pm;
      linhaDoPM.current = s.createPriceLine({
        price: posicao.precoMedio,
        color: cor,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `C ${numero(posicao.quantidade, 0)} · ${reaisComSinal(posicao.resultado)} (${percentual(posicao.resultadoPct, 1)})`,
      });
    }
  }, [operacoes, posicao, barras, eventos, destaque]);

  /**
   * As marcas de balanco publicado, acima do candle.
   *
   * Ficam do lado oposto as de compra e venda, que vao embaixo: sao duas leituras
   * diferentes e nao podem se empilhar. `eventos` e `destaque` entram nas
   * dependencias porque a serie e recriada quando eles mudam, e a marca precisa
   * ser reatada na serie nova -- o mesmo motivo do efeito de cima.
   */
  useEffect(() => {
    const s = serie.current;
    if (!s) return;

    marcadoresDeBalanco.current?.detach();
    const diasDoGrafico = barras.map((b) => b.tradeDate);
    const marcas = publicacoes
      .map((p) => ({
        rotulo: p.rotulo,
        // A empresa costuma entregar o balanco depois do fechamento: a marca vai
        // no primeiro pregao a partir da entrega, que e quando o preco reagiu.
        dia: diasDoGrafico.find((d) => d >= p.data),
      }))
      .filter((m): m is { rotulo: string; dia: string } => m.dia !== undefined)
      .map((m) => ({
        time: m.dia as Time,
        position: "aboveBar" as const,
        shape: "circle" as const,
        color: SERIE.balanco,
        text: m.rotulo,
      }));
    marcadoresDeBalanco.current = createSeriesMarkers(s, marcas);
  }, [publicacoes, barras, eventos, destaque]);

  // A ultima versao de `recalcularPixelsDaRegua` (definida no efeito abaixo),
  // para o efeito de redimensionamento poder chamar a atual sem precisar
  // reassinar o ResizeObserver a cada ponto novo (varias vezes por segundo
  // durante um arrasto).
  const recalcularPixelsRef = useRef<() => void>(() => {});

  /**
   * Os pixels dos pontos da regua: recalculados aqui (nao no render, que nao
   * pode ler refs do grafico) sempre que os pontos mudam -- e o que da a
   * atualizacao "ao vivo" enquanto a ponta segue o cursor ou o dedo.
   * `useLayoutEffect` em vez de `useEffect`: roda antes da pintura, sem o
   * atraso de um quadro que deixaria o retangulo um passo atras do ponteiro.
   */
  useLayoutEffect(() => {
    function recalcular() {
      const c = chart.current;
      const s = serie.current;
      const el = alvo.current;
      if (!c || !s || !el || !inicioDaRegua || !pontaDaRegua) {
        setPixelsDaRegua(null);
        return;
      }
      const xIni = c.timeScale().logicalToCoordinate(inicioDaRegua.indice as Logical);
      const yIni = s.priceToCoordinate(inicioDaRegua.preco);
      const xFim = c.timeScale().logicalToCoordinate(pontaDaRegua.indice as Logical);
      const yFim = s.priceToCoordinate(pontaDaRegua.preco);
      if (xIni === null || yIni === null || xFim === null || yFim === null) {
        setPixelsDaRegua(null);
        return;
      }

      // O rotulo troca de lado perto da borda direita, e fica sempre dentro
      // da area do grafico nas duas direcoes.
      const areaL = el.clientWidth;
      const areaA = el.clientHeight;
      const margem = 10;
      let rotuloEsquerda =
        xFim + margem + LARGURA_DO_ROTULO_DA_REGUA > areaL
          ? xFim - margem - LARGURA_DO_ROTULO_DA_REGUA
          : xFim + margem;
      rotuloEsquerda = Math.min(Math.max(rotuloEsquerda, 4), areaL - LARGURA_DO_ROTULO_DA_REGUA - 4);
      const rotuloTopo = Math.min(
        Math.max(yFim - ALTURA_DO_ROTULO_DA_REGUA / 2, 4),
        areaA - ALTURA_DO_ROTULO_DA_REGUA - 4,
      );

      setPixelsDaRegua({
        inicio: { x: xIni, y: yIni },
        ponta: { x: xFim, y: yFim },
        rotuloEsquerda,
        rotuloTopo,
      });
    }
    recalcularPixelsRef.current = recalcular;
    recalcular();
  }, [inicioDaRegua, pontaDaRegua, barras, eventos, destaque]);

  /**
   * Regua ligada: desliga a rolagem e o zoom do grafico (senao arrastar o dedo
   * ou o mouse pra medir tambem move o candle) e acompanha o redimensionamento
   * e o intervalo visivel para recalcular os pixels dos pontos guardados em
   * dados -- eles moveriam na tela mesmo sem os pontos mudarem. Desligada,
   * restaura o comportamento padrao -- o grafico volta a se comportar
   * exatamente como sem a regua.
   */
  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    c.applyOptions({ handleScroll: !reguaLigada, handleScale: !reguaLigada });
    if (!reguaLigada) return;

    const recalcular = () => window.requestAnimationFrame(() => recalcularPixelsRef.current());
    const observador = new ResizeObserver(recalcular);
    if (alvo.current) observador.observe(alvo.current);
    c.timeScale().subscribeVisibleLogicalRangeChange(recalcular);
    return () => {
      observador.disconnect();
      c.timeScale().unsubscribeVisibleLogicalRangeChange(recalcular);
    };
  }, [reguaLigada, barras, eventos, destaque]);

  // Esc limpa e desliga a regua -- unico jeito de fazer isso pelo teclado,
  // ja que nao ha "clicar fora" (o overlay cobre o grafico inteiro).
  useEffect(() => {
    if (!reguaLigada) return;
    function aoTeclar(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      setReguaLigada(false);
      limparRegua();
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [reguaLigada]);

  /** Preco (2 casas) e indice de barra (limitado a `barras`) sob o ponteiro. */
  function pontoDoToque(clienteX: number, clienteY: number): PontoDaRegua | null {
    const c = chart.current;
    const s = serie.current;
    const el = alvo.current;
    if (!c || !s || !el || barras.length === 0) return null;
    const rect = el.getBoundingClientRect();
    const x = clienteX - rect.left;
    const y = clienteY - rect.top;

    const precoBruto = s.coordinateToPrice(y);
    if (precoBruto === null) return null;
    const preco = Math.round(Number(precoBruto) * 100) / 100;

    const logico = c.timeScale().coordinateToLogical(x);
    if (logico === null) return null;
    const indice = Math.min(Math.max(Math.round(logico), 0), barras.length - 1);

    return { indice, preco };
  }

  function aoPressionarNaRegua(e: EventoDePonteiro<HTMLDivElement>) {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    const ponto = pontoDoToque(e.clientX, e.clientY);
    if (!ponto) return;
    // So captura toque/caneta: sao um gesto so (pressionar, arrastar, soltar).
    // O mouse usa dois cliques distintos, e capturar no primeiro faria o
    // segundo clique (que fixa) sair de baixo do ponteiro sem problema, mas
    // sem necessidade -- o overlay ja cobre o grafico inteiro.
    if (e.pointerType !== "mouse") e.currentTarget.setPointerCapture(e.pointerId);

    if (inicioDaRegua === null || reguaFixada) {
      // Sem ponto, ou uma medicao ja fixada: este toque comeca outra medicao.
      setInicioDaRegua(ponto);
      setPontaDaRegua(ponto);
      setReguaFixada(false);
      return;
    }
    // ANCORADA e mouse: o segundo clique fixa a medicao.
    if (e.pointerType === "mouse") {
      setPontaDaRegua(ponto);
      setReguaFixada(true);
    }
  }

  function aoMoverNaRegua(e: EventoDePonteiro<HTMLDivElement>) {
    if (inicioDaRegua === null || reguaFixada) return;
    const ponto = pontoDoToque(e.clientX, e.clientY);
    if (ponto) setPontaDaRegua(ponto);
  }

  function aoSoltarNaRegua(e: EventoDePonteiro<HTMLDivElement>) {
    // O mouse fixa no segundo clique (em `aoPressionarNaRegua`), nao ao soltar.
    if (e.pointerType === "mouse") return;
    if (inicioDaRegua === null || reguaFixada) return;
    const ponto = pontoDoToque(e.clientX, e.clientY);
    if (ponto) setPontaDaRegua(ponto);
    setReguaFixada(true);
  }

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

  // A medida em si nao depende de pixel nenhum -- so dos pontos em dados --
  // entao pode ser calculada aqui no render, sem tocar em ref.
  const medicaoDaRegua =
    inicioDaRegua && pontaDaRegua ? medirMovimento({ inicio: inicioDaRegua, fim: pontaDaRegua }) : null;
  const corDaRegua =
    medicaoDaRegua !== null && medicaoDaRegua.porAcao < 0 ? SERIE.baixa : SERIE.alta;

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

        {regua && (
          <button
            type="button"
            onClick={alternarRegua}
            disabled={escolhendoPreco}
            aria-pressed={reguaLigada}
            aria-label="Régua: medir preço e movimento tocando no gráfico"
            className={`inline-flex h-8 items-center gap-2 rounded-full px-3 text-[12px] font-bold transition-colors disabled:opacity-40 ${
              reguaLigada ? "bg-selecao text-acento" : "bg-painel-2 text-tinta-3"
            }`}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden>
              <g transform="rotate(-45 8 8)">
                <rect
                  x="1.5"
                  y="6"
                  width="13"
                  height="4"
                  rx="1"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.3"
                />
                <path
                  d="M4 6v1.6M7 6v2.4M10 6v1.6M13 6v1.6"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                />
              </g>
            </svg>
            Régua
          </button>
        )}
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
        className={`relative w-full ${classeDeAltura}`}
        style={{ cursor: escolhendoPreco || reguaLigada ? "crosshair" : undefined }}
      >
        {/* So o alvo do lightweight-charts: ele injeta seus proprios elementos
            aqui por fora do React (createChart/appendChild), entao este div nao
            pode ter filhos declarados em JSX -- misturar os dois deixaria o
            React tentando reconciliar um DOM que ele nao criou. O overlay da
            regua, por isso, e um irmao posicionado por cima, nao um filho. */}
        <div ref={alvo} className="h-full w-full" />

        {/* Overlay da regua: so existe com a regua ligada -- desligada, o
            grafico se comporta exatamente como sem ela (sem ate um listener a
            mais no caminho). `touchAction: none` impede o navegador de rolar a
            pagina no lugar de medir quando o gesto e um arrasto vertical. O
            `z-index` explicito e necessario: os proprios canvas do
            lightweight-charts tem z-index 1 e 2 (o de cima e o do crosshair),
            entao um overlay com z-index automatico ficaria por baixo deles. */}
        {reguaLigada && (
          <div
            className="absolute inset-0 z-10"
            style={{ touchAction: "none" }}
            onPointerDown={aoPressionarNaRegua}
            onPointerMove={aoMoverNaRegua}
            onPointerUp={aoSoltarNaRegua}
            onPointerCancel={aoSoltarNaRegua}
          >
            {pixelsDaRegua && medicaoDaRegua && (
              <>
                <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
                  <rect
                    x={Math.min(pixelsDaRegua.inicio.x, pixelsDaRegua.ponta.x)}
                    y={Math.min(pixelsDaRegua.inicio.y, pixelsDaRegua.ponta.y)}
                    width={Math.abs(pixelsDaRegua.ponta.x - pixelsDaRegua.inicio.x)}
                    height={Math.abs(pixelsDaRegua.ponta.y - pixelsDaRegua.inicio.y)}
                    fill={`${corDaRegua}26`}
                    stroke={corDaRegua}
                    strokeWidth={1.5}
                  />
                  <circle
                    cx={pixelsDaRegua.inicio.x}
                    cy={pixelsDaRegua.inicio.y}
                    r={4}
                    fill={corDaRegua}
                    stroke={superficieRegua.fundo}
                    strokeWidth={1.5}
                  />
                </svg>
                <div
                  className="pointer-events-none absolute rounded-xl px-2.5 py-2 text-[11px] font-bold leading-tight shadow-sm"
                  style={{
                    left: pixelsDaRegua.rotuloEsquerda,
                    top: pixelsDaRegua.rotuloTopo,
                    width: LARGURA_DO_ROTULO_DA_REGUA,
                    background: superficieRegua.fundo,
                    color: superficieRegua.rotulo,
                    border: `1px solid ${corDaRegua}`,
                  }}
                >
                  <div className="num" style={{ color: corDaRegua }}>
                    {percentual(medicaoDaRegua.variacaoPct, 2)}
                  </div>
                  <div className="num">{reaisComSinal(medicaoDaRegua.porAcao)}</div>
                  <div className="num text-tinta-3">{medicaoDaRegua.candles} candles</div>
                </div>
              </>
            )}

            {!inicioDaRegua && (
              <div className="pointer-events-none absolute right-2 top-2 rounded-full bg-painel-2/90 px-2.5 py-1 text-[11px] font-semibold text-tinta-3">
                {telaDeToque ? "toque e arraste" : "clique no ponto inicial"}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Painel da regua: sempre abaixo da area do grafico, nunca por cima dos
          candles -- em 390px um popup flutuante cobriria justo o que se quer
          ler. So aparece com a medicao FIXADA e para quem esta logado --
          deslogado, o rotulo no grafico ja basta. */}
      {regua && regua.podeCriarAlerta && reguaFixada && inicioDaRegua && pontaDaRegua && (
        <PainelDaRegua
          key={`${inicioDaRegua.indice}:${inicioDaRegua.preco}:${pontaDaRegua.indice}:${pontaDaRegua.preco}`}
          nivel={pontaDaRegua.preco}
          agora={regua.agora}
          trade={regua.trade}
          criarAlerta={regua.criarAlerta}
        />
      )}
    </div>
  );
}
