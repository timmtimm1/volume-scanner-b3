"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { AnelDoDesvio } from "@/components/AnelDoDesvio";
import { Grafico } from "@/components/Grafico";
import { PainelDeFundamentos } from "@/components/PainelDeFundamentos";
import type { Direcao } from "@/lib/alertas";
import { PainelDeAlerta } from "@/components/PainelDeAlerta";
import { PainelDeTrade } from "@/components/PainelDeTrade";
import { candleParcial, diaNaB3, horaNaB3 } from "@/lib/candle-de-hoje";
import { LIMIAR_DO_ALERTA } from "@/lib/config";
import {
  data as fmtData,
  dinheiro,
  leituraDaFaixa,
  leituraDoTicket,
  multiplo,
  numero,
  percentual,
  proporcao,
  reais,
} from "@/lib/formato";
import { marcarAgora } from "@/lib/posicao";
import type { Barra, Evento, Fundamentos } from "@/lib/types";
import { useAlertasDoPapel } from "@/lib/useAlertasDoPapel";
import { useCandleDeHoje } from "@/lib/useCandleDeHoje";
import { useTradesDoPapel } from "@/lib/useTradesDoPapel";

type Props = {
  ticker: string;
  barras: Barra[];
  eventos: Evento[];
  /** Nulo em papel sem empresa ligada -- um ETF, ou um codigo que saiu da bolsa. */
  fundamentos: Fundamentos | null;
};

/** Onde a barra de cada janela fecha: 8σ ocupa a largura toda. */
const TETO_DAS_JANELAS = 8;

function ChipDeVariacao({ valor, grande = false }: { valor: number | null; grande?: boolean }) {
  if (valor === null) return null;
  const alta = valor >= 0;
  return (
    <span
      className={`num inline-flex items-center rounded-full font-bold ${
        grande ? "h-7 px-2.5 text-[13px]" : "h-6 px-2 text-[12px]"
      } ${alta ? "bg-alta-fundo text-alta" : "bg-baixa-fundo text-baixa"}`}
    >
      {percentual(valor)}
    </span>
  );
}

/** Um marcador sobre um trilho de 0 a 100%: onde o valor caiu dentro da faixa. */
function Trilho({ fracao }: { fracao: number | null }) {
  if (fracao === null || !Number.isFinite(fracao)) return null;
  const pos = Math.min(Math.max(fracao, 0), 1) * 100;
  return (
    <span className="relative hidden h-1.5 w-[72px] rounded-full bg-selecao sm:block">
      <span
        className="absolute -top-[3px] h-3 w-3 rounded-full border-[3px] border-acento bg-painel"
        style={{ left: `calc(${pos}% - 6px)` }}
      />
    </span>
  );
}

function LinhaDeContexto({
  rotulo,
  valor,
  cor = "text-tinta",
  fracao,
}: {
  rotulo: string;
  valor: string;
  cor?: string;
  fracao?: number | null;
}) {
  return (
    <div className="flex min-h-[42px] items-center gap-3 border-b border-linha">
      <span className="flex-1 text-[13px] font-semibold text-tinta-2">{rotulo}</span>
      {fracao !== undefined && <Trilho fracao={fracao} />}
      <span className={`num min-w-[56px] text-right text-[14px] font-extrabold ${cor}`}>{valor}</span>
    </div>
  );
}

function Quadro({ rotulo, valor, nota }: { rotulo: string; valor: string; nota?: string | null }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-2xl bg-painel-2 p-3">
      <span className="truncate text-[12px] font-bold text-tinta-3">{rotulo}</span>
      <span className="num truncate text-[19px] font-extrabold tracking-tight">{valor}</span>
      {nota && <span className="num truncate text-[11px] font-semibold text-tinta-3">{nota}</span>}
    </div>
  );
}

const corDaDirecao = (v: number | null) => ((v ?? 0) >= 0 ? "text-alta" : "text-baixa");

