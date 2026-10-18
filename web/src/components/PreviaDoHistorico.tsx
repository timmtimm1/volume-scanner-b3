"use client";

/**
 * A previa do evento escolhido no historico, ao lado da lista (computador).
 *
 * O grafico e o da ficha -- candles, volume, Bollinger e as medias de quem
 * olha --, centrado no pregao do evento, que sai dourado. So para ver: sem
 * regua e sem alertas, que moram na ficha completa, a um clique.
 *
 * Fica fixo na tela enquanto a lista rola, para trocar de evento sem perder o
 * lugar na lista.
 */

import Link from "next/link";
import { Grafico } from "@/components/Grafico";
import {
  data as fmtData,
  dinheiro,
  multiplo,
  nomeDaEmpresa,
  numero,
  percentual,
  reais,
} from "@/lib/formato";
import type { LinhaDoHistorico } from "@/lib/types";
import { useBarrasDoPapel } from "@/lib/useBarrasDoPapel";

/**
 * A altura do grafico acompanha a da janela: a previa inteira cabe na tela
 * sem rolar. O resto (cabecalho, barra de ferramentas, margens) e ~250 px.
 */
const ALTURA_DO_GRAFICO = "h-[max(340px,calc(100dvh-250px))]";

function Numero({ rotulo, valor, cor = "text-tinta" }: { rotulo: string; valor: string; cor?: string }) {
  return (
    <span className="flex flex-col gap-0.5">
      <span className="text-[11px] font-bold text-tinta-3">{rotulo}</span>
      <span className={`num text-[14px] font-extrabold ${cor}`}>{valor}</span>
    </span>
  );
}

export function PreviaDoHistorico({
  evento,
  limiarDoAlerta,
  aoAbrir,
}: {
  evento: LinhaDoHistorico;
  limiarDoAlerta: number;
  /** Chamado antes de ir para a ficha, para o historico guardar onde estava. */
  aoAbrir: () => void;
}) {
  const { dados, erro } = useBarrasDoPapel(evento.ticker);
  const nome = nomeDaEmpresa(evento.empresa);
  const corDaVariacao = (evento.retDay ?? 0) >= 0 ? "text-alta" : "text-baixa";
  const href = `/papel/${evento.ticker}/?data=${evento.tradeDate}`;

  return (
    // Segue a rolagem pela grade do Organizar (a caixa e `fixa`), nao por aqui.
    <section className="cartao flex min-w-0 flex-col gap-3 p-4">
      <div className="flex items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="flex items-baseline gap-2">
            <span className="text-[22px] font-extrabold leading-tight">{evento.ticker}</span>
            <span className="num text-[13px] font-semibold text-tinta-3">
              {fmtData(evento.tradeDate)}
            </span>
          </span>
          {nome && <span className="truncate text-[13px] font-bold text-tinta-2">{nome}</span>}
        </div>
        <Link
          href={href}
          onClick={aoAbrir}
          className="flex h-10 shrink-0 items-center gap-2 rounded-full bg-primario px-4 text-[13px] font-extrabold text-primario-tinta"
        >
          Abrir ficha completa
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden>
            <path d="M8 4l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </Link>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-2 rounded-2xl bg-painel-2 px-4 py-2.5">
        <Numero
          rotulo="Desvio (z)"
          valor={numero(evento.zLog)}
          cor={evento.zLog >= limiarDoAlerta ? "text-evento-tinta" : "text-acento"}
        />
        <Numero rotulo="z líquido" valor={numero(evento.zExcess)} />
        <Numero rotulo="rvol" valor={multiplo(evento.rvol)} />
        <Numero rotulo="Variação" valor={percentual(evento.retDay)} cor={corDaVariacao} />
        <Numero rotulo="Ticket" valor={reais(evento.avgTicket, 0)} />
        <Numero rotulo="Volume" valor={dinheiro(evento.volumeFinancial)} />
      </div>

      {dados ? (
        <Grafico
          barras={dados.barras}
          eventos={dados.eventos}
          destaque={evento.tradeDate}
          classeDeAltura={ALTURA_DO_GRAFICO}
        />
      ) : (
        <div
          className={`flex items-center justify-center rounded-2xl border border-dashed border-linha-2 text-[13px] font-semibold text-tinta-3 ${ALTURA_DO_GRAFICO}`}
        >
          {erro ? (
            <span>
              Não deu para carregar o gráfico de {evento.ticker}.{" "}
              <Link href={href} onClick={aoAbrir} className="text-acento underline">
                Abrir a ficha
              </Link>
            </span>
          ) : (
            `Carregando ${evento.ticker}…`
          )}
        </div>
      )}
    </section>
  );
}
