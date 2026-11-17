/**
 * Busca na Binance o dia UTC em andamento das moedas pedidas (so no servidor).
 *
 * `ticker/tradingDay` do espelho publico de dados de mercado, o mesmo que o
 * pipeline usa: ate 100 moedas por chamada, sem chave. Uma moeda que a
 * Binance deixou de negociar derruba a chamada inteira (HTTP 400); nesse caso
 * pergunta uma por vez. Falha de rede nao derruba a pagina: devolve o que
 * conseguiu, possivelmente nada, e a aba mostra so o dado do banco.
 */

import type { DiaDeHoje } from "./cripto-hoje";

// Dois enderecos da mesma Binance, perguntados juntos; vale a primeira resposta
// valida. O espelho publico (`data-api.binance.vision`) atende os Estados
// Unidos, mas do Brasil levou 10,7 s numa chamada em 17/11/2026; o principal
// (`api.binance.com`) responde rapido do Brasil e recusa os Estados Unidos
// (HTTP 451). Assim a pagina nao depende da regiao em que a Vercel roda.
const URLS = [
  "https://api.binance.com/api/v3/ticker/tradingDay",
  "https://data-api.binance.vision/api/v3/ticker/tradingDay",
];
const POR_CHAMADA = 100;
const ESPERA_MS = 8000;
const MOEDA = /^[A-Z0-9]{1,15}$/;

type Resposta = {
  symbol?: string;
  openPrice?: string;
  highPrice?: string;
  lowPrice?: string;
  lastPrice?: string;
  quoteVolume?: string;
  openTime?: number;
};

function ler(itens: unknown, agora: string): DiaDeHoje[] {
  if (!Array.isArray(itens)) return [];
  const saida: DiaDeHoje[] = [];
  for (const r of itens as Resposta[]) {
    const simbolo = String(r.symbol ?? "");
    if (!simbolo.endsWith("USDT") || typeof r.openTime !== "number") continue;
    const dia = {
      moeda: simbolo.slice(0, -4),
      dia: new Date(r.openTime).toISOString().slice(0, 10),
      abertura: Number(r.openPrice),
      maxima: Number(r.highPrice),
      minima: Number(r.lowPrice),
      ultimo: Number(r.lastPrice),
      volume: Number(r.quoteVolume),
      hora: agora,
    };
    if ([dia.abertura, dia.maxima, dia.minima, dia.ultimo].every((v) => Number.isFinite(v) && v > 0)) {
      saida.push(dia);
    }
  }
  return saida;
}

async function buscar(moedas: string[]): Promise<unknown | null> {
  const simbolos = encodeURIComponent(JSON.stringify(moedas.map((m) => `${m}USDT`)));
  const controle = new AbortController();
  const limite = setTimeout(() => controle.abort(), ESPERA_MS);
  const tentativa = async (url: string): Promise<unknown> => {
    const r = await fetch(`${url}?symbols=${simbolos}&type=MINI`, {
      cache: "no-store",
      signal: controle.signal,
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  };
  try {
    return await Promise.any(URLS.map(tentativa));
  } catch {
    return null; // os dois falharam ou passaram do limite
  } finally {
    clearTimeout(limite);
    controle.abort(); // cancela a que perdeu a corrida
  }
}

export async function diaDeHoje(pedidas: readonly string[]): Promise<Record<string, DiaDeHoje>> {
  const moedas = [...new Set(pedidas.map((m) => m.toUpperCase()))].filter((m) => MOEDA.test(m));
  const agora = new Date().toISOString();
  const achadas: DiaDeHoje[] = [];
  for (let i = 0; i < moedas.length; i += POR_CHAMADA) {
    const lote = moedas.slice(i, i + POR_CHAMADA);
    const dados = await buscar(lote);
    if (dados !== null) {
      achadas.push(...ler(dados, agora));
    } else if (lote.length > 1) {
      const uma = await Promise.all(lote.map((m) => buscar([m])));
      for (const d of uma) if (d !== null) achadas.push(...ler(d, agora));
    }
  }
  return Object.fromEntries(achadas.map((d) => [d.moeda, d]));
}
