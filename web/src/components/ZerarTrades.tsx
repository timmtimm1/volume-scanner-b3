"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const PALAVRA = "ZERAR";

type Totais = { trades: number; operacoes: number; marcacoes: number };

const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;

/**
 * Zera os trades de cripto em dois passos: baixar o backup e digitar a palavra.
 * O botao de apagar so liga depois do backup conferido. Sem `confirm()` do
 * navegador: a caixa fica na propria pagina, com o que vai sair escrito.
 */
export function ZerarTrades({ totais }: { totais: Totais }) {
  const router = useRouter();
  const [backupFeito, setBackupFeito] = useState(false);
  const [palavra, setPalavra] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function baixarBackup() {
    setOcupado(true);
    setErro(null);
    try {
      const r = await fetch("/api/patrimonio/zerar", { cache: "no-store" });
      if (!r.ok) throw new Error();
      const texto = await r.text();
      const conteudo = JSON.parse(texto) as { trades?: unknown[]; operacoes?: unknown[] };
      if (conteudo.trades?.length !== totais.trades || conteudo.operacoes?.length !== totais.operacoes) {
        setErro("O backup veio diferente do que a tela mostra. Recarregue a página e tente de novo.");
        return;
      }
      const url = URL.createObjectURL(new Blob([texto], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `backup-trades-cripto-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setBackupFeito(true);
    } catch {
      setErro("Não consegui gerar o backup. Nada foi apagado.");
    } finally {
      setOcupado(false);
    }
  }

  async function apagar() {
    setOcupado(true);
    setErro(null);
    try {
      const r = await fetch("/api/patrimonio/zerar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmacao: palavra, esperado: totais.trades }),
      });
      if (!r.ok) {
        const corpo = (await r.json().catch(() => null)) as { erro?: string } | null;
        setErro(corpo?.erro ?? "Não consegui apagar. Nada foi alterado.");
        return;
      }
      setPalavra("");
      setBackupFeito(false);
      router.refresh();
    } catch {
      setErro("Sem resposta do servidor. Recarregue a página para ver se os trades continuam lá.");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[13px] font-semibold leading-relaxed text-tinta-2">
        Apaga de vez {plural(totais.trades, "trade", "trades")} de cripto, com{" "}
        {plural(totais.operacoes, "operação", "operações")} e{" "}
        {plural(totais.marcacoes, "marcação diária", "marcações diárias")}. Trades de ações,
        alertas e o seu capital não mudam.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={baixarBackup}
          disabled={ocupado}
          className="toque h-10 rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta disabled:opacity-50"
        >
          1. Baixar backup
        </button>
        {backupFeito && <span className="text-[13px] font-bold text-alta">✓ Backup baixado</span>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-[13px] font-bold text-tinta-2">
          2. Digite {PALAVRA}
          <input
            value={palavra}
            onChange={(e) => setPalavra(e.target.value)}
            disabled={!backupFeito || ocupado}
            autoComplete="off"
            className="h-10 w-28 rounded-lg border border-linha-2 bg-painel-2 px-3 text-[14px] font-bold outline-none focus:border-acento disabled:opacity-50"
          />
        </label>
        <button
          type="button"
          onClick={apagar}
          disabled={!backupFeito || palavra !== PALAVRA || ocupado}
          className="toque h-10 rounded-full bg-baixa px-4 text-[13px] font-extrabold text-white transition-opacity disabled:opacity-40"
        >
          Apagar {plural(totais.trades, "trade", "trades")}
        </button>
      </div>
      {erro && (
        <p role="alert" className="text-[13px] font-bold text-baixa">
          {erro}
        </p>
      )}
    </div>
  );
}
