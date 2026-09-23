import { TabelaDoHistorico } from "@/components/TabelaDoHistorico";
import { LIMIAR_DO_ALERTA, Z_MINIMO_DO_SITE } from "@/lib/config";
import { eventosDoHistorico } from "@/lib/db";
import { linhaDoHistorico } from "@/lib/historico";

export default async function Historico() {
  const eventos = await eventosDoHistorico();

  // `linhaDoHistorico` corta o evento ao que a tabela usa e tira a precisao que
  // nenhuma celula mostra. O porque de cada campo esta em `lib/historico.ts`.
  const linhas = eventos.map(linhaDoHistorico);

  return (
    <TabelaDoHistorico
      eventos={linhas}
      limiarDoAlerta={LIMIAR_DO_ALERTA}
      minimo={Z_MINIMO_DO_SITE}
    />
  );
}
