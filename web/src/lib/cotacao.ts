/**
 * Cotacao de agora para a ficha, no servidor.
 *
 * Roda so na rota /api/cotacao: o token da brapi nunca chega ao navegador.
 *
 * Mesma regra dos alertas de preco no Python (`ProvedorMaisRecente`): o Yahoo
 * responde, e a brapi so e consultada para o que ele nao soube responder.
 *
 * A regra mudou em 23/09/2026 e o motivo nao e velocidade, e honestidade do
 * relogio. A brapi carimba `regularMarketTime` com a hora da RESPOSTA, nao a do
 * negocio: naquele dia, com o mercado aberto, ela devolveu para VIVA3 a
 * abertura, maxima, minima, fechamento e volume exatos do pregao ja fechado de
 * 22/09, carimbados como 23/09 as 10:19. O Yahoo, no mesmo instante, deu
 * 10:10:14 -- a hora do ultimo negocio -- e o parcial correto de hoje.
 *
 * Enquanto a escolha era "a de hora mais nova", a brapi vencia sempre, com dado
 * velho, e a ficha desenhava um candle de hoje que era copia do de ontem.
 *
 * Cada resposta fica 5 minutos no cache de dados do Next, por papel. Com a
 * brapi so na reserva, a cota gratuita de 15 mil por mes praticamente nao e
 * mais tocada pelo site.
 */

import { type CandleDeHoje, montarCandle } from "./candle-de-hoje";

const CACHE_SEGUNDOS = 300;

const YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart";
// v2, nao a v1 legada (/api/quote/{tickers}): mesmos campos, e ainda avisa
// quando um ticker foi renomeado (ver comentario em `daBrapi`).
const BRAPI = "https://brapi.dev/api/v2/stocks/quote";

// Sem User-Agent de navegador o Yahoo responde 429 (medido em 09/09/2026).
const CABECALHOS_YAHOO = { "User-Agent": "Mozilla/5.0 (compatible; volume-scanner-b3)" };

type RespostaDoYahoo = {
  candle: CandleDeHoje | null;
  /** 404: o Yahoo nao conhece o papel. */
  inexistente: boolean;
};

async function doYahoo(ticker: string): Promise<RespostaDoYahoo> {
  try {
    const r = await fetch(`${YAHOO}/${ticker}.SA?range=1d&interval=1d`, {
      headers: CABECALHOS_YAHOO,
      cache: "force-cache",
      next: { revalidate: CACHE_SEGUNDOS },
    });
    if (r.status === 404) return { candle: null, inexistente: true };
    if (!r.ok) {
      console.warn(`[cotacao] yahoo ${ticker} recusado com HTTP ${r.status}`);
      return { candle: null, inexistente: false };
    }
    const dados = await r.json();
    const resultado = dados?.chart?.result?.[0];
    const meta = resultado?.meta;
    const quote = resultado?.indicators?.quote?.[0];
    const epoch = meta?.regularMarketTime;
    const candle = montarCandle(ticker, "yahoo", {
      preco: meta?.regularMarketPrice,
      abertura: quote?.open?.[0],
      maxima: meta?.regularMarketDayHigh,
      minima: meta?.regularMarketDayLow,
      volume: meta?.regularMarketVolume,
      hora: typeof epoch === "number" ? new Date(epoch * 1000) : null,
    });
    return { candle, inexistente: false };
  } catch (erro) {
    console.warn(`[cotacao] yahoo ${ticker} falhou: ${(erro as Error).name}`);
    return { candle: null, inexistente: false };
  }
}

async function daBrapi(ticker: string, token: string): Promise<CandleDeHoje | null> {
  try {
    // Token no cabecalho, como a brapi recomenda. Uma requisicao por papel,
    // que e o que o plano gratuito aceita.
    const r = await fetch(`${BRAPI}?symbols=${ticker}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "force-cache",
      next: { revalidate: CACHE_SEGUNDOS },
    });
    if (!r.ok) {
      console.warn(`[cotacao] brapi ${ticker} recusado com HTTP ${r.status}`);
      return null;
    }
    const dados = await r.json();
    const item = dados?.results?.[0];
    // `symbol` e o codigo ATUAL do papel -- se a brapi disser que ele foi
    // renomeado (`changed: true`), e esse codigo que deve bater com o ticker
    // pedido, nao o `requestedSymbol`. Papel renomeado sem chegar aqui ainda
    // vira ficha vazia de candle parcial; nao ha alerta cadastrado a atualizar
    // neste caminho, so o grafico.
    if (item?.symbol !== ticker) return null;
    const info = item?.data;
    const hora = typeof info?.regularMarketTime === "string" ? new Date(info.regularMarketTime) : null;
    return montarCandle(ticker, "brapi", {
      preco: info?.regularMarketPrice,
      abertura: info?.regularMarketOpen,
      maxima: info?.regularMarketDayHigh,
      minima: info?.regularMarketDayLow,
      volume: info?.regularMarketVolume,
      hora,
    });
  } catch (erro) {
    console.warn(`[cotacao] brapi ${ticker} falhou: ${(erro as Error).name}`);
    return null;
  }
}

/**
 * O candle de hoje do papel: o Yahoo, e a brapi so quando ele nao responde.
 *
 * O Yahoo tambem serve de porteiro: se ele diz que o papel nao existe, a brapi
 * nem e consultada. A rota e publica, e sem isso qualquer um gastaria a cota da
 * brapi pedindo tickers inventados -- o Yahoo nao cobra por consulta.
 *
 * Nao ha mais comparacao de horas aqui. Comparar so faz sentido entre relogios
 * que medem a mesma coisa, e o da brapi mede outra (ver o topo do arquivo).
 * Quando ela responde, e porque o Yahoo nao respondeu -- e ai um preco com hora
 * duvidosa vale mais que nenhum. A hora aparece na ficha ao lado da fonte, para
 * quem olha saber de quando e.
 */
export async function candleDeHoje(ticker: string): Promise<CandleDeHoje | null> {
  const yahoo = await doYahoo(ticker);
  if (yahoo.inexistente) return null;
  if (yahoo.candle) return yahoo.candle;

  const token = process.env.SCANNER_BRAPI_TOKEN;
  return token ? await daBrapi(ticker, token) : null;
}
