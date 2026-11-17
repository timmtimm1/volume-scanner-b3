import { PainelDoScanner } from "@/components/PainelDoScanner";
import { LIMIAR_DO_ALERTA, Z_MINIMO_DO_SITE } from "@/lib/config";
import { barrasRecentes, distribuicaoDoPregao, eventosDoPregao, ultimoPregao } from "@/lib/db";

/**
 * Quantos papeis ganham mini-grafico. Num dia de estresse a lista passa de
 * cem; os de maior desvio ganham desenho, e a pagina nao vira megabytes.
 */
const PAPEIS_COM_GRAFICO = 60;

export default async function Scanner() {
  const pregao = await ultimoPregao();
  const [eventos, distribuicao] = await Promise.all([
    eventosDoPregao(pregao.tradeDate),
    distribuicaoDoPregao(pregao.tradeDate),
  ]);
  const comGrafico = [...eventos]
    .sort((a, b) => b.zLog - a.zLog)
    .slice(0, PAPEIS_COM_GRAFICO)
    .map((e) => e.ticker);
  const barras = await barrasRecentes(comGrafico, pregao.tradeDate, 40);

  return (
    <PainelDoScanner
      pregao={pregao}
      eventos={eventos}
      distribuicao={distribuicao}
      barras={barras}
      limiarDoAlerta={LIMIAR_DO_ALERTA}
      minimo={Z_MINIMO_DO_SITE}
    />
  );
}
