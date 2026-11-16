/**
 * Em qual mercado as consultas deste pedido rodam (so no servidor).
 *
 * Todas as consultas do site nomeiam o schema da B3 (`volume_scanner.tabela`).
 * As criptos vivem em `cripto_scanner`, com as mesmas tabelas. Em vez de dar um
 * parametro de mercado a cada uma das ~90 consultas, a pagina de cripto roda a
 * leitura dentro de `noMercado("cripto", ...)` e a conexao troca o nome do
 * schema no texto do SQL (`db.ts`). Fora dessa chamada nada muda: o padrao e a
 * B3, e as paginas das acoes nem sabem que isto existe.
 *
 * O contexto acompanha os `await` (AsyncLocalStorage). Ele NAO acompanha um
 * componente filho que busca dado por conta propria: tudo o que a pagina de
 * cripto le do banco tem de ser lido dentro da chamada, e descer como prop.
 */

import { AsyncLocalStorage } from "node:async_hooks";
import type { Mercado } from "./mercado";

const SCHEMA_DA_B3 = "volume_scanner.";
const SCHEMA_DE_CRIPTO = "cripto_scanner.";

const contexto = new AsyncLocalStorage<Mercado>();

export function noMercado<T>(mercado: Mercado, leitura: () => Promise<T>): Promise<T> {
  return contexto.run(mercado, leitura);
}

export function mercadoDoPedido(): Mercado {
  return contexto.getStore() ?? "b3";
}

/** O SQL como deve ir ao banco no mercado do pedido. */
export function sqlDoMercado(texto: string, mercado: Mercado = mercadoDoPedido()): string {
  return mercado === "cripto" ? texto.replaceAll(SCHEMA_DA_B3, SCHEMA_DE_CRIPTO) : texto;
}
