import Link from "next/link";
import { redirect } from "next/navigation";
import { ehDono } from "@/auth";
import { Selo } from "@/components/ResumoDoBacktest";
import { escolhasDa, rodadaAtual } from "@/lib/backtest";
import { fmtCusto, fmtIntervalo, fmtR, GRUPOS, SAIDAS } from "@/lib/backtest-tela";
import { semCripto } from "@/lib/cripto";
import { data } from "@/lib/formato";
import { noMercado } from "@/lib/mercado-servidor";
import { categoriaDaChave, NOME_DO_SETUP } from "@/lib/setups-tela";

/**
 * O backtest de cripto: o que cada setup de compra teria feito nas moedas da
 * Binance desde 2017, com custo, contra uma moeda sorteada no mesmo dia.
 *
 * Mesmo protocolo da B3 com outros anos: a saida de cada setup e escolhida
 * usando so 2017-2021 e conferida em 2022-2026. E dessa conferencia que sai a
 * cor do semaforo na aba Cripto.
 */
export const dynamic = "force-dynamic";

const ORDEM = { firme: 0, fraco: 1, falhou: 2 } as const;

function Numero({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="rotulo">{rotulo}</span>
      <span className="num text-[14px] font-bold">{children}</span>
    </div>
  );
}

export default async function BacktestDeCripto() {
  if (!(await ehDono())) redirect("/cripto");

  let lido;
  try {
    lido = await noMercado("cripto", async () => {
      const rodada = await rodadaAtual();
      return rodada ? { rodada, escolhas: await escolhasDa(rodada.id) } : null;
    });
  } catch (erro) {
    if (!semCripto(erro)) throw erro;
    lido = null;
  }

  const cabecalho = (
    <section className="cartao flex flex-col gap-1 p-5">
      <Link href="/cripto" className="text-[12px] font-bold text-tinta-3 hover:text-acento">
        ‹ Cripto
      </Link>
      <h1 className="text-[22px] font-extrabold tracking-tight">Backtest de cripto</h1>
      {lido && (
        <p className="num text-[12px] font-semibold text-tinta-3">
          Dados de {data(lido.rodada.dadosDe)} a {data(lido.rodada.dadosAte)} ·{" "}
          {lido.rodada.trades.toLocaleString("pt-BR")} trades em {lido.rodada.papeis} moedas ·
          custo de {fmtCusto(lido.rodada.custo)} por lado · saída forçada em {lido.rodada.teto} dias
        </p>
      )}
    </section>
  );

  if (!lido) {
    return (
      <div className="flex flex-col gap-4">
        {cabecalho}
        <section className="cartao p-5 text-[14px] leading-relaxed text-tinta-2">
          Ainda não há rodada do backtest de cripto neste banco. Sem ela, o semáforo da aba
          Cripto fica cinza.
        </section>
      </div>
    );
  }

  const escolhas = [...lido.escolhas].sort(
    (a, b) =>
      ORDEM[a.nivel] - ORDEM[b.nivel] || (b.expConferencia ?? -9) - (a.expConferencia ?? -9),
  );
  const contagem = { firme: 0, fraco: 0, falhou: 0 };
  for (const e of escolhas) contagem[e.nivel] += 1;

  return (
    <div className="flex flex-col gap-4">
      {cabecalho}

      <section className="cartao flex flex-col gap-2 p-5 text-[13px] font-semibold leading-relaxed text-tinta-2">
        <p>
          <strong className="font-extrabold text-tinta">
            {contagem.firme} firme{contagem.firme === 1 ? "" : "s"}, {contagem.fraco} fraco
            {contagem.fraco === 1 ? "" : "s"}, {contagem.falhou}{" "}
            {contagem.falhou === 1 ? "falhou" : "falharam"}.
          </strong>{" "}
          São as mesmas regras de compra das ações, sem mudar corte nenhum, aplicadas ao candle
          diário de todas as moedas que a Binance já negociou contra o dólar (USDT), inclusive as
          que saíram de lá.
        </p>
        <p>
          O <strong className="font-extrabold text-tinta">controle</strong> é uma moeda sorteada
          no mesmo dia, comprada na abertura seguinte, com o stop à mesma distância e a mesma
          saída. O setup só vale alguma coisa se ganhar dele. A saída de cada setup foi escolhida
          usando só 2017–2021 e conferida em 2022–2026; a cor do semáforo é essa conferência.
        </p>
        <p>
          R é o múltiplo do risco: +0,30 R quer dizer ganhar, em média, 30% do que se arrisca
          por trade. Setup que falhou continua na lista: saber o que não funciona também é
          resultado.
        </p>
      </section>

      <ul className="flex flex-col gap-3">
        {escolhas.map((e) => {
          const categoria = categoriaDaChave(e.setup);
          return (
            <li key={e.setup} className="cartao flex flex-col gap-3 p-4 md:p-5">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="min-w-0 flex-1 text-[16px] font-extrabold">
                  {categoria ? NOME_DO_SETUP[categoria] : e.setup}
                </h2>
                <Selo nivel={e.nivel} />
              </div>
              {e.saida === null ? (
                <p className="text-[13px] font-semibold text-tinta-3">
                  Nenhuma combinação chegou a 100 trades em 2017–2021, então não houve escolha.
                </p>
              ) : (
                <>
                  <p className="text-[12px] font-semibold text-tinta-3">
                    {SAIDAS[e.saida]}
                    {e.grupo && ` · ${GRUPOS[e.grupo].toLowerCase()}`}
                  </p>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-3 md:grid-cols-5">
                    <Numero rotulo="R por trade, 2022–2026">
                      <span
                        className={(e.expConferencia ?? 0) >= 0 ? "text-alta" : "text-baixa"}
                      >
                        {fmtR(e.expConferencia)}
                      </span>
                    </Numero>
                    <Numero rotulo="Intervalo de 95%">
                      {fmtIntervalo(e.icConfBaixo, e.icConfAlto)}
                    </Numero>
                    <Numero rotulo="Contra o controle">
                      <span
                        className={(e.difConferencia ?? 0) >= 0 ? "text-alta" : "text-baixa"}
                      >
                        {fmtR(e.difConferencia)}
                      </span>
                    </Numero>
                    <Numero rotulo="Trades, 2022–2026">
                      {e.nConferencia === null ? "—" : e.nConferencia.toLocaleString("pt-BR")}
                    </Numero>
                    <Numero rotulo="2017–2021">{fmtR(e.expEscolha)}</Numero>
                  </div>
                </>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