export function FichaDoPapel({ ticker, barras, eventos, fundamentos }: Props) {
  const params = useSearchParams();
  const pedido = params.get("data");
  const hoje = useCandleDeHoje(ticker);
  const parcial = useMemo(() => candleParcial(barras, hoje), [barras, hoje]);
  const ultimoOficial = barras.at(-1)?.close ?? null;

  const evento = useMemo(() => {
    if (pedido) {
      const achado = eventos.find((e) => e.tradeDate === pedido);
      if (achado) return achado;
    }
    return eventos[0] ?? null;
  }, [eventos, pedido]);

  // O alerta sai no Telegram antes de o site ser reconstruido: por alguns
  // minutos o link aponta para um pregao que esta pagina ainda nao tem. Sem
  // este aviso, a ficha mostrava o evento anterior como se fosse o pedido.
  const pedidoAusente =
    pedido !== null && /^\d{4}-\d{2}-\d{2}$/.test(pedido) && evento?.tradeDate !== pedido;

  const barra = useMemo(
    () => barras.find((b) => b.tradeDate === evento?.tradeDate) ?? null,
    [barras, evento],
  );

  const estadoDosAlertas = useAlertasDoPapel(ticker, barras, evento?.tradeDate, hoje);
  const estadoDosTrades = useTradesDoPapel(ticker, estadoDosAlertas.autenticado);

  // Compras e vendas de TODOS os trades do papel (nao so o aberto) viram
  // marcador no grafico; o PM tracejado e so do trade aberto, se houver.
  const operacoesDeTrade = useMemo(
    () =>
      estadoDosTrades.trades.flatMap((t) =>
        t.operacoes.map((o) => ({ data: o.data, tipo: o.tipo, quantidade: o.quantidade })),
      ),
    [estadoDosTrades.trades],
  );
  // "Agora" para a regua: o close de hoje, mas so quando "hoje" e mesmo o dia
  // corrente em Sao Paulo -- fora do pregao (fim de semana, feriado) a ultima
  // cotacao buscada pode ser de um dia que ja esta em `barras` com dado oficial,
  // e ele e quem vale.
  const agoraDaRegua =
    hoje && hoje.dia === diaNaB3(new Date()) ? hoje.close : (barras.at(-1)?.close ?? null);
  const tradeParaRegua = estadoDosTrades.tradeAberto
    ? {
        quantidade: estadoDosTrades.tradeAberto.quantidade,
        precoMedio: estadoDosTrades.tradeAberto.precoMedio,
        custoComprado: estadoDosTrades.tradeAberto.custoComprado,
        realizado: estadoDosTrades.tradeAberto.realizado,
      }
    : null;
  const regua =
    agoraDaRegua !== null
      ? {
          agora: agoraDaRegua,
          trade: tradeParaRegua,
          podeCriarAlerta: estadoDosAlertas.autenticado === true,
          criarAlerta: async (preco: number, direcao: Direcao) => {
            await estadoDosAlertas.criarAlertaEm(preco, direcao);
          },
        }
      : undefined;

  // O resultado do trade aberto marcado ao preco de agora (mesmo "agora" da
  // regua, ja calculado acima), para a linha tracejada do preco medio no
  // grafico -- estilo Profit, ela mostra se o trade esta ganhando ou perdendo.
  // Sem trade aberto ou sem "agora" disponivel, sem linha.
  const posicaoDoGrafico = useMemo(() => {
    const aberto = estadoDosTrades.tradeAberto;
    if (!aberto || agoraDaRegua === null) return null;
    const marcado = marcarAgora(aberto, agoraDaRegua);
    return {
      quantidade: aberto.quantidade,
      precoMedio: aberto.precoMedio,
      resultado: marcado.resultado,
      resultadoPct: marcado.resultadoPct,
    };
  }, [estadoDosTrades.tradeAberto, agoraDaRegua]);

  // Qual aba do cartao de contexto esta aberta. Comeca sempre em "evento":
  // quem chega pelo alerta do Telegram quer ver por que o papel apareceu, e
  // nao o balanco -- os fundamentos estao a um toque.
  const [aba, setAba] = useState<"evento" | "fundamentos">("evento");

  // As datas em que a empresa publicou balanco, para marcar no grafico. Sem
  // elas nao da para ver se o volume anomalo veio logo depois do resultado.
  const publicacoes = useMemo(
    () =>
      (fundamentos?.trimestres ?? [])
        .filter((t) => t.publicadoEm !== null)
        .map((t) => ({ data: t.publicadoEm as string, rotulo: t.rotulo })),
    [fundamentos],
  );

  // O pregao que os multiplos usam. Sem evento -- papel que tem ficha mas nunca
  // cruzou o limiar, que `dynamicParams` deixa existir -- vale o ultimo pregao
  // que a pagina tem.
  const dataDosFundamentos = evento?.tradeDate ?? barras.at(-1)?.tradeDate ?? null;

  // Montado aqui, e nao no JSX, para a checagem de nulo valer para o TypeScript
  // nos tres lugares que perguntam se ha fundamentos. Criar o elemento nao
  // executa o componente: ele so roda se entrar na arvore.
  const painelDeFundamentos =
    fundamentos !== null && dataDosFundamentos !== null ? (
      <PainelDeFundamentos dados={fundamentos} barras={barras} data={dataDosFundamentos} />
    ) : null;

  // Papel sem evento nao tem o que mostrar na aba Evento: a ficha abre direto
  // nos fundamentos, e sem as abas.
  const verFundamentos =
    painelDeFundamentos !== null && (evento === null || aba === "fundamentos");
  const comAbas = evento !== null && painelDeFundamentos !== null;

  const faixa = leituraDaFaixa(evento?.pos252 ?? null);
  const ticket = leituraDoTicket(
    evento?.avgTicket ?? null,
    evento?.ticketZ ?? null,
    evento?.tradesCount ?? null,
  );
  const janelas = Object.keys(evento?.zByWindow ?? {})
    .map(Number)
    .sort((a, b) => a - b);
  const mercadoCalmo = (evento?.mktVolZ ?? 0) < 2;

  return (
    <div className="flex flex-col gap-4">
      {pedidoAusente && pedido && (
        <p className="rounded-2xl bg-evento-fundo px-4 py-3 text-[13px] font-semibold leading-relaxed text-evento-tinta">
          O pregão de <strong className="num">{fmtData(pedido)}</strong> ainda não chegou a
          esta página. O site é atualizado alguns minutos depois do alerta; recarregue daqui
          a pouco.
          {evento && <> Abaixo, o evento mais recente disponível ({fmtData(evento.tradeDate)}).</>}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)_360px] lg:grid-rows-[auto_1fr]">
        {/* Identidade: papel, pregao e preco */}
        <section className="cartao flex flex-col gap-3.5 p-5 lg:col-start-1 lg:row-start-1">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              aria-label="Voltar ao scanner"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-linha text-tinta-2 transition-colors hover:text-acento lg:hidden"
            >
              <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden>
                <path d="M12 4l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
            <span className="hidden h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-selecao text-[15px] font-extrabold text-acento lg:flex">
              {ticker.slice(0, 2)}
            </span>
            <div className="min-w-0 flex-1">
              <h1 className="text-[26px] font-extrabold leading-none tracking-tight">{ticker}</h1>
              <p className="num mt-1 text-[13px] font-semibold text-tinta-3">
                {evento ? `Pregão de ${fmtData(evento.tradeDate)}` : "sem evento no período"}
              </p>
            </div>
            {evento && (
              <span className="lg:hidden">
                <AnelDoDesvio z={evento.zLog} tamanho={56} espessura={5} fonte={14} />
              </span>
            )}
          </div>

          {barra && (
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="num text-[30px] font-extrabold tracking-tight">{reais(barra.close)}</span>
              <ChipDeVariacao valor={evento?.retDay ?? null} grande />
              {evento?.notificado && (
                <span className="rounded-full bg-evento-fundo px-2.5 py-1 text-[11px] font-bold text-evento-tinta">
                  notificado no Telegram
                </span>
              )}
            </div>
          )}

          {parcial && (
            <div className="flex items-center gap-2.5 rounded-xl bg-painel-2 px-3 py-2.5">
              <span className="relative h-2.5 w-2.5 shrink-0">
                <span className="pulso absolute -inset-1.5 rounded-full bg-acento" />
                <span className="absolute inset-0 rounded-full bg-acento" />
              </span>
              <span className="num whitespace-nowrap text-[12px] font-bold text-tinta-3">
                Hoje · {horaNaB3(parcial.hora)}
              </span>
              <span className="num flex-1 whitespace-nowrap text-right text-[15px] font-extrabold">
                {reais(parcial.close)}
              </span>
              {ultimoOficial !== null && (
                <span className={`num text-[13px] font-extrabold ${corDaDirecao(parcial.close / ultimoOficial - 1)}`}>
                  {percentual(parcial.close / ultimoOficial - 1)}
                </span>
              )}
            </div>
          )}
        </section>

        {/* Grafico */}
        <section className="cartao flex min-w-0 flex-col gap-4 p-4 md:p-5 lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <div className="flex flex-col gap-0.5">
            <h2 className="text-[18px] font-extrabold">Gráfico diário</h2>
            <p className="text-[13px] font-semibold text-tinta-3">
              {barras.length} pregões{parcial ? " e a cotação de hoje" : ""} · candle do evento em dourado
            </p>
          </div>

          <Grafico
            barras={barras}
            eventos={eventos}
            destaque={evento?.tradeDate}
            alertas={estadoDosAlertas.alertas}
            escolhendoPreco={estadoDosAlertas.escolhendo}
            aoEscolherPreco={estadoDosAlertas.escolherNoGrafico}
            hoje={hoje}
            operacoes={operacoesDeTrade}
            posicao={posicaoDoGrafico}
            publicacoes={publicacoes}
            regua={regua}
            classeDeAltura="h-[320px] md:h-[440px] lg:h-[580px]"
          />

          {eventos.length > 0 && (
            <div className="flex flex-col gap-2.5 rounded-2xl bg-painel-2 p-3 md:flex-row md:items-center">
              <span className="flex shrink-0 flex-col">
                <span className="text-[13px] font-extrabold">Eventos deste papel</span>
                <span className="text-[11px] font-semibold text-tinta-3">
                  {eventos.length === 1 ? "cruzou 3σ uma vez" : `cruzou 3σ ${eventos.length} vezes`}
                </span>
              </span>
              <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
                {eventos.map((e) => {
                  const selecionado = e.tradeDate === evento?.tradeDate;
                  return (
                    <Link
                      key={e.tradeDate}
                      href={`/papel/${ticker}/?data=${e.tradeDate}`}
                      replace
                      scroll={false}
                      aria-current={selecionado ? "true" : undefined}
                      className={`num flex h-10 shrink-0 items-center gap-2 rounded-full px-3.5 text-[13px] font-bold transition-colors ${
                        selecionado
                          ? "bg-primario text-primario-tinta"
                          : "border border-linha bg-painel text-tinta hover:border-acento"
                      }`}
                    >
                      {e.zLog >= LIMIAR_DO_ALERTA && <span className="h-2 w-2 rounded-full bg-evento" />}
                      {fmtData(e.tradeDate).slice(0, 5)}
                      <span className={selecionado ? "opacity-75" : "text-acento"}>{numero(e.zLog)}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          )}
        </section>

        {/* Desvio, numeros e leitura */}
        {evento && (
          <section className="flex flex-col gap-4 lg:col-start-1 lg:row-start-2">
            <div className="cartao flex flex-col gap-4 p-5">
              <div className="flex items-center justify-between">
                <h2 className="text-[16px] font-extrabold">Desvio do volume</h2>
                <span className="text-[12px] font-bold text-evento-tinta">
                  alerta em {numero(LIMIAR_DO_ALERTA, 0)}σ
                </span>
              </div>
              <div className="hidden items-center gap-4 lg:flex">
                <AnelDoDesvio z={evento.zLog} tamanho={104} espessura={11} />
                <div className="flex flex-col gap-1">
                  <span className="text-[13px] font-bold text-tinta-2">maior entre as janelas</span>
                  <span className="num text-[12px] font-semibold text-tinta-3">
                    janela de {evento.zJanela} pregões
                  </span>
                  {evento.zRobust !== null && (
                    <span className="num text-[12px] font-semibold text-tinta-3">
                      z robusto {numero(evento.zRobust)}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex flex-col gap-2.5">
                {janelas.map((j) => {
                  const z = evento.zByWindow[j] ?? 0;
                  const largura = Math.min(Math.max(z, 0), TETO_DAS_JANELAS) / TETO_DAS_JANELAS;
                  return (
                    <div key={j} className="flex items-center gap-2.5">
                      <span className="num w-8 text-[12px] font-bold text-tinta-3">{j}d</span>
                      <span className="relative h-2 flex-1 rounded-full bg-selecao">
                        <span
                          className={`absolute inset-y-0 left-0 rounded-full ${z >= LIMIAR_DO_ALERTA ? "bg-evento" : "bg-acento"}`}
                          style={{ width: `${largura * 100}%` }}
                        />
                        <span
                          className="absolute -top-1 h-4 w-0.5 rounded-sm bg-evento"
                          style={{ left: `${(LIMIAR_DO_ALERTA / TETO_DAS_JANELAS) * 100}%` }}
                        />
                      </span>
                      <span className="num w-10 text-right text-[13px] font-extrabold">{numero(z)}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="cartao grid grid-cols-2 gap-2.5 p-3.5">
              <Quadro
                rotulo="Volume relativo"
                valor={multiplo(evento.rvol)}
                nota={`mediana de ${janelas[0] ?? 30}d`}
              />
              <Quadro
                rotulo="Financeiro"
                valor={dinheiro(evento.volumeFinancial)}
                nota={evento.tradesCount ? `${numero(evento.tradesCount, 0)} negócios` : null}
              />
              <Quadro
                rotulo="Ticket médio"
                valor={reais(evento.avgTicket, 0)}
                nota={`z ${numero(evento.ticketZ, 1)}`}
              />
              <Quadro
                rotulo="z do mercado"
                valor={numero(evento.mktVolZ)}
                nota={mercadoCalmo ? "dia normal" : "mercado agitado"}
              />
            </div>

            {ticket && (
              <p className="rounded-2xl bg-selecao px-4 py-3.5 text-[13px] leading-relaxed text-tinta-2">
                Ticket de <strong className="num text-tinta">{reais(evento.avgTicket, 0)}</strong>
                {evento.tradesCount ? (
                  <>
                    {" "}com <strong className="num text-tinta">{numero(evento.tradesCount, 0)}</strong> negócios
                  </>
                ) : null}
                : <strong className="text-acento">{ticket}</strong>.
              </p>
            )}
          </section>
        )}

        {/* Contexto e alerta */}
        <section className="flex flex-col gap-4 lg:col-start-3 lg:row-span-2 lg:row-start-1">
          {(evento || verFundamentos) && (
            <div className="cartao px-5 pb-2 pt-5">
              <div className="mb-1.5 flex items-center justify-between gap-3">
                {comAbas ? (
                  <div className="flex items-center gap-1" role="tablist" aria-label="O que ver">
                    {(["evento", "fundamentos"] as const).map((chave) => (
                      <button
                        key={chave}
                        type="button"
                        role="tab"
                        aria-selected={aba === chave}
                        onClick={() => setAba(chave)}
                        className={`rounded-full px-3 py-1.5 text-[14px] font-extrabold transition-colors ${
                          aba === chave ? "bg-selecao text-acento" : "text-tinta-3 hover:text-tinta"
                        }`}
                      >
                        {chave === "evento" ? "Evento" : "Fundamentos"}
                      </button>
                    ))}
                  </div>
                ) : (
                  <h2 className="text-[16px] font-extrabold">
                    {evento ? "Contexto do evento" : "Fundamentos"}
                  </h2>
                )}
                <span className="shrink-0 text-[12px] font-semibold text-tinta-3">a leitura é sua</span>
              </div>
              {verFundamentos ? (
                painelDeFundamentos
              ) : (
                evento && (
                  <>
                    <LinhaDeContexto rotulo="Variação do dia" valor={percentual(evento.retDay)} cor={corDaDirecao(evento.retDay)} />
                    <LinhaDeContexto rotulo="Gap de abertura" valor={percentual(evento.gap)} cor={corDaDirecao(evento.gap)} />
                    <LinhaDeContexto rotulo="Fechou no range" valor={proporcao(evento.clv)} fracao={evento.clv} />
                    <LinhaDeContexto rotulo="Amplitude do dia" valor={proporcao(evento.rangeNorm, 1)} />
                    <LinhaDeContexto
                      rotulo={faixa ? `Faixa de 252 pregões · ${faixa}` : "Faixa de 252 pregões"}
                      valor={proporcao(evento.pos252)}
                      fracao={evento.pos252}
                    />
                    <LinhaDeContexto
                      rotulo="20 pregões anteriores"
                      valor={percentual(evento.retPrior20)}
                      cor={corDaDirecao(evento.retPrior20)}
                    />
                    <LinhaDeContexto rotulo="z do ticket" valor={numero(evento.ticketZ, 1)} />
                    <div className="flex min-h-[50px] items-center gap-3">
                      <span className="flex-1 text-[13px] font-extrabold">z líquido do mercado</span>
                      <span className="num inline-flex h-8 items-center rounded-full bg-selecao px-3 text-[15px] font-extrabold text-acento">
                        {numero(evento.zExcess)}
                      </span>
                    </div>
                  </>
                )
              )}
            </div>
          )}
          <PainelDeTrade estado={estadoDosTrades} hoje={hoje} />
          <PainelDeAlerta estado={estadoDosAlertas} />
        </section>
      </div>
    </div>
  );
}
