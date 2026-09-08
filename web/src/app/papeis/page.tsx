import { universo } from "@/lib/db";
import { dinheiro, numero, proporcao, reais } from "@/lib/formato";

/**
 * Quais papéis o scanner acompanha, e por que cada um entrou.
 *
 * Não está entre as três telas da seção 6 do plano. Existe porque a barra de
 * navegação já a anunciava desde o desenho, e porque a pergunta que ela responde
 * — "isso aqui está de olho em quê?" — é a primeira que se faz ao ver um alerta
 * de um papel desconhecido.
 */
export default async function Papeis() {
  const u = await universo();
  const cortados = u.avaliados - u.papeis.length;

  return (
    <>
      <header className="border-b border-linha bg-painel px-4 py-3.5 md:px-6">
        <div className="flex flex-wrap items-center gap-4">
          <div>
            <h1 className="text-[17px] font-bold">Papéis acompanhados</h1>
            <p className="num mt-0.5 text-[11px] text-tinta-3">
              Liquidez medida nos últimos {u.janela} pregões
            </p>
          </div>
          <div className="flex-1" />
          <div className="flex items-baseline gap-2">
            <span className="num text-[22px] font-semibold text-ambar">
              {u.papeis.length}
            </span>
            <span className="text-[11px] leading-tight text-tinta-2">
              de {u.avaliados}
              <br />
              negociados
            </span>
          </div>
        </div>
      </header>

      <div className="border-b border-linha bg-painel-2 px-4 py-3 md:px-6">
        <p className="text-[11px] leading-relaxed text-tinta-2">
          Entra no scanner quem negociou uma mediana de pelo menos{" "}
          <strong className="num text-tinta">{dinheiro(u.pisoMediana)}</strong> por
          pregão <em>e</em> apareceu em pelo menos{" "}
          <strong className="num text-tinta">{proporcao(u.coberturaMinima)}</strong> dos{" "}
          {u.janela} pregões da janela.{" "}
          {cortados > 0 && (
            <>
              <strong className="num text-tinta">{cortados}</strong>{" "}
              {cortados === 1 ? "papel ficou" : "papéis ficaram"} de fora.
            </>
          )}
        </p>
        <p className="mt-1.5 text-[11px] leading-relaxed text-tinta-3">
          O corte de liquidez evita que um papel que negocia três mil reais por dia
          vire 8σ ao negociar quarenta mil. O de presença evita que um papel que
          apareceu em dois pregões da janela, com volume alto, entre por mediana.
        </p>
      </div>

      <div className="p-4 md:p-6">
        {u.papeis.length === 0 ? (
          <div className="rounded-md border border-dashed border-linha-2 p-8 text-center text-[13px] text-tinta-3">
            Nenhum papel passou nos cortes. O banco provavelmente ainda não tem{" "}
            {u.janela} pregões carregados.
          </div>
        ) : (
          <div className="overflow-hidden rounded-md border border-linha bg-painel">
            <div className="hidden grid-cols-[minmax(0,1fr)_140px_120px_110px] border-b border-linha bg-painel-2 px-3.5 py-2 md:grid">
              <span className="rotulo">Papel</span>
              <span className="rotulo text-right">Mediana diária</span>
              <span className="rotulo text-right">Presença</span>
              <span className="rotulo text-right">Último</span>
            </div>

            {u.papeis.map((p) => (
              <div
                key={p.ticker}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-linha px-3.5 py-2.5 last:border-b-0 md:grid md:grid-cols-[minmax(0,1fr)_140px_120px_110px] md:gap-0 md:py-2"
              >
                <span className="text-[14px] font-semibold md:text-[13px]">
                  {p.ticker}
                </span>
                <span className="num ml-auto text-right text-[13px] md:ml-0 md:text-[12px]">
                  {dinheiro(p.medianaVolume)}
                </span>
                <span className="flex items-center justify-end gap-2">
                  <span className="hidden h-1 w-10 overflow-hidden rounded-sm bg-linha-2 md:block">
                    <span
                      className="block h-full bg-tinta-2"
                      style={{ width: `${p.cobertura * 100}%` }}
                    />
                  </span>
                  <span className="num text-[11px] text-tinta-2 md:w-9 md:text-right md:text-[12px]">
                    {proporcao(p.cobertura)}
                  </span>
                </span>
                <span className="num text-right text-[12px] text-tinta-2 md:text-[13px] md:text-tinta">
                  {reais(p.ultimoFechamento)}
                </span>
              </div>
            ))}
          </div>
        )}

        <p className="num mt-3 text-[11px] text-tinta-3">
          {numero(u.papeis.length, 0)} papéis · a lista muda conforme a liquidez de
          cada um sobe ou cai
        </p>
      </div>
    </>
  );
}
