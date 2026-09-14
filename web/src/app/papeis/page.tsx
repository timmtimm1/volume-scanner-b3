import { universo } from "@/lib/db";
import { dinheiro, numero, proporcao, reais } from "@/lib/formato";

/**
 * Quais papéis o scanner acompanha, e por que cada um entrou.
 *
 * Não está entre as três telas da seção 6 do plano. Existe porque a pergunta
 * que ela responde — "isso aqui está de olho em quê?" — é a primeira que se faz
 * ao ver um alerta de um papel desconhecido.
 */
export default async function Papeis() {
  const u = await universo();
  const cortados = u.avaliados - u.papeis.length;

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex min-w-0 flex-col gap-0.5">
            <h1 className="text-[22px] font-extrabold tracking-tight">Papéis acompanhados</h1>
            <p className="num text-[13px] font-semibold text-tinta-3">
              Liquidez medida nos últimos {u.janela} pregões
            </p>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-3 rounded-2xl bg-selecao px-4 py-2.5">
            <span className="num text-[24px] font-extrabold text-acento">{u.papeis.length}</span>
            <span className="text-[12px] font-bold leading-tight text-tinta-2">
              de {u.avaliados}
              <br />
              negociados
            </span>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <p className="rounded-2xl bg-painel-2 px-4 py-3.5 text-[13px] leading-relaxed text-tinta-2">
            Entra no scanner quem negociou uma mediana de pelo menos{" "}
            <strong className="num text-tinta">{dinheiro(u.pisoMediana)}</strong> por pregão{" "}
            <em>e</em> apareceu em pelo menos{" "}
            <strong className="num text-tinta">{proporcao(u.coberturaMinima)}</strong> dos {u.janela}{" "}
            pregões da janela.{" "}
            {cortados > 0 && (
              <>
                <strong className="num text-tinta">{cortados}</strong>{" "}
                {cortados === 1 ? "papel ficou" : "papéis ficaram"} de fora.
              </>
            )}
          </p>
          <p className="rounded-2xl bg-painel-2 px-4 py-3.5 text-[13px] leading-relaxed text-tinta-3">
            O corte de liquidez evita que um papel que negocia três mil reais por dia vire 8σ ao
            negociar quarenta mil. O de presença evita que um papel que apareceu em dois pregões da
            janela, com volume alto, entre por mediana.
          </p>
        </div>
      </section>

      {u.papeis.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-linha-2 p-8 text-center text-[13px] font-semibold text-tinta-3">
          Nenhum papel passou nos cortes. O banco provavelmente ainda não tem {u.janela} pregões
          carregados.
        </div>
      ) : (
        <section className="cartao overflow-hidden p-2 md:p-3">
          <div className="hidden grid-cols-[minmax(0,1fr)_150px_150px_120px] gap-2 px-3 py-2 md:grid">
            <span className="rotulo">Papel</span>
            <span className="rotulo text-right">Mediana diária</span>
            <span className="rotulo text-right">Presença</span>
            <span className="rotulo text-right">Último</span>
          </div>

          <div className="flex flex-col gap-0.5">
            {u.papeis.map((p) => (
              <div
                key={p.ticker}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-xl px-3 py-2.5 hover:bg-painel-2 md:grid-cols-[minmax(0,1fr)_150px_150px_120px] md:gap-2"
              >
                <span className="text-[15px] font-extrabold md:text-[14px]">{p.ticker}</span>
                <span className="num text-right text-[14px] font-bold md:text-[13px]">
                  {dinheiro(p.medianaVolume)}
                </span>
                <span className="col-span-2 flex items-center gap-2 md:col-span-1 md:justify-end">
                  <span className="h-1.5 w-24 overflow-hidden rounded-full bg-selecao md:w-14">
                    <span className="block h-full rounded-full bg-acento" style={{ width: `${p.cobertura * 100}%` }} />
                  </span>
                  <span className="num text-[12px] font-semibold text-tinta-2">{proporcao(p.cobertura)} dos pregões</span>
                  <span className="num ml-auto text-[12px] font-semibold text-tinta-3 md:hidden">
                    {reais(p.ultimoFechamento)}
                  </span>
                </span>
                <span className="num hidden text-right text-[13px] font-semibold md:block">
                  {reais(p.ultimoFechamento)}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      <p className="num px-1 text-[12px] font-semibold text-tinta-3">
        {numero(u.papeis.length, 0)} papéis · a lista muda conforme a liquidez de cada um sobe ou cai
      </p>
    </div>
  );
}
