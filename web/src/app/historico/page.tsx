import { TabelaDoHistorico } from "@/components/TabelaDoHistorico";
import { eventosDoHistorico, Z_MINIMO_DO_SITE } from "@/lib/db";

const LIMIAR_DO_ALERTA = 6;

export default async function Historico() {
  const eventos = await eventosDoHistorico();
  const acimaDoLimiar = eventos.filter((e) => e.zLog >= LIMIAR_DO_ALERTA).length;
  const primeiro = eventos.at(-1)?.tradeDate;
  const ultimo = eventos[0]?.tradeDate;

  return (
    <TabelaDoHistorico
      eventos={eventos}
      acimaDoLimiar={acimaDoLimiar}
      de={primeiro}
      ate={ultimo}
      limiarDoAlerta={LIMIAR_DO_ALERTA}
      minimo={Z_MINIMO_DO_SITE}
    />
  );
}
