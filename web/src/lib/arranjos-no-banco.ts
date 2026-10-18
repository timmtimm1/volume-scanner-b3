/**
 * Os arranjos do Organizar, do lado do servidor.
 *
 * Como os alertas, estas consultas rodam com o site no ar e so depois de
 * `ehDono()`: o arranjo e do dono, e visitante ve sempre o padrao. Uma linha
 * por pagina; sem linha, vale o padrao do codigo.
 *
 * A validacao mora aqui: quem escreve no banco valida o que escreve.
 */

import { COLUNAS_DA_PAGINA, PAGINAS, validarItens } from "./arranjo";
import type { Arranjo, PaginaArrumavel } from "./arranjo";
import { conexaoDeAlertas } from "./db";

export class ArranjoInvalido extends Error {}

export function lerPagina(v: unknown): PaginaArrumavel {
  if (typeof v === "string" && (PAGINAS as readonly string[]).includes(v)) {
    return v as PaginaArrumavel;
  }
  throw new ArranjoInvalido("pagina desconhecida");
}

/** O corpo do PUT: `{pagina, itens}`, com os itens no formato e cabendo nas colunas. */
export function lerPedido(corpo: unknown): { pagina: PaginaArrumavel; itens: Arranjo } {
  if (typeof corpo !== "object" || corpo === null) throw new ArranjoInvalido("pedido invalido");
  const { pagina: bruta, itens: brutos } = corpo as Record<string, unknown>;
  const pagina = lerPagina(bruta);
  const itens = validarItens(brutos, COLUNAS_DA_PAGINA[pagina]);
  if (!itens) throw new ArranjoInvalido("itens invalidos");
  return { pagina, itens };
}

/** Todos os arranjos salvos, por pagina. Linha que nao valida mais e ignorada. */
export async function lerArranjos(): Promise<Partial<Record<PaginaArrumavel, Arranjo>>> {
  try {
    const { rows } = await conexaoDeAlertas().query<{ pagina: string; itens: unknown }>(
      "SELECT pagina, itens FROM volume_scanner.arranjos",
    );
    const arranjos: Partial<Record<PaginaArrumavel, Arranjo>> = {};
    for (const { pagina, itens } of rows) {
      if (!(PAGINAS as readonly string[]).includes(pagina)) continue;
      const validos = validarItens(itens, COLUNAS_DA_PAGINA[pagina as PaginaArrumavel]);
      if (validos) arranjos[pagina as PaginaArrumavel] = validos;
    }
    return arranjos;
  } catch (erro) {
    // Tabela ainda nao criada (deploy antes da migration): ninguem arrumou nada.
    if ((erro as { code?: string }).code === "42P01") return {};
    throw erro;
  }
}

export async function gravarArranjo(pagina: PaginaArrumavel, itens: Arranjo): Promise<void> {
  await conexaoDeAlertas().query(
    `INSERT INTO volume_scanner.arranjos (pagina, itens, atualizado_em)
     VALUES ($1, $2::jsonb, now())
     ON CONFLICT (pagina) DO UPDATE SET itens = EXCLUDED.itens, atualizado_em = now()`,
    [pagina, JSON.stringify(itens)],
  );
}

/** "Restaurar padrao": sem linha, a pagina volta ao padrao do codigo. */
export async function apagarArranjo(pagina: PaginaArrumavel): Promise<void> {
  await conexaoDeAlertas().query("DELETE FROM volume_scanner.arranjos WHERE pagina = $1", [pagina]);
}
