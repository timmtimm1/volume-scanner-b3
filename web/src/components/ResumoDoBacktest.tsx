import Link from "next/link";
import {
  type Escolha,
  fmtIntervalo,
  fmtR,
  GRUPOS,
  linkDaSelecao,
  NIVEIS,
  type Nivel,
  ORDEM_DOS_SETUPS,
  SAIDAS,
  type Selecao,
  SETUPS,
} from "@/lib/backtest-tela";

type Props = { escolhas: Escolha[]; selecao: Selecao };

const COLUNAS =
  "md:grid-cols-[minmax(0,1fr)_88px_minmax(0,1.5fr)_minmax(0,1.3fr)_minmax(0,1fr)_64px_minmax(0,0.9fr)]";

/** Verde so para "firme": e o unico nivel que pode ser lido como bom. */
const COR_DO_NIVEL: Record<Nivel, string> = {
  firme: "bg-alta-fundo text-alta",
  fraco: "bg-evento-fundo text-evento-tinta",
  falhou: "bg-painel text-tinta-2 border border-linha-2",
};

function Selo({ nivel }: { nivel: Nivel }) {
  return (
    <span
      title={NIVEIS[nivel].explicacao}
      className={`inline-flex h-7 items-center rounded-full px-3 text-[12px] font-extrabold ${COR_DO_NIVEL[nivel]}`}
    >
      {NIVEIS[nivel].nome}
    </span>
  );
}

function Valor({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="rotulo md:hidden">{rotulo}</span>
      {children}
    </div>
  );
}

/**
 * O resumo: um paragrafo que explica como ler, e uma linha por setup, sempre na
 * mesma ordem (nunca pelo resultado). Cada linha leva ao detalhe da combinacao
 * que foi escolhida em 1995-2015.
 */
export function ResumoDoBacktest({ escolhas, selecao }: Props) {
  return (
    <section className="cartao flex flex-col gap-4 p-4 md:p-5">
      <div className="flex flex-col gap-2">
        <h2 className="text-[18px] font-extrabold">Resumo</h2>
        <div className="flex max-w-[75ch] flex-col gap-2 text-[14px] leading-relaxed text-tinta-2">
          <p>
            <strong className="font-extrabold text-tinta">R</strong> é quanto você arriscou no
            trade (a entrada menos o stop). Ganhar 1 R é ganhar o mesmo tanto que se arriscou.{" "}
            <strong className="font-extrabold text-tinta">R por trade</strong> é a média do que
            cada trade rendeu, já descontado o custo.
          </p>
          <p>
            O <strong className="font-extrabold text-tinta">controle</strong> é um papel sorteado
            no mesmo dia e comprado do mesmo jeito. Se o setup não ganha dele, o ganho era só o
            mercado subindo.
          </p>
          <p>
            A combinação de saída e tendência de cada setup foi escolhida usando só 1995–2015 e
            depois conferida em 2016–2026. Setup que falhou continua na lista: saber o que não
            funciona também vale.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2 md:gap-0.5">
        <div className={`hidden gap-3 px-3 md:grid ${COLUNAS}`}>
          <span className="rotulo">Setup</span>
          <span className="rotulo">Nível</span>
          <span className="rotulo">Combinação escolhida</span>
          <span className="rotulo">R por trade, 2016–2026</span>
          <span className="rotulo">Contra o controle</span>
          <span className="rotulo text-right">Trades</span>
          <span className="rotulo text-right">1995–2015</span>
        </div>
        <ul className="flex flex-col gap-2 md:gap-0.5">
          {ORDEM_DOS_SETUPS.map((id) => {
            const e = escolhas.find((x) => x.setup === id);
            const ativo = id === selecao.setup;
            const link = linkDaSelecao({
              setup: id,
              saida: e?.saida ?? "mme9",
              grupo: e?.grupo ?? "todos",
            });
            return (
              <li key={id}>
                <Link
                  href={`${link}#detalhe`}
                  aria-current={ativo ? "true" : undefined}
                  className={`toque grid grid-cols-2 items-start gap-x-3 gap-y-2.5 rounded-2xl border p-3.5 transition-colors md:items-center md:gap-3 md:rounded-xl md:px-3 md:py-2.5 ${COLUNAS} ${
                    ativo
                      ? "border-acento bg-selecao"
                      : "border-transparent bg-painel-2 hover:border-linha-2"
                  }`}
                >
                  <span className="flex items-center gap-2 text-[16px] font-extrabold md:text-[15px]">
                    {SETUPS[id].nome}
                  </span>
                  <span className="flex justify-end md:justify-start">
                    {e ? <Selo nivel={e.nivel} /> : <span className="text-tinta-3">—</span>}
                  </span>
                  {e === undefined ? (
                    <span className="col-span-2 text-[13px] font-semibold text-tinta-3 md:col-span-5">
                      Sem resultado nesta rodada.
                    </span>
                  ) : e.saida === null || e.grupo === null ? (
                    <span className="col-span-2 text-[13px] font-semibold text-tinta-3 md:col-span-5">
                      Nenhuma combinação chegou a 100 trades em 1995–2015, então não houve escolha.
                    </span>
                  ) : (
                    <>
                      <div className="col-span-2 md:col-span-1">
                        <Valor rotulo="Combinação escolhida">
                          <span className="text-[13px] font-bold text-tinta-2">
                            {SAIDAS[e.saida]} · {GRUPOS[e.grupo]}
                          </span>
                        </Valor>
                      </div>
                      <Valor rotulo="R por trade, 2016–2026">
                        <span className="num text-[14px] font-extrabold">
                          {fmtR(e.expConferencia)}
                        </span>
                        <span className="num text-[12px] font-semibold text-tinta-3">
                          {fmtIntervalo(e.icConfBaixo, e.icConfAlto)}
                        </span>
                      </Valor>
                      <Valor rotulo="Contra o controle">
                        <span className="num text-[14px] font-extrabold">
                          {fmtR(e.difConferencia)}
                        </span>
                      </Valor>
                      <Valor rotulo="Trades, 2016–2026">
                        <span className="num text-[13px] font-bold md:text-right">
                          {e.nConferencia ?? "—"}
                        </span>
                      </Valor>
                      <Valor rotulo="1995–2015">
                        <span className="num text-[12px] font-semibold text-tinta-3 md:text-right">
                          {fmtR(e.expEscolha)}
                          <span className="block">
                            {e.nEscolha === null ? "" : `${e.nEscolha} trades`}
                          </span>
                        </span>
                      </Valor>
                    </>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
        <ul className="mt-2 flex flex-col gap-1.5 px-1">
          {(Object.keys(NIVEIS) as Nivel[]).map((n) => (
            <li key={n} className="flex items-start gap-2.5">
              <Selo nivel={n} />
              <span className="min-w-0 flex-1 pt-0.5 text-[12px] font-semibold text-tinta-3">
                {NIVEIS[n].explicacao}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
