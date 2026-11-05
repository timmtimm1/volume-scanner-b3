"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { ORDEM_DAS_SAIDAS, SAIDAS } from "@/lib/backtest-tela";
import type { CategoriaDoSetup, SaidaDoSetup } from "@/lib/config";

type Props = { categoria: CategoriaDoSetup; alerta: boolean; saida: SaidaDoSetup };

/**
 * O que o usuario escolhe para um setup: alerta ligado ou nao, e a saida.
 * Salvar grava em `setup_preferencias` e recarrega a pagina -- o bloco muda de
 * lugar (entre "ligados" e "outros") sozinho, porque a lista vem do servidor.
 */
export function PreferenciaDoSetup({ categoria, alerta, saida }: Props) {
  const id = useId();
  const router = useRouter();
  const [alertaNovo, setAlertaNovo] = useState(alerta);
  const [saidaNova, setSaidaNova] = useState<SaidaDoSetup>(saida);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const mudou = alertaNovo !== alerta || saidaNova !== saida;

  async function salvar() {
    setSalvando(true);
    setErro(null);
    try {
      const r = await fetch("/api/setups/preferencias/", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ categoria, alerta: alertaNovo, saida: saidaNova }),
      });
      if (!r.ok) {
        const corpo = (await r.json().catch(() => null)) as { erro?: string } | null;
        setErro(corpo?.erro ?? "Não consegui salvar. Tente de novo.");
        return;
      }
      router.refresh();
    } catch {
      setErro("Sem conexão. Tente de novo.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-painel-2 p-3.5">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <button
          type="button"
          role="switch"
          aria-checked={alertaNovo}
          onClick={() => setAlertaNovo((v) => !v)}
          className="toque flex items-center gap-3"
        >
          <span
            className={`relative inline-block h-7 w-12 shrink-0 rounded-full transition-colors ${
              alertaNovo ? "bg-primario" : "bg-linha-2"
            }`}
          >
            <span
              className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow transition-all ${
                alertaNovo ? "left-6" : "left-1"
              }`}
            />
          </span>
          <span className="text-[14px] font-bold">Alerta {alertaNovo ? "ligado" : "desligado"}</span>
        </button>

        {/* no celular o seletor ganha a linha inteira: espremido, so a seta aparecia */}
        <div className="flex min-w-0 flex-1 basis-full flex-col gap-1 sm:basis-0">
          <label htmlFor={`${id}-saida`} className="rotulo">
            Saída
          </label>
          <select
            id={`${id}-saida`}
            value={saidaNova}
            onChange={(e) => setSaidaNova(e.target.value as SaidaDoSetup)}
            className="toque h-11 w-full min-w-0 rounded-xl border border-linha-2 bg-painel px-3 text-[14px] font-bold text-tinta"
          >
            {ORDEM_DAS_SAIDAS.map((s) => (
              <option key={s} value={s}>
                {SAIDAS[s]}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          onClick={salvar}
          disabled={!mudou || salvando}
          className="toque h-11 rounded-full bg-primario px-5 text-[14px] font-extrabold text-primario-tinta disabled:opacity-40"
        >
          {salvando ? "Salvando…" : "Salvar"}
        </button>
      </div>
      <p className="text-[12px] font-semibold text-tinta-3">
        Vale para os setups que armarem a partir da próxima noite; os que já estão em andamento
        seguem a saída com que armaram.
      </p>
      {erro && (
        <p role="alert" className="text-[12px] font-bold text-baixa">
          {erro}
        </p>
      )}
    </div>
  );
}
