import { numero, proporcao, reais } from "@/lib/formato";
import { calcularLote, type Perfil } from "@/lib/lote";

type Props = {
  perfil: Perfil | null;
  entrada: number | null;
  stop: number | null;
};

/**
 * A linha do lote: "Compre 100 ações · perda máxima R$ 100,00 (1,00% do
 * capital) · posição R$ 2.000,00". Sem capital salvo, o convite para definir.
 *
 * E uma conta de tamanho de posicao a partir do stop, nao uma indicacao: o
 * texto diz quanto da para comprar e quanto se perde no stop, e para ai.
 */
export function LoteDoSetup({ perfil, entrada, stop }: Props) {
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

  const lote = calcularLote({ ...perfil, entrada, stop });
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
    return (
      <p className="text-[12px] font-semibold text-tinta-3">
        Sem lote: com {numero(perfil.riscoPct, Number.isInteger(perfil.riscoPct) ? 0 : 2)}% de risco
        sobre o seu capital, não dá nem para 1 ação a esse preço e esse stop.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-0.5">
      <p className="num text-[13px] font-bold">
        Compre {numero(lote.quantidade, 0)} {lote.quantidade === 1 ? "ação" : "ações"}
        <span className="font-semibold text-tinta-2">
          {" "}
          · perda máxima {reais(lote.perdaMaxima)} ({proporcao(lote.pctDoCapital, 2)} do capital)
          · posição {reais(lote.valorPosicao)}
        </span>
      </p>
      {lote.limitadoPeloCapital && (
        <p className="text-[12px] font-semibold text-tinta-3">
          O capital limitou o lote: o risco permitia mais ações do que você consegue comprar.
        </p>
      )}
    </div>
  );
}
