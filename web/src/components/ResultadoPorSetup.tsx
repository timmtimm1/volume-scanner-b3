import Link from "next/link";
import { fmtR } from "@/lib/backtest-tela";
import { estatisticaPorSetup } from "@/lib/diario";
import { proporcao } from "@/lib/formato";
import { CATEGORIAS_DE_SETUP } from "@/lib/config";
import { regrasDoDiario, type Mercado } from "@/lib/mercado";
import {
  chaveDoBacktest,
  NOME_NO_DIARIO,
  ordemNoDiario,
  type CategoriaDoSetup,
} from "@/lib/setups-tela";
import type { TradeResumo } from "@/lib/trades";
import type { CategoriaDoDiario } from "@/lib/config";

/** A pagina do backtest de cada mercado. */
const BACKTEST: Record<Mercado, string> = { b3: "/setups/backtest", cripto: "/cripto/backtest" };

/**
 * "Seu resultado por setup": o diario, so com trades encerrados. A ordem e a
 * dos setups na aba Setups, nunca por resultado: o quadro mostra o que
 * aconteceu, nao quem "ganhou". Em R o resultado nao tem moeda, entao o filtro
 * "Tudo" soma os dois mercados; o link para o backtest so aparece com um
 * mercado escolhido (o mesmo setup tem um backtest em cada).
 */
export function ResultadoPorSetup({
  trades,
  mercado,
}: {
  trades: TradeResumo[];
  /** O mercado do filtro; null = os dois. */
  mercado: Mercado | null;
}) {
  const ordem = ordemNoDiario(regrasDoDiario("cripto").categoriasDoEstudo);
  const linhas = estatisticaPorSetup(trades, ordem);
  if (linhas.length === 0) return null;
  const daAba = (c: string | null): c is CategoriaDoSetup =>
    c !== null && (CATEGORIAS_DE_SETUP as readonly string[]).includes(c);

  return (
    <section className="cartao flex flex-col gap-3 p-4 md:p-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-[16px] font-extrabold">Seu resultado por setup</h2>
        <p className="text-[12px] font-semibold text-tinta-3">
          Só trades encerrados. R é o resultado dividido pelo risco do trade: +1 R é ganhar o que se
          arriscava, −1 R é perder. Trade sem stop entra na contagem, mas fica de fora do R.
        </p>
      </div>

      <ul className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {linhas.map((l) => (
          <li key={l.categoria ?? "sem-setup"} className="flex flex-col gap-2 rounded-2xl bg-painel-2 p-3.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <span className="text-[15px] font-extrabold">
                {l.categoria === null ? "Sem setup" : NOME_NO_DIARIO[l.categoria as CategoriaDoDiario]}
              </span>
              <span className="num text-[12px] font-semibold text-tinta-3">
                {l.encerrados} {l.encerrados === 1 ? "trade encerrado" : "trades encerrados"}
                {l.comR < l.encerrados && ` · ${l.comR} com stop`}
              </span>
            </div>
            <dl className="grid grid-cols-3 gap-2">
              <div className="flex min-w-0 flex-col gap-0.5">
                <dt className="rotulo">Acerto</dt>
                <dd className="num text-[14px] font-extrabold">
                  {l.acerto === null ? "—" : proporcao(l.acerto, 0)}
                </dd>
              </div>
              <div className="flex min-w-0 flex-col gap-0.5">
                <dt className="rotulo">Média</dt>
                <dd className="num text-[14px] font-extrabold">
                  {l.mediaR === null ? "—" : fmtR(l.mediaR)}
                </dd>
              </div>
              <div className="flex min-w-0 flex-col gap-0.5">
                <dt className="rotulo">Soma</dt>
                <dd className="num text-[14px] font-extrabold">
                  {l.acerto === null ? "—" : fmtR(l.somaR)}
                </dd>
              </div>
            </dl>
            {mercado !== null && daAba(l.categoria) && (
              <Link
                href={`${BACKTEST[mercado]}?setup=${encodeURIComponent(chaveDoBacktest(l.categoria))}`}
                className="toque inline-flex h-9 w-fit items-center text-[12px] font-bold text-acento hover:underline"
              >
                ver no Backtest
              </Link>
            )}
          </li>
        ))}
      </ul>

      <p className="text-[12px] font-semibold text-tinta-3">
        Com poucos trades o número muda muito; compare com o backtest e com a conferência ao vivo na
        aba Setups (ou Cripto).
      </p>
    </section>
  );
}
