"use client";

import { useState } from "react";
import { type Ano, fmtR } from "@/lib/backtest-tela";

/**
 * R por trade de cada ano, em barras. 31 anos em 390px: a lista rola na
 * horizontal por dentro do cartao, com barras de largura fixa, e a pagina nao
 * estoura. Verde acima de zero, vermelho abaixo (so aqui a cor diz "ganhou" ou
 * "perdeu"). O n do ano esta no title (mouse) e na linha de leitura, que o toque
 * numa barra preenche (celular nao tem title).
 */
export function AnosDoBacktest({ anos }: { anos: Ano[] }) {
  const [aberto, setAberto] = useState<number | null>(null);
  const comValor = anos.filter((a) => a.expectativa !== null);
  if (comValor.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-linha-2 p-6 text-center text-[13px] font-semibold text-tinta-3">
        Sem dados ano a ano para esta combinação.
      </p>
    );
  }
  // A escala e simetrica em torno do zero, com piso para um ano so nao esticar.
  const teto = Math.max(0.2, ...comValor.map((a) => Math.abs(a.expectativa ?? 0)));
  const ALTURA = 72; // px de cada lado do zero
  const lido = anos.find((a) => a.ano === aberto) ?? comValor[comValor.length - 1];

  return (
    <div className="flex flex-col gap-2">
      <div className="-mx-1 overflow-x-auto px-1 pb-1">
        <ul className="flex min-w-[330px] items-stretch gap-px" aria-label="R por trade de cada ano">
          {anos.map((a) => {
            const v = a.expectativa;
            const h = v === null ? 0 : Math.max(2, (Math.abs(v) / teto) * ALTURA);
            const positivo = (v ?? 0) >= 0;
            return (
              <li key={a.ano} className="min-w-[10px] flex-1">
                <button
                  type="button"
                  onClick={() => setAberto(a.ano)}
                  onMouseEnter={() => setAberto(a.ano)}
                  title={`${a.ano}: ${fmtR(v)} por trade, ${a.n} trade${a.n === 1 ? "" : "s"}`}
                  aria-pressed={lido.ano === a.ano}
                  className={`flex w-full flex-col items-center rounded-sm ${
                    lido.ano === a.ano ? "bg-selecao" : ""
                  }`}
                >
                <div className="flex w-full items-end justify-center" style={{ height: ALTURA }}>
                  {v !== null && positivo && (
                    <span className="block w-[70%] rounded-t-sm bg-alta" style={{ height: h }} />
                  )}
                </div>
                <div className="h-px w-full bg-linha-2" />
                <div className="flex w-full items-start justify-center" style={{ height: ALTURA }}>
                  {v !== null && !positivo && (
                    <span className="block w-[70%] rounded-b-sm bg-baixa" style={{ height: h }} />
                  )}
                </div>
                <span className="num mt-1 h-[34px] text-[10px] font-semibold text-tinta-3 [writing-mode:vertical-rl]">
                  {a.ano % 5 === 0 || lido.ano === a.ano ? a.ano : ""}
                </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      <p className="num text-[13px] font-bold">
        {lido.ano}: {fmtR(lido.expectativa)} por trade
        <span className="font-semibold text-tinta-3">
          {" "}
          · {lido.n} trade{lido.n === 1 ? "" : "s"}
        </span>
      </p>
      <p className="text-[12px] font-semibold text-tinta-3">
        R por trade em cada ano, já com custo. Ano com poucos trades balança muito: toque numa
        barra para ver o número de trades.
      </p>
    </div>
  );
}
