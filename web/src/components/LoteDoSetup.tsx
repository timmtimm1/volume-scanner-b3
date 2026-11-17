import { numero, proporcao } from "@/lib/formato";
import { loteNoMercado, type Perfil } from "@/lib/lote";
import { quantidade, textos, valor, type Mercado } from "@/lib/mercado";

type Props = {
  perfil: Perfil | null;
  entrada: number | null;
  stop: number | null;
  /** Ausente = B3. */
  mercado?: Mercado;
  /** A moeda, para "0,0153 BTC" (na B3 a unidade e "ações"). */
  ticker?: string;
};

/**
 * A linha do lote: "Compre 100 ações · perda máxima R$ 100,00 (1,00% do
 * capital) · posição R$ 2.000,00". Sem capital salvo, o convite para definir.
 * Em cripto: "Compre 0,0153 BTC", em dólar.
 *
 * E uma conta de tamanho de posicao a partir do stop, nao uma indicacao: o
 * texto diz quanto da para comprar e quanto se perde no stop, e para ai.
 */
export function LoteDoSetup({ perfil, entrada, stop, mercado = "b3", ticker = "" }: Props) {
  if (perfil === null) {
    return (
      <p className="text-[12px] font-semibold text-tinta-3">
        <a href="#perfil" className="font-bold text-acento hover:underline">
          Defina seu capital
        </a>{" "}
        para ver o lote.
      </p>
    );
  }

  const lote = loteNoMercado(mercado, { ...perfil, entrada, stop });
  const dadosOk = entrada !== null && stop !== null && entrada > 0 && stop > 0;

  if (!dadosOk) return null;
  if (!(entrada > stop)) {
    return (
      <p className="text-[12px] font-semibold text-tinta-3">
        Sem lote: o stop precisa estar abaixo do preço de entrada.
      </p>
    );
  }
  if (lote.quantidade === 0) {
    const risco = `${numero(perfil.riscoPct, Number.isInteger(perfil.riscoPct) ? 0 : 2)}%`;
    return (
      <p className="text-[12px] font-semibold text-tinta-3">
        Sem lote: com {risco} de risco sobre o seu capital, {textos(mercado).semLote}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-0.5">
      <p className="num text-[13px] font-bold">
        Compre {quantidade(mercado, lote.quantidade, ticker)}
        <span className="font-semibold text-tinta-2">
          {" "}
          · perda máxima {valor(mercado, lote.perdaMaxima)} ({proporcao(lote.pctDoCapital, 2)} do
          capital) · posição {valor(mercado, lote.valorPosicao)}
        </span>
      </p>
      {lote.limitadoPeloCapital && (
        <p className="text-[12px] font-semibold text-tinta-3">
          O capital limitou o lote: o risco permitia mais do que você consegue comprar.
        </p>
      )}
    </div>
  );
}
