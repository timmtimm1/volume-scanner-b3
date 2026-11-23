/**
 * O que a aba Cripto le do servidor: a lista de moedas e a ficha da moeda aberta.
 * So no servidor, e sempre depois de `ehDono()`.
 */

import { escolhasDa, rodadaAtual } from "./backtest";
import type { SaidaDoSetup } from "./config";
import { moedas } from "./cripto";
import { comCandleDeHoje } from "./cripto-hoje";
import { diaDeHoje } from "./cripto-hoje-binance";
import { type LinhaDaMoeda, precoDaLinha } from "./cripto-lista";
import { conexaoDeAlertas, niveisDoPapel, papel } from "./db";
import { type Cor, type LinhaDoBacktest, montarEntrada } from "./entradas";
import { linhasDoBacktest } from "./entradas-dados";
import {
  arredondarPreco,
  gatilhoNoMercado,
  stopNoMercado,
  tendenciaSoLiquidos,
  textos,
} from "./mercado";
import { noMercado } from "./mercado-servidor";
import { listarSetups, preferenciasDosSetups } from "./setups";
import {
  type CategoriaDoSetup,
  categoriaDaChave,
  chaveDoBacktest,
  type Setup,
} from "./setups-tela";
import { lerTendencias } from "./tendencias";

const MERCADO = "cripto" as const;

/** Dias de grafico: o banco guarda 400; a ficha do papel mostra 180. */
const DIAS = 260;

/**
 * Uma linha por moeda: as 50 maiores e, fora delas, as que tem trade aberto (uma
 * moeda que saiu do ranking nao pode sumir da lista com a sua posicao dentro).
 */
export async function lerListaDeMoedas(): Promise<LinhaDaMoeda[]> {
  const [{ rows }, tendencias] = await noMercado(MERCADO, () =>
    Promise.all([
      conexaoDeAlertas().query<{
        ticker: string;
        nome: string;
        posicao: number | null;
        dia: string | null;
        fechamento: string | null;
        anterior: string | null;
        setups: string;
        com_trade: boolean;
      }>(
        `SELECT m.ticker, m.nome, m.posicao,
                u.trade_date::text AS dia, u.close AS fechamento, a.close AS anterior,
                (SELECT count(*) FROM volume_scanner.setups s
                  WHERE s.ticker = m.ticker AND s.estado = 'armado') AS setups,
                EXISTS (SELECT 1 FROM volume_scanner.trades t
                         WHERE t.ticker = m.ticker AND t.encerrado_em IS NULL) AS com_trade
           FROM volume_scanner.moedas m
           LEFT JOIN LATERAL (
                SELECT trade_date, close FROM volume_scanner.daily_bars b
                 WHERE b.ticker = m.ticker ORDER BY trade_date DESC LIMIT 1) u ON true
           LEFT JOIN LATERAL (
                SELECT close FROM volume_scanner.daily_bars b
                 WHERE b.ticker = m.ticker ORDER BY trade_date DESC OFFSET 1 LIMIT 1) a ON true
          WHERE m.no_top
             OR EXISTS (SELECT 1 FROM volume_scanner.trades t
                         WHERE t.ticker = m.ticker AND t.encerrado_em IS NULL)
          ORDER BY m.posicao NULLS LAST, m.ticker`,
      ),
      lerTendencias(tendenciaSoLiquidos(MERCADO)),
    ]),
  );
  const hoje = await diaDeHoje(rows.map((r) => r.ticker));
  const inclinacoes = new Map(tendencias.linhas.map((l) => [l.ticker, l.inclinacoes]));
  return rows.map((r) => {
    const fechamento = r.fechamento === null ? null : Number(r.fechamento);
    const anterior = r.anterior === null ? null : Number(r.anterior);
    return {
      ticker: r.ticker,
      nome: r.nome,
      posicao: r.posicao,
      ...precoDaLinha(fechamento, anterior, r.dia, hoje[r.ticker]),
      setups: Number(r.setups),
      comTrade: r.com_trade,
      inclinacoes: inclinacoes.get(r.ticker) ?? null,
    };
  });
}

/** A nota do backtest de cada setup armado, a mesma cor do cartao da aba Setups. */
async function notasDosArmados(armados: Setup[]): Promise<Record<number, Cor>> {
  if (armados.length === 0) return {};
  const [rodada, preferencias] = await Promise.all([rodadaAtual(), preferenciasDosSetups()]);
  const saidas: Partial<Record<CategoriaDoSetup, SaidaDoSetup>> = {};
  let linhas: LinhaDoBacktest[] = [];
  if (rodada) {
    const [escolhas, grade] = await Promise.all([
      escolhasDa(rodada.id),
      linhasDoBacktest(rodada.id, textos(MERCADO).periodoDaNota),
    ]);
    linhas = grade;
    for (const e of escolhas) {
      const categoria = categoriaDaChave(e.setup);
      if (categoria && e.saida) saidas[categoria] = e.saida;
    }
  }
  const notas: Record<number, Cor> = {};
  for (const s of armados) {
    notas[s.id] = montarEntrada(
      {
        setup: s,
        chave: chaveDoBacktest(s.categoria),
        gatilho: gatilhoNoMercado(MERCADO, s.maxima),
        stop: stopNoMercado(MERCADO, s.minima),
        saida: s.saidaRegra ?? saidas[s.categoria] ?? preferencias[s.categoria].saida,
        lote: null,
      },
      linhas,
      {
        periodoDaNota: textos(MERCADO).periodoDaNota,
        arredondarPreco: (v) => arredondarPreco(MERCADO, v),
      },
    ).cor;
  }
  return notas;
}

/** Tudo o que a ficha da moeda precisa; null se a moeda nao tem candle no banco. */
export async function lerFichaDaMoeda(ticker: string) {
  const dados = await noMercado(MERCADO, async () => {
    const [ficha, nomes, setups] = await Promise.all([
      papel(ticker, DIAS),
      moedas(),
      listarSetups(ticker),
    ]);
    if (ficha.barras.length === 0) return null;
    const [niveis, notas] = await Promise.all([
      niveisDoPapel(ticker, ficha.barras[0].tradeDate),
      notasDosArmados(setups.filter((s) => s.estado === "armado")),
    ]);
    return { ficha, nome: nomes[ticker] ?? null, setups, niveis, notas };
  });
  if (dados === null) return null;

  const desde = dados.ficha.barras[0].tradeDate;
  // O candle de hoje, em andamento, direto da Binance a cada abertura.
  const agora = (await diaDeHoje([ticker]))[ticker];
  const barras = comCandleDeHoje(dados.ficha.barras, agora);
  return {
    ticker,
    nome: dados.nome?.nome ?? null,
    posicao: dados.nome?.posicao ?? null,
    barras,
    aoVivo: barras.length > dados.ficha.barras.length && agora ? agora.hora : null,
    eventos: dados.ficha.eventos.map((e) => ({ tradeDate: e.tradeDate })),
    niveis: dados.niveis,
    setups: dados.setups.filter((s) => s.tradeDate >= desde),
    notas: dados.notas,
  };
}
