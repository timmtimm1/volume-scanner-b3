import { nomeDaEmpresa, numero, reais } from "@/lib/formato";
import { detalheDoAjuste, soQuemCaiu, soQuemSubiu } from "@/lib/semana";
import type { AcaoDaSemana, AcoesDaSemana } from "@/lib/types";
import { Bloco, LinkDoPapel, Nota, Rotulo, Variacao } from "./SemanaPecas";

function LinhaDaAcao({
  posicao,
  acao,
  nome,
}: {
  posicao: number;
  acao: AcaoDaSemana;
  nome: string | undefined;
}) {
  const detalhe = detalheDoAjuste(acao);
  const empresa = nomeDaEmpresa(nome);
  return (
    <li className="grid grid-cols-[18px_minmax(0,1fr)_auto] items-baseline gap-x-2 gap-y-0.5 border-b border-linha py-2.5 last:border-b-0">
      <span className="num text-[11px] font-semibold text-tinta-3">{posicao}</span>
      <span className="flex min-w-0 items-baseline gap-2">
        <LinkDoPapel ticker={acao.ticker} className="text-[15px]" />
        {empresa && <span className="truncate text-[12px] text-tinta-3">{empresa}</span>}
      </span>
      <Variacao valor={acao.variacao} className="text-[15px]" />
      <span className="num col-span-2 col-start-2 text-[12px] font-semibold text-tinta-3">
        {reais(acao.preco_inicio)} → {reais(acao.preco_fim)}
      </span>
      {(detalhe || !acao.conferido) && (
        <>
          <span className="col-span-2 col-start-2 flex flex-wrap items-center gap-x-2 gap-y-1">
            {detalhe && (
              <>
                <span
                  title={detalhe}
                  className="rounded-full bg-selecao px-2 py-px text-[10px] font-bold text-tinta-2"
                >
                  ajustada
                </span>
                <span className="num text-[11px] text-tinta-3">{detalhe}</span>
              </>
            )}
            {!acao.conferido && (
              <span
                title="A B3 não respondeu para este emissor: pode haver evento que não foi descontado."
                className="rounded-full bg-evento-fundo px-2 py-px text-[10px] font-bold text-evento-tinta"
              >
                proventos não conferidos
              </span>
            )}
          </span>
        </>
      )}
    </li>
  );
}

function Lista({
  titulo,
  acoes,
  nomes,
  vazio,
}: {
  titulo: string;
  acoes: AcaoDaSemana[];
  nomes: Record<string, string>;
  vazio: string;
}) {
  return (
    <div className="flex min-w-0 flex-col">
      <Rotulo>{titulo}</Rotulo>
      {acoes.length === 0 ? (
        <p className="py-3 text-[13px] text-tinta-3">{vazio}</p>
      ) : (
        <ul>
          {acoes.map((a, i) => (
            <LinhaDaAcao key={a.ticker} posicao={i + 1} acao={a} nome={nomes[a.ticker]} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function SemanaAcoes({
  acoes,
  nomes,
}: {
  acoes: AcoesDaSemana;
  nomes: Record<string, string>;
}) {
  return (
    <Bloco titulo="Ações" subtitulo="Variação na semana, do fechamento da base ao da sexta">
      <div className="grid gap-x-8 gap-y-5 md:grid-cols-2">
        <Lista
          titulo="Maiores altas"
          acoes={soQuemSubiu(acoes.altas, (a) => a.variacao)}
          nomes={nomes}
          vazio="Nenhum papel subiu na semana."
        />
        <Lista
          titulo="Maiores quedas"
          acoes={soQuemCaiu(acoes.quedas, (a) => a.variacao)}
          nomes={nomes}
          vazio="Nenhum papel caiu na semana."
        />
      </div>

      {acoes.fora_do_ranking.length > 0 && (
        <div className="flex flex-col gap-1.5 rounded-2xl bg-painel-2 px-4 py-3">
          <Rotulo>Fora do ranking</Rotulo>
          <ul className="flex flex-col gap-1">
            {acoes.fora_do_ranking.map((a) => (
              <li key={a.ticker} className="text-[12px] leading-relaxed text-tinta-2">
                <LinkDoPapel ticker={a.ticker} /> · variação bruta{" "}
                <Variacao valor={a.variacao_bruta} /> · {a.eventos_sem_ajuste ?? "evento sem razão por ação"}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Nota>
        <span className="num">{numero(acoes.avaliados, 0)}</span> papéis avaliados; variação ajustada por
        proventos e desdobramentos.
        {acoes.falhas_b3.length > 0 && (
          <>
            {" "}
            A B3 não respondeu para {acoes.falhas_b3.length}{" "}
            {acoes.falhas_b3.length === 1 ? "emissor" : "emissores"}.
          </>
        )}
      </Nota>
    </Bloco>
  );
}
