"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { AnelDoDesvio } from "@/components/AnelDoDesvio";
import { FaixaDeVolume, MiniCandles } from "@/components/MiniGraficos";
import {
  data as fmtData,
  diaDaSemana,
  dinheiro,
  leituraDoTicket,
  multiplo,
  numero,
  percentual,
  proporcao,
  reais,
} from "@/lib/formato";
import type { Barra, Evento, FaixaDeDesvio, Pregao } from "@/lib/types";

/**
 * Tela 1: o pregao, quanto cada papel fugiu do normal e a lista de eventos.
 *
 * O filtro de z muda so o que a tela mostra. O Telegram continua avisando pelo
 * `alert.threshold` do config.yaml -- por isso a marca de "notificado" vem do
 * evento, e nao da posicao do controle.
 */

type Props = {
  pregao: Pregao;
  eventos: Evento[];
  distribuicao: FaixaDeDesvio[];
  barras: Record<string, Barra[]>;
  limiarDoAlerta: number;
  minimo: number;
};

const ROTULO_DA_FAIXA = ["abaixo de 1σ", "1 a 2σ", "2 a 3σ", "3 a 4σ", "4 a 5σ", "5 a 6σ", "6σ ou mais"];
const TETO = 8;

function corDaFaixa(faixa: number): string {
  if (faixa >= 6) return "var(--evento)";
  if (faixa >= 3) return "var(--acento)";
  return "var(--lavanda)";
}

function ChipDeVariacao({ valor }: { valor: number | null }) {
  if (valor === null) return <span className="text-tinta-3">—</span>;
  return (
    <span
      className={`num inline-flex h-6 items-center rounded-full px-2 text-[12px] font-bold ${
        valor >= 0 ? "bg-alta-fundo text-alta" : "bg-baixa-fundo text-baixa"
      }`}
    >
      {percentual(valor)}
    </span>
  );
}

function Quadro({ rotulo, valor, nota, destaque }: { rotulo: string; valor: string; nota: string; destaque?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-2xl bg-painel-2 p-3">
      <span className={`num text-[22px] font-extrabold tracking-tight ${destaque ?? ""}`}>{valor}</span>
      <span className="truncate text-[12px] font-bold text-tinta-2">{rotulo}</span>
      <span className="truncate text-[11px] font-semibold text-tinta-3">{nota}</span>
    </div>
  );
}

function BarrasDasJanelas({ evento, limiar }: { evento: Evento; limiar: number }) {
  const janelas = Object.keys(evento.zByWindow)
    .map(Number)
    .sort((a, b) => a - b);
  return (
    <div className="flex flex-col gap-2">
      {janelas.map((j) => {
        const z = evento.zByWindow[j] ?? 0;
        return (
          <div key={j} className="flex items-center gap-2.5">
            <span className="num w-8 text-[12px] font-bold text-tinta-3">{j}d</span>
            <span className="relative h-2 flex-1 rounded-full bg-selecao">
              <span
                className={`absolute inset-y-0 left-0 rounded-full ${z >= limiar ? "bg-evento" : "bg-acento"}`}
                style={{ width: `${(Math.min(Math.max(z, 0), TETO) / TETO) * 100}%` }}
              />
              <span className="absolute -top-1 h-4 w-0.5 rounded-sm bg-evento" style={{ left: `${(limiar / TETO) * 100}%` }} />
            </span>
            <span className="num w-10 text-right text-[13px] font-extrabold">{numero(z)}</span>
          </div>
        );
      })}
    </div>
  );
}

