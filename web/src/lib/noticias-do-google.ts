/**
 * Busca as manchetes no RSS do Google Noticias, no servidor.
 *
 * Gratuito, sem chave e nao oficial: se o Google mudar o formato ou sair do
 * ar, a resposta vira `null` e a aba mostra o aviso -- o resto da ficha nao
 * depende disto.
 *
 * Cada busca fica 30 minutos no cache de dados do Next. Noticia nao muda a
 * cada minuto, e o Google nao tem cota, mas nao convem martelar.
 */

import { empresaDoTicker, identidadeDoPapel } from "./nomes-na-imprensa";
import {
  buscasDoGoogle,
  filtrarNoticias,
  lerRss,
  type Noticia,
  type ResultadoDasNoticias,
} from "./noticias";

const CACHE_SEGUNDOS = 1800;
const RSS = "https://news.google.com/rss/search";
const CABECALHOS = { "User-Agent": "Mozilla/5.0 (compatible; volume-scanner-b3)" };

/** Papel pequeno quase nunca tem 3 noticias numa semana; ai a janela abre para um mes. */
const DIAS = 7;
const DIAS_SE_POUCO = 30;
const POUCO = 3;

export type RespostaDasNoticias = { buscas: string[]; resultado: ResultadoDasNoticias | null };

/** Uma busca. null se o Google recusou ou nao respondeu. */
async function buscar(q: string, ticker: string): Promise<Noticia[] | null> {
  const parametros = new URLSearchParams({ q, hl: "pt-BR", gl: "BR", ceid: "BR:pt-419" });
  try {
    const r = await fetch(`${RSS}?${parametros}`, {
      headers: CABECALHOS,
      cache: "force-cache",
      next: { revalidate: CACHE_SEGUNDOS },
    });
    if (!r.ok) {
      console.warn(`[noticias] google ${ticker} recusado com HTTP ${r.status}`);
      return null;
    }
    return lerRss(await r.text());
  } catch (erro) {
    console.warn(`[noticias] google ${ticker} falhou: ${(erro as Error).name}`);
    return null;
  }
}

export async function noticiasDoPapel(ticker: string): Promise<RespostaDasNoticias> {
  const id = identidadeDoPapel(ticker);
  if (!empresaDoTicker(ticker)) {
    console.warn(`[noticias] ${ticker} fora da tabela de nomes; buscando so pelo ticker`);
  }

  async function naJanela(dias: number): Promise<RespostaDasNoticias> {
    const buscas = buscasDoGoogle(id, dias);
    const respostas = await Promise.all(buscas.map((q) => buscar(q, ticker)));
    // Uma busca que falha nao derruba as outras; so todas falhando vira aviso.
    if (respostas.every((r) => r === null)) return { buscas, resultado: null };
    const noticias = respostas.flatMap((r) => r ?? []);
    return { buscas, resultado: filtrarNoticias(noticias, id, dias) };
  }

  const semana = await naJanela(DIAS);
  if (semana.resultado === null || semana.resultado.grupos.length >= POUCO) return semana;
  const mes = await naJanela(DIAS_SE_POUCO);
  return mes.resultado === null ? semana : mes;
}
