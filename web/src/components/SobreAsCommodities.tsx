import Link from "next/link";
import { COMMODITIES, SOBRE_OS_CONTRATOS, SOBRE_OS_TOKENS } from "@/lib/commodities";

const ETIQUETA = { token: "token de ouro", contrato: "contrato perpétuo" } as const;

function Bullets({ titulo, itens }: { titulo: string; itens: readonly string[] }) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-[13px] font-extrabold text-tinta">{titulo}</h3>
      <ul className="flex list-disc flex-col gap-1 pl-5 text-[13px] leading-relaxed text-tinta-2">
        {itens.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
    </div>
  );
}

/** O cartão "As commodities" da aba Por ano: quem são, e o que muda de um tipo para o outro. */
export function SobreAsCommodities() {
  return (
    <section className="cartao flex flex-col gap-3 p-4 md:p-5">
      <h2 className="text-[16px] font-extrabold">As commodities</h2>
      <ul className="divide-y divide-linha">
        {Object.values(COMMODITIES).map((c) => (
          <li key={c.ticker}>
            <Link
              href={`/analise/${encodeURIComponent(c.ticker)}`}
              className="toque flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-2 text-[13px] hover:text-acento"
            >
              <b className="font-extrabold text-tinta">{c.ticker}</b>
              <span className="font-semibold text-tinta">{c.nome}</span>
              <span className="rounded-md bg-painel-2 px-1.5 py-0.5 text-[11px] font-extrabold text-tinta-3">
                {ETIQUETA[c.tipo]}
              </span>
              <span className="min-w-0 text-[12px] font-semibold text-tinta-3">{c.unidade}</span>
            </Link>
          </li>
        ))}
      </ul>
      <Bullets titulo="Tokens de ouro" itens={SOBRE_OS_TOKENS} />
      <Bullets titulo="Contratos" itens={SOBRE_OS_CONTRATOS} />
    </section>
  );
}
