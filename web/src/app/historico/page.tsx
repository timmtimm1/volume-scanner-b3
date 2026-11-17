import { TabelaDoHistorico } from "@/components/TabelaDoHistorico";
import { LIMIAR_DO_ALERTA, Z_MINIMO_DO_SITE } from "@/lib/config";
import { eventosDoHistorico } from "@/lib/db";
import { linhaDoHistorico } from "@/lib/historico";
import { lerTendencias } from "@/lib/tendencias";

export default async function Historico() {
  // A tendencia de todos os papeis com negocio no ultimo pregao, nao so os
  // liquidos: o historico tem evento de papel menor, e o filtro vale para ele.
  const [eventos, tendencias] = await Promise.all([eventosDoHistorico(), lerTendencias(false)]);

  // `linhaDoHistorico` corta o evento ao que a tabela usa e tira a precisao que
  // nenhuma celula mostra. O porque de cada campo esta em `lib/historico.ts`.
  const linhas = eventos.map(linhaDoHistorico);

  return (
    <TabelaDoHistorico
      eventos={linhas}
      limiarDoAlerta={LIMIAR_DO_ALERTA}
      minimo={Z_MINIMO_DO_SITE}
      tendencias={Object.fromEntries(tendencias.linhas.map((l) => [l.ticker, l.inclinacoes]))}
      diaDaTendencia={tendencias.dia}
    />
  );
}
