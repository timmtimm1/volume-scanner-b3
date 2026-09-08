import { ListaDeEventos } from "@/components/ListaDeEventos";
import { eventosDoPregao, ultimoPregao, Z_MINIMO_DO_SITE } from "@/lib/db";
import { data, diaDaSemana, numero } from "@/lib/formato";

/** Espelha `alert.threshold` do config.yaml. */
const LIMIAR_DO_ALERTA = 6;

export default async function Scanner() {
  const pregao = await ultimoPregao();
  const eventos = await eventosDoPregao(pregao.tradeDate);
  const mercadoCalmo = (pregao.mktVolZ ?? 0) < 2;

  return (
    <>
      <header className="border-b border-linha bg-painel px-4 py-3.5 md:px-6">
        <h1 className="text-[17px] font-bold">Scanner do dia</h1>
        <p className="num mt-0.5 text-[11px] text-tinta-3">
          Pregão de {data(pregao.tradeDate)} · {diaDaSemana(pregao.tradeDate)}
        </p>
      </header>

      <div className="flex flex-col gap-2 border-b border-linha bg-painel-2 px-4 py-3 md:flex-row md:items-center md:px-6">
        <div className="flex items-baseline gap-2">
          <span className="rotulo">Volume do mercado</span>
          <span className="num text-[14px] font-semibold">
            z {numero(pregao.mktVolZ)}
          </span>
          <span className="text-[11px] text-tinta-3">
            {mercadoCalmo
              ? "dia normal — o que aparece abaixo é dos papéis"
              : "mercado inteiro girando mais; leia o z líquido antes"}
          </span>
        </div>
        <div className="flex-1" />
        <div className="flex gap-6">
          <div className="md:text-right">
            <div className="rotulo">Avaliados</div>
            <div className="num text-[14px]">{pregao.avaliados}</div>
          </div>
          <div className="md:text-right">
            <div className="rotulo">Notificados</div>
            <div className="num text-[14px] text-ambar">{pregao.notificados}</div>
          </div>
        </div>
      </div>

      <ListaDeEventos
        eventos={eventos}
        limiarDoAlerta={LIMIAR_DO_ALERTA}
        minimo={Z_MINIMO_DO_SITE}
      />
    </>
  );
}
