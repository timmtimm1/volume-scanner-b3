/**
 * Perfil de risco do dono (capital e risco por trade), salvo na conta: uma
 * linha so, `volume_scanner.perfil_de_risco` (migration 0018). Do lado do
 * servidor; a conta do lote e a validacao moram em `lote.ts`, puro.
 *
 * Toda funcao daqui e chamada apenas depois de `ehDono()`.
 */

import { conexaoDeAlertas } from "./db";
import { type Perfil, validarPerfil } from "./lote";

export { PerfilInvalido, type Perfil } from "./lote";

/** Tabela ou coluna ausente: a migration 0018 ainda nao rodou neste banco. */
export function faltaAMigration(erro: unknown): boolean {
  const codigo = (erro as { code?: string } | null)?.code;
  return codigo === "42P01" || codigo === "42703";
}

/** O perfil salvo, ou null se ainda nao ha (ou a migration ainda nao rodou). */
export async function lerPerfil(): Promise<Perfil | null> {
  try {
    const { rows } = await conexaoDeAlertas().query<{
      capital: string | number;
      risco_pct: string | number;
    }>("SELECT capital, risco_pct FROM volume_scanner.perfil_de_risco WHERE id = 1");
    if (rows.length === 0) return null;
    return { capital: Number(rows[0].capital), riscoPct: Number(rows[0].risco_pct) };
  } catch (erro) {
    if (faltaAMigration(erro)) return null;
    throw erro;
  }
}

/**
 * Valida e grava. Lanca `PerfilInvalido` (campo ruim) ou o erro do banco --
 * inclusive 42P01 se a tabela nao existe, que a rota traduz em 503.
 */
export async function gravarPerfil(entrada: unknown): Promise<Perfil> {
  const corpo = entrada !== null && typeof entrada === "object" ? (entrada as Record<string, unknown>) : {};
  const perfil = validarPerfil(corpo);
  await conexaoDeAlertas().query(
    `INSERT INTO volume_scanner.perfil_de_risco (id, capital, risco_pct, atualizado_em)
          VALUES (1, $1, $2, now())
     ON CONFLICT (id)
       DO UPDATE SET capital = EXCLUDED.capital, risco_pct = EXCLUDED.risco_pct,
                     atualizado_em = now()`,
    [perfil.capital, perfil.riscoPct],
  );
  return perfil;
}
