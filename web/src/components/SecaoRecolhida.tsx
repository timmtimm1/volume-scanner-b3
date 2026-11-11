/** Uma secao da aba que nasce fechada: o titulo, a contagem e a seta; toca e abre. */
export function SecaoRecolhida({
  titulo,
  contagem,
  children,
}: {
  titulo: string;
  contagem?: number;
  children: React.ReactNode;
}) {
  return (
    <details className="cartao group">
      <summary className="toque flex cursor-pointer list-none items-center gap-3 p-4 md:p-5 [&::-webkit-details-marker]:hidden">
        <h2 className="flex-1 text-[16px] font-extrabold">
          {titulo}
          {contagem !== undefined && (
            <span className="num ml-2 text-[13px] font-bold text-tinta-3">{contagem}</span>
          )}
        </h2>
        <span
          aria-hidden
          className="shrink-0 text-[18px] font-bold text-tinta-3 transition-transform group-open:rotate-90"
        >
          ›
        </span>
      </summary>
      <div className="px-4 pb-4 md:px-5 md:pb-5">{children}</div>
    </details>
  );
}
