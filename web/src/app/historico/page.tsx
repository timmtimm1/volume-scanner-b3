import { TabelaDoHistorico } from "@/components/TabelaDoHistorico";
import { eventosDoHistorico, Z_MINIMO_DO_SITE } from "@/lib/db";

const LIMIAR_DO_ALERTA = 6;

export default async function Historico() {
  const eventos = await eventosDoHistorico();
  const notificados = eventos.filter((e) => e.notificado).length;
  const primeiro = eventos.at(-1)?.tradeDate;
  const ultimo = eventos[0]?.tradeDate;

  return (
    <TabelaDoHistorico
      eventos={eventos}
      notificados={notificados}
      de={primeiro}
      ate={ultimo}
      limiarDoAlerta={LIMIAR_DO_ALERTA}
      minimo={Z_MINIMO_DO_SITE}
    />
  );
}
