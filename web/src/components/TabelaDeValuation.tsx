"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { numero, reais } from "@/lib/formato";
import type { LinhaDeValuation } from "@/lib/valuation-dados";
import { type Metodo, NOME_DO_METODO, textoDaDiferenca } from "@/lib/valuation";
import { COR_DO_SINAL, Luz } from "./BlocoDeValuation";

/**
 * A lista de todas as empresas com as tres contas de preco justo, ordenavel
 * pela diferenca de cada metodo. No celular cada papel vira um cartao; no
 * computador, uma tabela.
 */

type Ordem = "abaixo" | Metodo | "ticker";

const METODOS: readonly Metodo[] = ["graham", "bazin", "dcf"];
/** Mediana de volume a partir da qual o papel conta como liquido: o piso do scanner. */
const PISO_DE_LIQUIDEZ = 500_000;

function diferenca(l: LinhaDeValuation, m: Metodo): number | null {
  return l.avaliacoes.find((a) => a.metodo === m)?.diferenca ?? null;
}

function quantosAbaixo(l: LinhaDeValuation): number {
  return l.avaliacoes.filter((a) => a.sinal === "abaixo").length;
}

function comparar(ordem: Ordem): (a: LinhaDeValuation, b: LinhaDeValuation) => number {
  if (ordem === "ticker") return (a, b) => a.ticker.localeCompare(b.ticker);
  if (ordem === "abaixo") {
    // mais metodos abaixo primeiro; no empate, a menor diferenca media
    const media = (l: LinhaDeValuation) => {
      const ds = l.avaliacoes.map((a) => a.diferenca).filter((d): d is number => d !== null);
      return ds.length ? ds.reduce((s, d) => s + d, 0) / ds.length : Infinity;
    };
    return (a, b) => quantosAbaixo(b) - quantosAbaixo(a) || media(a) - media(b);
  }
  // sem conta vai para o fim, em qualquer ordem
  return (a, b) => (diferenca(a, ordem) ?? Infinity) - (diferenca(b, ordem) ?? Infinity);
}

function Celula({ l, m }: { l: LinhaDeValuation; m: Metodo }) {
  const a = l.avaliacoes.find((x) => x.metodo === m);
  if (!a || a.precoJusto === null) {
    return (
      <span className="text-[12px] font-semibold text-tinta-3" title={a?.motivo ?? undefined}>
        —
      </span>
    );
  }
  return (
    <span className="flex items-center justify-end gap-2" title={a.sinal ? COR_DO_SINAL[a.sinal].rotulo : undefined}>
      <Luz sinal={a.sinal} />
      <span className="num text-[13px] font-bold">{reais(a.precoJusto)}</span>
      <span className={`num w-[86px] text-right text-[12px] font-bold ${a.sinal ? COR_DO_SINAL[a.sinal].texto : ""}`}>
        {textoDaDiferenca(a.diferenca)}
      </span>
    </span>
  );
}

export function TabelaDeValuation({ linhas }: { linhas: LinhaDeValuation[] }) {
  const [ordem, setOrdem] = useState<Ordem>("abaixo");
  const [busca, setBusca] = useState("");
  const [soLiquidos, setSoLiquidos] = useState(true);

  const visiveis = useMemo(() => {
    const termo = busca.trim().toUpperCase();
    return linhas
      .filter((l) => !soLiquidos || (l.volume ?? 0) >= PISO_DE_LIQUIDEZ)
      .filter(
        (l) => termo === "" || l.ticker.includes(termo) || l.empresa.toUpperCase().includes(termo),
      )
      .sort(comparar(ordem));
  }, [linhas, ordem, busca, soLiquidos]);

  const opcoes: { valor: Ordem; rotulo: string }[] = [
    { valor: "abaixo", rotulo: "Mais métodos abaixo" },
    ...METODOS.map((m) => ({ valor: m as Ordem, rotulo: NOME_DO_METODO[m] })),
    { valor: "ticker", rotulo: "A–Z" },
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar papel ou empresa"
          aria-label="Buscar papel ou empresa"
          className="toque h-10 min-w-0 flex-1 rounded-full border border-linha-2 bg-painel px-4 text-[14px] font-semibold outline-none focus:border-acento md:max-w-[280px]"
        />
        <label className="toque flex h-10 items-center gap-2 rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2">
          <input
            type="checkbox"
            checked={soLiquidos}
            onChange={(e) => setSoLiquidos(e.target.checked)}
            className="accent-[var(--acento)]"
          />
          só líquidos
        </label>
        <span className="num text-[12px] font-semibold text-tinta-3">{visiveis.length} papéis</span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Ordenar por">
        <span className="text-[12px] font-bold text-tinta-3">Ordenar:</span>
        {opcoes.map((o) => (
          <button
            key={o.valor}
            type="button"
            onClick={() => setOrdem(o.valor)}
            aria-pressed={ordem === o.valor}
            className={`toque h-9 rounded-full px-3.5 text-[12px] font-bold transition-colors ${
              ordem === o.valor
                ? "bg-primario text-primario-tinta"
                : "border border-linha-2 text-tinta-2 hover:text-tinta"
            }`}
          >
            {o.rotulo}
          </button>
        ))}
      </div>

      {visiveis.length === 0 ? (
        <p className="py-4 text-[13px] font-semibold text-tinta-3">Nenhum papel com esse filtro.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-linha">
          <li className="hidden items-center gap-3 pb-2 md:flex">
            <span className="rotulo w-[190px]">Papel</span>
            <span className="rotulo w-[84px] text-right">Preço</span>
            {METODOS.map((m) => (
              <span key={m} className="rotulo flex-1 text-right">
                {NOME_DO_METODO[m]}
              </span>
            ))}
          </li>
          {visiveis.map((l) => (
            <li key={l.ticker} className="flex flex-col gap-1.5 py-3 md:flex-row md:items-center md:gap-3 md:py-2">
              <div className="flex items-baseline gap-2 md:w-[190px] md:flex-col md:items-start md:gap-0">
                <Link
                  href={`/papel/${l.ticker}`}
                  className="text-[15px] font-extrabold transition-colors hover:text-acento"
                >
                  {l.ticker}
                </Link>
                <span className="min-w-0 flex-1 truncate text-[11px] font-semibold text-tinta-3 md:w-full md:flex-none">
                  {l.empresa} · {l.trimestre}
                </span>
                <span className="num text-[13px] font-bold md:hidden">{reais(l.preco)}</span>
              </div>
              <span className="num hidden w-[84px] text-right text-[13px] font-bold md:inline">
                {reais(l.preco)}
              </span>
              {METODOS.map((m) => (
                <div key={m} className="flex items-center justify-between gap-2 md:flex-1 md:justify-end">
                  <span className="text-[12px] font-semibold text-tinta-3 md:hidden">
                    {NOME_DO_METODO[m]}
                  </span>
                  <Celula l={l} m={m} />
                </div>
              ))}
            </li>
          ))}
        </ul>
      )}
      <p className="text-[11px] font-semibold text-tinta-3">
        Líquido = mediana de volume acima de R$ {numero(PISO_DE_LIQUIDEZ / 1000, 0)} mil nos
        últimos 60 pregões, o mesmo piso do scanner.
      </p>
    </div>
  );
}
