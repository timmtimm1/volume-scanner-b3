/**
 * A aba Patrimonio, do lado do servidor: le os trades de cripto e monta a curva.
 * As contas moram em `patrimonio.ts`. Sempre depois de `ehDono()`.
 */

import { diaDeHoje } from "./cripto-hoje-binance";
import { conexaoDeAlertas } from "./db";
import { diaDoMercado } from "./mercado";
import { noMercado } from "./mercado-servidor";
import { montarCurva, resumirCurva, type TradeDaCurva } from "./patrimonio";
import { lerPerfil } from "./perfil";
import { marcarAgora } from "./posicao";
import { listarTrades } from "./trades";

const MERCADO = "cripto" as const;

export async function lerPatrimonio() {
  const { trades, perfil, snapshots, contagem } = await noMercado(MERCADO, async () => {
    const pool = conexaoDeAlertas();
    const [trades, perfil, { rows: snapshots }, { rows: contagem }] = await Promise.all([
      listarTrades(),
      lerPerfil(),
      pool.query<{ trade_id: string; dia: string; resultado: string }>(
        `SELECT trade_id, trade_date::text AS dia, resultado
           FROM volume_scanner.trade_snapshots
          ORDER BY trade_id, trade_date`,
      ),
      pool.query<{ operacoes: string; marcacoes: string }>(
        `SELECT (SELECT count(*) FROM volume_scanner.trade_operacoes) AS operacoes,
                (SELECT count(*) FROM volume_scanner.trade_snapshots) AS marcacoes`,
      ),
    ]);
    return { trades, perfil, snapshots, contagem };
  });

  const porTrade = new Map<number, { data: string; resultado: number }[]>();
  for (const s of snapshots) {
    const id = Number(s.trade_id);
    const lista = porTrade.get(id) ?? [];
    lista.push({ data: s.dia, resultado: Number(s.resultado) });
    porTrade.set(id, lista);
  }

  const abertos = trades.filter((t) => t.encerradoEm === null);
  const agora = abertos.length > 0 ? await diaDeHoje(abertos.map((t) => t.ticker)) : {};
  const paraCurva: TradeDaCurva[] = trades.map((t) => ({
    id: t.id,
    operacoes: t.operacoes,
    snapshots: porTrade.get(t.id) ?? [],
    resultadoAgora:
      t.encerradoEm === null
        ? marcarAgora(t, agora[t.ticker]?.ultimo ?? t.ultimoSnapshot?.fechamento ?? null).resultado
        : null,
  }));

  const capital = perfil?.capital ?? 0;
  const curva = perfil ? montarCurva(capital, paraCurva, diaDoMercado(MERCADO, new Date())) : [];
  return {
    perfil,
    curva,
    resumo: resumirCurva(capital, curva),
    totais: {
      trades: trades.length,
      abertos: abertos.length,
      operacoes: Number(contagem[0].operacoes),
      marcacoes: Number(contagem[0].marcacoes),
    },
  };
}
