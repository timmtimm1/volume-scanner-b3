import { TabelaDoHistorico } from "@/components/TabelaDoHistorico";
import { LIMIAR_DO_ALERTA, Z_MINIMO_DO_SITE } from "@/lib/config";
import { eventosDoHistorico } from "@/lib/db";
import type { LinhaDoHistorico } from "@/lib/types";

export default async function Historico() {
  const eventos = await eventosDoHistorico();

  // So os campos que a tabela usa vao para o navegador. O Evento inteiro tem o
  // dobro de campos, e a pagina chegava a 689 KB com 400 eventos.
  const linhas: LinhaDoHistorico[] = eventos.map((e) => ({
    ticker: e.ticker,
    empresa: e.empresa,
    tradeDate: e.tradeDate,
    zLog: e.zLog,
    rvol: e.rvol,
    retDay: e.retDay,
    zExcess: e.zExcess,
    avgTicket: e.avgTicket,
    volumeFinancial: e.volumeFinancial,
  }));

  return (
    <TabelaDoHistorico
      eventos={linhas}
      limiarDoAlerta={LIMIAR_DO_ALERTA}
      minimo={Z_MINIMO_DO_SITE}
    />
  );
}
