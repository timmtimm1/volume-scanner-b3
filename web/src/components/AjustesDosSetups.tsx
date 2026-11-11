import Link from "next/link";
import { fmtR, type Nivel, SAIDAS } from "@/lib/backtest-tela";
import type { CategoriaDoSetup, SaidaDoSetup } from "@/lib/config";
import {
  chaveDoBacktest,
  type Conferencia,
  NOME_DO_SETUP,
  ORDEM_DAS_CATEGORIAS,
  type Preferencias,
  textoAoVivo,
} from "@/lib/setups-tela";
import { PreferenciaDoSetup } from "./PreferenciaDoSetup";
import { Selo } from "./ResumoDoBacktest";

type Props = {
  preferencias: Preferencias;
  niveis: Partial<Record<CategoriaDoSetup, Nivel>>;
  conferencias: Partial<Record<CategoriaDoSetup, Conferencia>>;
  /** A saida que o backtest escolheu para cada setup (a melhor em 1995-2015). */
  saidasDoBacktest: Partial<Record<CategoriaDoSetup, SaidaDoSetup>>;
};

/**
 * Os ajustes de cada setup, um por linha, na ordem fixa do Backtest: alerta,
 * saida, a nota e a conferencia ao vivo. Fica recolhido no fim da aba -- e o
 * que se mexe de vez em quando, nao o que se le todo dia.
 */
export function AjustesDosSetups({ preferencias, niveis, conferencias, saidasDoBacktest }: Props) {
  return (
    <ul className="flex flex-col divide-y divide-linha">
      {ORDEM_DAS_CATEGORIAS.map((categoria) => {
        const pref = preferencias[categoria];
        const nivel = niveis[categoria];
        const conferencia = conferencias[categoria];
        const bt = conferencia?.backtest;
        const melhor = saidasDoBacktest[categoria];
        return (
          <li key={categoria} className="flex flex-col gap-2.5 py-4 first:pt-0 last:pb-0">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <h3 className="text-[16px] font-extrabold">{NOME_DO_SETUP[categoria]}</h3>
              {nivel && <Selo nivel={nivel} />}
              <span className="flex-1" />
              <Link
                href={`/setups/backtest?setup=${encodeURIComponent(chaveDoBacktest(categoria))}`}
                className="text-[13px] font-bold text-acento hover:underline"
              >
                ver no Backtest
              </Link>
            </div>
            <PreferenciaDoSetup
              key={`${pref.alerta}-${pref.saida}`}
              categoria={categoria}
              alerta={pref.alerta}
              saida={pref.saida}
            />
            {melhor && melhor !== pref.saida && (
              <p className="text-[12px] font-bold text-evento-tinta">
                A melhor saída deste setup no backtest é “{SAIDAS[melhor]}”. A nota do cartão é
                medida com a saída que estiver escolhida aqui.
              </p>
            )}
            <p className="num text-[12px] font-semibold text-tinta-3">
              {textoAoVivo(conferencia?.aoVivo ?? null)}
              {bt && bt.r !== null && <> · Backtest 2016–2026: {fmtR(bt.r)} por trade, já com custo</>}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