export function PainelDoScanner({ pregao, eventos, distribuicao, barras, limiarDoAlerta, minimo }: Props) {
  const router = useRouter();

  /**
   * Abre no limiar do alerta -- e o que o Telegram mandou, e o que interessa
   * primeiro. Em pregao calmo isso da lista vazia, entao comeca no piso do site.
   */
  const houveAlerta = eventos.some((e) => e.zLog >= limiarDoAlerta);
  const [corte, setCorte] = useState(houveAlerta ? limiarDoAlerta : minimo);
  const [escolhido, setEscolhido] = useState<string | null>(null);

  const visiveis = useMemo(
    () => eventos.filter((e) => e.zLog >= corte).sort((a, b) => b.zLog - a.zLog),
    [eventos, corte],
  );
  // O papel da previa: o escolhido, se ainda estiver na lista; senao o primeiro.
  const previa = visiveis.find((e) => e.ticker === escolhido) ?? visiveis[0] ?? null;

  const totalAcimaDoPiso = distribuicao.reduce((a, f) => a + f.papeis, 0);
  const maiorFaixa = Math.max(1, ...distribuicao.map((f) => f.papeis));
  const aPartirDe3 = distribuicao.filter((f) => f.faixa >= 3).reduce((a, f) => a + f.papeis, 0);
  const mercadoCalmo = (pregao.mktVolZ ?? 0) < 2;

  function abrir(evento: Evento) {
    // Com a previa na tela (computador), o clique escolhe; sem ela, abre a ficha.
    if (window.matchMedia("(min-width: 1024px)").matches) {
      setEscolhido(evento.ticker);
    } else {
      router.push(`/papel/${evento.ticker}/?data=${evento.tradeDate}`);
    }
  }

  const fracaoDoCorte = (corte - minimo) / (TETO - minimo);
  const fracaoDoLimiar = (limiarDoAlerta - minimo) / (TETO - minimo);

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)_380px] lg:items-start">
      {/* Resumo do pregao */}
      <section className="flex flex-col gap-4">
        <div className="cartao flex flex-col gap-4 p-5">
          <div className="flex flex-col gap-0.5">
            <h1 className="text-[22px] font-extrabold tracking-tight lg:text-[18px]">Scanner do dia</h1>
            <p className="num text-[13px] font-semibold text-tinta-3">
              Pregão de {fmtData(pregao.tradeDate)} · {diaDaSemana(pregao.tradeDate)}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <Quadro rotulo="Avaliados" valor={numero(pregao.avaliados, 0)} nota="papéis no pregão" />
            <Quadro
              rotulo={`A partir de ${numero(corte, 1)}σ`}
              valor={numero(visiveis.length, 0)}
              nota="na lista"
              destaque="text-acento"
            />
            <Quadro
              rotulo="Notificados"
              valor={numero(pregao.notificados, 0)}
              nota={pregao.notificados > 0 ? "no Telegram" : "nada notificado"}
              destaque={pregao.notificados > 0 ? "text-evento-tinta" : undefined}
            />
            <Quadro
              rotulo="z do mercado"
              valor={numero(pregao.mktVolZ)}
              nota={mercadoCalmo ? "dia normal" : "mercado agitado"}
            />
          </div>

          {/* No celular a distribuicao vira uma faixa unica */}
          {totalAcimaDoPiso > 0 && (
            <div className="flex flex-col gap-1.5 lg:hidden">
              <div className="flex h-2.5 gap-0.5 overflow-hidden rounded-full">
                {distribuicao
                  .filter((f) => f.papeis > 0)
                  .map((f) => (
                    <span
                      key={f.faixa}
                      style={{ width: `${(f.papeis / totalAcimaDoPiso) * 100}%`, background: corDaFaixa(f.faixa) }}
                    />
                  ))}
              </div>
              <div className="flex justify-between text-[11px] font-bold">
                <span className="num text-tinta-3">{distribuicao[0].papeis} abaixo de 1σ</span>
                <span className="num text-acento">{aPartirDe3} a partir de 3σ</span>
              </div>
            </div>
          )}
        </div>

        <div className="cartao hidden flex-col gap-3 p-5 lg:flex">
          <div className="flex flex-col gap-0.5">
            <h2 className="text-[16px] font-extrabold">Quanto cada papel fugiu do normal</h2>
            <p className="num text-[12px] font-semibold text-tinta-3">
              {numero(totalAcimaDoPiso, 0)} papéis acima do piso de volume
            </p>
          </div>
          <div className="flex flex-col gap-2.5">
            {distribuicao.map((f) => (
              <div key={f.faixa} className="grid grid-cols-[84px_minmax(0,1fr)_36px] items-center gap-2.5">
                <span className="num text-[12px] font-bold text-tinta-3">{ROTULO_DA_FAIXA[f.faixa]}</span>
                <span className="h-3 rounded-full bg-painel-2">
                  <span
                    className="block h-3 rounded-full"
                    style={{
                      width: f.papeis === 0 ? 0 : `${Math.max(3, (f.papeis / maiorFaixa) * 100)}%`,
                      background: corDaFaixa(f.faixa),
                    }}
                  />
                </span>
                <span className="num text-right text-[13px] font-extrabold">{f.papeis}</span>
              </div>
            ))}
          </div>
        </div>

        <p className="hidden rounded-2xl bg-selecao px-4 py-3.5 text-[13px] leading-relaxed text-tinta-2 lg:block">
          {mercadoCalmo ? (
            <>
              Volume do mercado dentro do normal (<span className="num font-bold text-tinta">z {numero(pregao.mktVolZ)}</span>): o que aparece na lista é movimento dos papéis.
            </>
          ) : (
            <>
              Mercado inteiro girando mais que o normal (<span className="num font-bold text-tinta">z {numero(pregao.mktVolZ)}</span>): leia o z líquido de cada papel antes.
            </>
          )}
          {!houveAlerta && <> Nenhum papel cruzou {numero(limiarDoAlerta, 0)}σ neste pregão.</>}
        </p>
      </section>

      {/* Eventos */}
      <section className="cartao flex min-w-0 flex-col gap-4 p-4 md:p-5">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-[18px] font-extrabold">Eventos do dia</h2>
          <p className="text-[13px] font-semibold text-tinta-3">
            {visiveis.length === 1 ? "1 papel" : `${visiveis.length} papéis`} a partir de {numero(corte, 1)}σ · o Telegram avisa acima de {numero(limiarDoAlerta, 0)}σ
          </p>
        </div>

        <div className="flex flex-col gap-2 rounded-2xl bg-painel-2 px-4 py-3.5">
          <div className="flex items-baseline justify-between">
            <label htmlFor="corte-do-scanner" className="text-[13px] font-bold text-tinta-2">
              Mostrar a partir de
            </label>
            <span className="num text-[15px] font-extrabold text-acento">{numero(corte, 1)}σ</span>
          </div>
          <div className="relative">
            <input
              id="corte-do-scanner"
              type="range"
              min={minimo}
              max={TETO}
              step={0.1}
              value={corte}
              onChange={(e) => setCorte(Number(e.target.value))}
              className="h-6 w-full cursor-pointer bg-transparent"
              aria-valuetext={`${numero(corte, 1)} sigma`}
            />
            <span
              aria-hidden
              className="pointer-events-none absolute top-[3px] h-[18px] w-0.5 rounded-sm bg-evento"
              style={{ left: `calc(${fracaoDoLimiar * 100}% + ${(0.5 - fracaoDoLimiar) * 16}px)` }}
            />
          </div>
          <div className="flex justify-between text-[11px] font-bold">
            <span className="num text-tinta-3">{numero(minimo, 0)}σ</span>
            <span className="num text-evento-tinta">alerta em {numero(limiarDoAlerta, 0)}σ</span>
            <span className="num text-tinta-3">{TETO}σ</span>
          </div>
          <span className="sr-only">{Math.round(fracaoDoCorte * 100)}% da faixa</span>
        </div>

        {visiveis.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-linha-2 p-8 text-center text-[13px] font-semibold text-tinta-3">
            Nenhum papel a partir de {numero(corte, 1)}σ neste pregão.
          </div>
        ) : (
          <>
            {/* Computador e tablet: linhas */}
            <div className="hidden grid-cols-[96px_52px_minmax(110px,1fr)_60px_84px_104px] gap-3 px-3 md:grid">
              <span className="rotulo">Papel</span>
              <span className="rotulo">Desvio</span>
              <span className="rotulo">Volume · 40 pregões</span>
              <span className="rotulo">Normal</span>
              <span className="rotulo">Variação</span>
              <span className="rotulo text-right">Financeiro</span>
            </div>
            <div className="hidden flex-col gap-0.5 md:flex">
              {visiveis.map((e) => {
                const selecionado = previa?.ticker === e.ticker;
                return (
                  <div
                    key={e.ticker}
                    role="button"
                    tabIndex={0}
                    onClick={() => abrir(e)}
                    onKeyDown={(k) => {
                      if (k.key === "Enter" || k.key === " ") {
                        k.preventDefault();
                        abrir(e);
                      }
                    }}
                    aria-pressed={selecionado}
                    className={`grid h-16 cursor-pointer grid-cols-[96px_52px_minmax(110px,1fr)_60px_84px_104px] items-center gap-3 rounded-2xl px-3 transition-colors ${
                      selecionado ? "lg:bg-selecao" : "hover:bg-painel-2"
                    }`}
                  >
                    <span className="flex min-w-0 flex-col">
                      <span className="flex items-center gap-1.5 text-[15px] font-extrabold">
                        {e.ticker}
                        {e.notificado && <span className="h-2 w-2 rounded-full bg-evento" title="notificado no Telegram" />}
                      </span>
                      <span className="num text-[11px] font-semibold text-tinta-3">janela {e.zJanela}d</span>
                    </span>
                    <AnelDoDesvio z={e.zLog} tamanho={48} espessura={5} fonte={12} />
                    <FaixaDeVolume barras={barras[e.ticker] ?? []} diaDoEvento={e.tradeDate} />
                    <span className="num text-[14px] font-extrabold">{multiplo(e.rvol)}</span>
                    <span>
                      <ChipDeVariacao valor={e.retDay} />
                    </span>
                    <span className="num text-right text-[14px] font-bold text-tinta-2">{dinheiro(e.volumeFinancial)}</span>
                  </div>
                );
              })}
            </div>

            {/* Celular: cartoes */}
            <div className="flex flex-col gap-3 md:hidden">
              {visiveis.map((e) => (
                <Link
                  key={e.ticker}
                  href={`/papel/${e.ticker}/?data=${e.tradeDate}`}
                  className="flex flex-col gap-2.5 rounded-2xl border border-linha bg-painel p-3.5"
                >
                  <div className="flex items-center gap-2.5">
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[18px] font-extrabold">{e.ticker}</span>
                        <ChipDeVariacao valor={e.retDay} />
                        {e.notificado && <span className="h-2 w-2 rounded-full bg-evento" title="notificado no Telegram" />}
                      </div>
                      <span className="num truncate text-[12px] font-semibold text-tinta-3">
                        {multiplo(e.rvol)} o normal · {dinheiro(e.volumeFinancial)}
                      </span>
                    </div>
                    <AnelDoDesvio z={e.zLog} tamanho={52} espessura={5} fonte={13} />
                  </div>
                  <FaixaDeVolume barras={barras[e.ticker] ?? []} diaDoEvento={e.tradeDate} altura={36} />
                </Link>
              ))}
            </div>
          </>
        )}
      </section>

      {/* Previa do papel escolhido (computador) */}
      {previa && (
        <section className="cartao sticky top-4 hidden flex-col gap-4 p-5 lg:flex">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-selecao text-[15px] font-extrabold text-acento">
              {previa.ticker.slice(0, 2)}
            </span>
            <div className="flex min-w-0 flex-1 flex-col">
              <span className="text-[22px] font-extrabold leading-tight">{previa.ticker}</span>
              <span className="num truncate text-[12px] font-semibold text-tinta-3">
                {leituraDoTicket(previa.avgTicket, previa.ticketZ, previa.tradesCount) ?? `ticket ${reais(previa.avgTicket, 0)}`}
                {previa.ticketZ !== null && ` · ticket z ${numero(previa.ticketZ, 1)}`}
              </span>
            </div>
            <AnelDoDesvio z={previa.zLog} tamanho={58} espessura={6} fonte={14} />
          </div>

          <div className="flex items-center gap-2.5">
            <span className="num text-[26px] font-extrabold tracking-tight">{reais(previa.close)}</span>
            <ChipDeVariacao valor={previa.retDay} />
          </div>

          <div className="border-t border-linha pt-3">
            <MiniCandles barras={barras[previa.ticker] ?? []} diaDoEvento={previa.tradeDate} />
          </div>

          <BarrasDasJanelas evento={previa} limiar={limiarDoAlerta} />

          <div className="grid grid-cols-3 gap-2">
            {(
              [
                ["Gap", percentual(previa.gap), (previa.gap ?? 0) >= 0 ? "text-alta" : "text-baixa"],
                ["No range", proporcao(previa.clv), "text-tinta"],
                ["Amplitude", proporcao(previa.rangeNorm, 1), "text-tinta"],
                ["Faixa 252d", proporcao(previa.pos252), "text-tinta"],
                ["20 pregões", percentual(previa.retPrior20), (previa.retPrior20 ?? 0) >= 0 ? "text-alta" : "text-baixa"],
                ["z líquido", numero(previa.zExcess), "text-acento"],
              ] as const
            ).map(([rotulo, valor, cor]) => (
              <div key={rotulo} className="flex min-w-0 flex-col gap-0.5 rounded-xl bg-painel-2 px-3 py-2.5">
                <span className="truncate text-[11px] font-bold text-tinta-3">{rotulo}</span>
                <span className={`num text-[15px] font-extrabold ${cor}`}>{valor}</span>
              </div>
            ))}
          </div>

          <Link
            href={`/papel/${previa.ticker}/?data=${previa.tradeDate}`}
            className="flex h-12 items-center justify-center gap-2 rounded-full bg-primario text-[15px] font-extrabold text-primario-tinta"
          >
            Abrir ficha completa
            <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden>
              <path d="M7 4l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        </section>
      )}
    </div>
  );
}
