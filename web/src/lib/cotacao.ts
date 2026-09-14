/**
 * Cotacao de agora para a ficha, no servidor.
 *
 * Roda so na rota /api/cotacao: o token da brapi nunca chega ao navegador.
 *
 * Mesma regra dos alertas de preco no Python: consulta Yahoo e brapi e fica com
 * a cotacao de hora mais nova. Medido em 14/09/2026, o Yahoo atrasa ~15 minutos;
 * a brapi gratuita, pela propria brapi, ~30.
 *
 * Cada resposta fica 5 minutos no cache de dados do Next, por papel. Abrir a
 * mesma ficha varias vezes, ou deixa-la aberta, nao gasta requisicao a mais --
 * a cota gratuita da brapi e de 15 mil por mes, dividida com os alertas.
 */

import { type CandleDeHoje, maisRecente, montarCandle } from "./candle-de-hoje";

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
 * O candle mais recente que os fornecedores conhecem para o papel.
 *
 * O Yahoo vai primeiro e serve de porteiro: se ele diz que o papel nao existe,
 * a brapi nem e consultada. A rota e publica, e sem isso qualquer um gastaria a
 * cota da brapi pedindo tickers inventados -- o Yahoo nao cobra por consulta.
 */
export async function candleDeHoje(ticker: string): Promise<CandleDeHoje | null> {
  const yahoo = await doYahoo(ticker);
  if (yahoo.inexistente) return null;

  const token = process.env.SCANNER_BRAPI_TOKEN;
  const brapi = token ? await daBrapi(ticker, token) : null;

  // brapi na primeira posicao: em empate de hora, fica a fonte com contrato.
  return maisRecente(brapi, yahoo.candle);
}
