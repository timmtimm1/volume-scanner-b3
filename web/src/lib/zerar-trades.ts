/**
 * Backup e apagamento dos trades de CRIPTO (pedido de 23/11/2026). Apagar nao tem
 * volta, entao as duas funcoes recusam rodar fora de `noMercado("cripto", ...)`:
 * um erro de quem chama nunca pode alcancar os trades de acoes.
 *
 * Alertas e o perfil de risco nao entram. Operacoes e marcacoes diarias saem junto
 * com o trade, pelo ON DELETE CASCADE.
 */

import type { PoolClient } from "pg";
import { conexaoDeAlertas } from "./db";
import { mercadoDoPedido } from "./mercado-servidor";

/** A quantidade de trades mudou desde que a tela foi aberta. */
export class ContagemMudou extends Error {
  constructor(readonly atual: number) {
    super("a quantidade de trades mudou");
  }
}

function exigirCripto(): void {
  if (mercadoDoPedido() !== "cripto") throw new Error("zerar trades so vale para cripto");
}

/**
 * Os trades, as operacoes e as marcacoes num JSON so. Montado pelo Postgres e
 * devolvido como texto: datas seguem AAAA-MM-DD e os precos de 10 casas nao passam
 * pelo `number` do JavaScript, que os arredondaria.
 */
export async function backupDosTrades(): Promise<string> {
  exigirCripto();
  const { rows } = await conexaoDeAlertas().query<{ backup: string }>(
    `SELECT json_build_object(
              'formato', 1,
              'mercado', 'cripto',
              'geradoEm', now(),
              'trades', COALESCE((SELECT json_agg(t ORDER BY t.id)
                                    FROM volume_scanner.trades t), '[]'::json),
              'operacoes', COALESCE((SELECT json_agg(o ORDER BY o.trade_id, o.data, o.id)
                                       FROM volume_scanner.trade_operacoes o), '[]'::json),
              'marcacoes', COALESCE((SELECT json_agg(s ORDER BY s.trade_id, s.trade_date)
                                       FROM volume_scanner.trade_snapshots s), '[]'::json)
            )::text AS backup`,
  );
  return rows[0].backup;
}

/**
 * Apaga todos os trades de cripto, numa transacao. So apaga se ainda existir a
 * quantidade que a pessoa viu na tela: um trade registrado depois (em outra aba,
 * por exemplo) nao esta no backup e nao pode sumir sem aviso.
 */
export async function zerarTrades(esperado: number): Promise<{ apagados: number }> {
  exigirCripto();
  const client = (await conexaoDeAlertas().connect()) as PoolClient;
  try {
    await client.query("BEGIN");
    // Segura novas gravacoes entre a contagem e o DELETE.
    await client.query("LOCK TABLE volume_scanner.trades IN SHARE ROW EXCLUSIVE MODE");
    const { rows } = await client.query<{ n: string }>(
      "SELECT count(*) AS n FROM volume_scanner.trades",
    );
    const atual = Number(rows[0].n);
    if (atual !== esperado) throw new ContagemMudou(atual);
    const { rowCount } = await client.query("DELETE FROM volume_scanner.trades");
    await client.query("COMMIT");
    return { apagados: rowCount ?? 0 };
  } catch (erro) {
    await client.query("ROLLBACK");
    throw erro;
  } finally {
    client.release();
  }
}
