"use client";

import Link from "next/link";
import { fmtR, type Nivel, SAIDAS } from "@/lib/backtest-tela";
import { diaCurto } from "@/lib/formato";
import {
  type Bloco,
  type Conferencia,
  chaveDoBacktest,
  MAXIMO_DE_ENCERRADOS,
  NOME_DO_SETUP,
  textoAoVivo,
} from "@/lib/setups-tela";
import { CartaoArmado, LinhaDeEncerrado, LinhaEmAndamento } from "./CartaoDeSetup";
import { PreferenciaDoSetup } from "./PreferenciaDoSetup";
import { Selo } from "./ResumoDoBacktest";

type Props = {
  bloco: Bloco;
  nivel: Nivel | undefined;
  conferencia?: Conferencia;
  hoje: string;
  ultimoPregao: string | null;
};

/** "3 armados hoje · 2 em andamento", com o singular certo. */
export function resumoDoBloco(b: Pick<Bloco, "armados" | "emAndamento">): string {
  const a = b.armados.length;
  const m = b.emAndamento.length;
  return `${a} armado${a === 1 ? "" : "s"} hoje · ${m} em andamento`;
}

/** Nome, selo do nivel do backtest (se ha rodada) e a contagem. */
export function CabecalhoDoBloco({ bloco, nivel }: Pick<Props, "bloco" | "nivel">) {
  return (
    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
      <h2 className="text-[18px] font-extrabold">{NOME_DO_SETUP[bloco.categoria]}</h2>
      {nivel && <Selo nivel={nivel} />}
      <span className="num text-[13px] font-semibold text-tinta-3">{resumoDoBloco(bloco)}</span>
    </div>
  );
}

function Subsecao({
  titulo,
  contagem,
  children,
}: {
  titulo: string;
  contagem: number;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-[14px] font-extrabold">
        {titulo}
        <span className="num ml-2 text-[12px] font-bold text-tinta-3">{contagem}</span>
      </h3>
      {children}
    </div>
  );
}

const GRADE = "grid gap-3 md:grid-cols-2 xl:grid-cols-3";

/**
 * A conferencia ao vivo: o que o setup fez desde a estreia, ao lado do numero
 * do backtest (2016-2026). Decisao de 21/10/2026: o historico ao vivo e a
 * conferencia da regra.
 */
function LinhaDeConferencia({ conferencia }: { conferencia: Conferencia | undefined }) {
  const bt = conferencia?.backtest;
  return (
    <div className="flex flex-col gap-0.5 rounded-xl bg-painel-2 px-3 py-2 text-[12px] font-semibold text-tinta-2">
      <span className="num">{textoAoVivo(conferencia?.aoVivo ?? null)}</span>
      {bt && bt.r !== null && (
        <span className="num text-tinta-3">
          Backtest 2016–2026: {fmtR(bt.r)} por trade, já com custo
          {bt.saida ? ` · saída “${SAIDAS[bt.saida]}”` : ""}
        </span>
      )}
    </div>
  )
}

/** O miolo de um bloco: preferencias, armados, em andamento, encerrados e o link do Backtest. */
export function CorpoDoBloco({ bloco, conferencia, hoje, ultimoPregao }: Omit<Props, "nivel">) {
  return (
    <div className="flex flex-col gap-4">
      <PreferenciaDoSetup
        key={`${bloco.alerta}-${bloco.saida}`}
        categoria={bloco.categoria}
        alerta={bloco.alerta}
        saida={bloco.saida}
      />
      <LinhaDeConferencia conferencia={conferencia} />

      <Subsecao titulo="Armados hoje" contagem={bloco.armados.length}>
        {bloco.armados.length === 0 ? (
          <p className="text-[13px] font-semibold text-tinta-3">
            Nenhum armado no último pregão{ultimoPregao ? ` (${diaCurto(ultimoPregao)})` : ""}.
          </p>
        ) : (
          <>
            <p className="text-[12px] font-semibold text-tinta-3">
              Entram se o pregão seguinte passar do gatilho, R$ 0,01 acima da máxima do candle.
            </p>
            <div className={GRADE}>
              {bloco.armados.map((s) => (
                <CartaoArmado key={s.id} s={s} hoje={hoje} />
              ))}
            </div>
          </>
        )}
      </Subsecao>

      <Subsecao titulo="Em andamento" contagem={bloco.emAndamento.length}>
        {bloco.emAndamento.length === 0 ? (
          <p className="text-[13px] font-semibold text-tinta-3">Nenhum em andamento.</p>
        ) : (
          <>
            <ul className="flex flex-col divide-y divide-linha">
              {bloco.emAndamento.map((s) => (
                <LinhaEmAndamento key={s.id} s={s} />
              ))}
            </ul>
            <p className="text-[12px] font-semibold text-tinta-3">
              Resultado até o último fechamento, em R e já com o custo, como no backtest.
            </p>
          </>
        )}
      </Subsecao>

      <Subsecao titulo="Últimos encerrados" contagem={bloco.encerrados.length}>
        {bloco.encerrados.length === 0 ? (
          <p className="text-[13px] font-semibold text-tinta-3">Nenhum encerrado nos últimos 180 dias.</p>
        ) : (
          <>
            <ul className="flex flex-col divide-y divide-linha">
              {bloco.encerrados.map((s) => (
                <LinhaDeEncerrado key={s.id} s={s} />
              ))}
            </ul>
            <p className="text-[12px] font-semibold text-tinta-3">
              Os {MAXIMO_DE_ENCERRADOS} mais recentes. O resultado em R é o ganho ou a perda em
              múltiplos do risco (entrada menos stop).
            </p>
          </>
        )}
      </Subsecao>

      <Link
        href={`/setups/backtest?setup=${encodeURIComponent(chaveDoBacktest(bloco.categoria))}`}
        className="toque inline-flex h-11 w-fit items-center rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
      >
        ver no Backtest
      </Link>
    </div>
  );
}

/** Setup com alerta ligado: aberto, no topo da aba. */
export function BlocoLigado(props: Props) {
  return (
    <section className="cartao flex flex-col gap-4 p-4 md:p-5">
      <CabecalhoDoBloco bloco={props.bloco} nivel={props.nivel} />
      <CorpoDoBloco
        bloco={props.bloco}
        conferencia={props.conferencia}
        hoje={props.hoje}
        ultimoPregao={props.ultimoPregao}
      />
    </section>
  );
}

/** Setup sem alerta: fechado; toca e abre. */
export function BlocoFechado(props: Props) {
  return (
    <details className="cartao group">
      <summary className="toque flex cursor-pointer list-none items-center gap-3 p-4 md:p-5 [&::-webkit-details-marker]:hidden">
        <CabecalhoDoBloco bloco={props.bloco} nivel={props.nivel} />
        <span
          aria-hidden
          className="shrink-0 text-[18px] font-bold text-tinta-3 transition-transform group-open:rotate-90"
        >
          ›
        </span>
      </summary>
      <div className="px-4 pb-4 md:px-5 md:pb-5">
        <CorpoDoBloco
          bloco={props.bloco}
          conferencia={props.conferencia}
          hoje={props.hoje}
          ultimoPregao={props.ultimoPregao}
        />
      </div>
    </details>
  );
}
