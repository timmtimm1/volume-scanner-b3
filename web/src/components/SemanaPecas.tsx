import Link from "next/link";
import type { ReactNode } from "react";
import { percentual } from "@/lib/formato";

/** Pecas visuais repetidas nos blocos do resumo da semana. */

/** Verde e vermelho SO para direcao de preco. Variacao nula fica neutra. */
export function corDaVariacao(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "text-tinta-3";
  const arredondado = Number((v * 100).toFixed(1));
  if (arredondado === 0) return "text-tinta-2";
  return arredondado > 0 ? "text-alta" : "text-baixa";
}

/** Variacao de preco em fracao: `+22,2%`, na cor da direcao. */
export function Variacao({
  valor,
  className = "",
}: {
  valor: number | null | undefined;
  className?: string;
}) {
  return (
    <span className={`num font-bold ${corDaVariacao(valor)} ${className}`}>
      {percentual(valor)}
    </span>
  );
}

/**
 * Um bloco do resumo. Com `indisponivel`, o cartao fica com o titulo e a frase
 * fixa; o texto tecnico do erro vai so no `title`, para quem passar o mouse.
 */
export function Bloco({
  titulo,
  subtitulo,
  indisponivel,
  children,
  className = "",
}: {
  titulo: string;
  subtitulo?: ReactNode;
  indisponivel?: string | null;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`cartao flex min-w-0 flex-col gap-3 p-4 md:p-5 ${className}`}>
      <div className="flex flex-col gap-0.5">
        <h2 className="text-[17px] font-extrabold tracking-tight">{titulo}</h2>
        {subtitulo && <p className="num text-[12px] font-semibold text-tinta-3">{subtitulo}</p>}
      </div>
      {indisponivel != null ? <Indisponivel motivo={indisponivel} /> : children}
    </section>
  );
}

export function Indisponivel({ motivo }: { motivo: string }) {
  return (
    <p
      title={motivo}
      className="rounded-2xl bg-painel-2 px-4 py-3 text-[13px] font-semibold text-tinta-3"
    >
      Indisponível nesta edição
    </p>
  );
}

/** Subtitulo de secao dentro de um bloco. */
export function Rotulo({ children }: { children: ReactNode }) {
  return <h3 className="rotulo">{children}</h3>;
}

/** Link para a ficha do papel. Sem prefetch: sao dezenas por tela e cada ficha e pesada. */
export function LinkDoPapel({ ticker, className = "" }: { ticker: string; className?: string }) {
  return (
    <Link
      href={`/papel/${ticker}`}
      prefetch={false}
      className={`font-extrabold text-acento hover:underline ${className}`}
    >
      {ticker}
    </Link>
  );
}

/** Nota de rodape do bloco: pequena e discreta. */
export function Nota({ children }: { children: ReactNode }) {
  return <p className="text-[11px] leading-relaxed text-tinta-3">{children}</p>;
}
