"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { numero, reais } from "@/lib/formato";
import { numeroDoTexto, RISCO_PADRAO_PCT, type Perfil } from "@/lib/lote";

type Props = { inicial: Perfil | null };

/** "R$ 10.000" sem centavos redondos, "R$ 10.000,50" com. */
function capitalEmTexto(capital: number): string {
  return reais(capital, Number.isInteger(capital) ? 0 : 2);
}

/** O numero no campo de edicao: sem "R$" e com virgula, como a pessoa digita. */
function paraCampo(v: number): string {
  return String(v).replace(".", ",");
}

/**
 * Capital e risco por trade, salvos na conta. Alimentam a calculadora de lote
 * dos setups. Sem perfil salvo, o editor ja abre: e o convite "Defina seu
 * capital".
 *
 * Salvar grava em `/api/perfil` e recarrega a pagina: os cartoes da aba Setups
 * vem do servidor com o perfil e recalculam o lote sozinhos.
 */
export function PerfilDeRisco({ inicial }: Props) {
  const id = useId();
  const router = useRouter();
  const [perfil, setPerfil] = useState<Perfil | null>(inicial);
  const [editando, setEditando] = useState(inicial === null);
  const [capital, setCapital] = useState(inicial ? paraCampo(inicial.capital) : "");
  const [risco, setRisco] = useState(paraCampo(inicial?.riscoPct ?? RISCO_PADRAO_PCT));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  function abrir() {
    setCapital(perfil ? paraCampo(perfil.capital) : "");
    setRisco(paraCampo(perfil?.riscoPct ?? RISCO_PADRAO_PCT));
    setErro(null);
    setEditando(true);
  }

  async function salvar() {
    const c = numeroDoTexto(capital);
    const r = numeroDoTexto(risco);
    if (c === null || c <= 0) {
      setErro("Digite o capital em reais, maior que zero.");
      return;
    }
    if (r === null || r <= 0 || r > 10) {
      setErro("O risco por trade tem de ficar entre 0 e 10%.");
      return;
    }
    setSalvando(true);
    setErro(null);
    try {
      const resposta = await fetch("/api/perfil/", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ capital: c, riscoPct: r }),
      });
      const corpo = (await resposta.json().catch(() => null)) as
        | { perfil?: Perfil; erro?: string }
        | null;
      if (!resposta.ok || !corpo?.perfil) {
        setErro(corpo?.erro ? `Não consegui salvar: ${corpo.erro}.` : "Não consegui salvar. Tente de novo.");
        return;
      }
      setPerfil(corpo.perfil);
      setEditando(false);
      router.refresh();
    } catch {
      setErro("Sem conexão. Tente de novo.");
    } finally {
      setSalvando(false);
    }
  }

  const campo =
    "num toque h-11 w-full min-w-0 rounded-xl border border-linha-2 bg-painel px-3 text-[14px] font-bold outline-none focus:border-acento";

  return (
    <section id="perfil" className="cartao flex flex-col gap-3 p-4 md:p-5">
      {!editando && perfil ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <p className="num min-w-0 flex-1 text-[14px] font-bold">
            Capital {capitalEmTexto(perfil.capital)}
            <span className="font-semibold text-tinta-3">
              {" "}
              · risco {numero(perfil.riscoPct, Number.isInteger(perfil.riscoPct) ? 0 : 2)}% por trade
            </span>
          </p>
          <button
            type="button"
            onClick={abrir}
            className="toque h-10 rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
          >
            Editar
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-[14px] font-extrabold">
            {perfil ? "Seu capital e o risco por trade" : "Defina seu capital para ver o lote"}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-capital`}>
              <span className="rotulo">Capital (R$)</span>
              <input
                id={`${id}-capital`}
                type="text"
                inputMode="decimal"
                value={capital}
                onChange={(e) => setCapital(e.target.value)}
                placeholder="10000"
                className={campo}
              />
            </label>
            <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-risco`}>
              <span className="rotulo">Risco por trade (%)</span>
              <input
                id={`${id}-risco`}
                type="text"
                inputMode="decimal"
                value={risco}
                onChange={(e) => setRisco(e.target.value)}
                placeholder="1"
                className={campo}
              />
            </label>
          </div>
          <p className="text-[12px] font-semibold text-tinta-3">
            O risco é quanto do capital você aceita perder se o stop for atingido. O lote sai dessa
            conta, em ações inteiras.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={salvar}
              disabled={salvando || capital.trim() === "" || risco.trim() === ""}
              className="toque h-11 flex-1 rounded-full bg-primario px-5 text-[14px] font-extrabold text-primario-tinta disabled:opacity-40 sm:flex-none"
            >
              {salvando ? "Salvando…" : "Salvar"}
            </button>
            {perfil && (
              <button
                type="button"
                onClick={() => setEditando(false)}
                className="toque h-11 rounded-full px-4 text-[14px] font-bold text-tinta-3 hover:text-tinta"
              >
                Cancelar
              </button>
            )}
          </div>
        </div>
      )}
      {erro && (
        <p role="alert" className="text-[12px] font-bold text-baixa">
          {erro}
        </p>
      )}
    </section>
  );
}
