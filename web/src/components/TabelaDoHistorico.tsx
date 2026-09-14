"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { data as fmtData, dinheiro, multiplo, numero, percentual, reais } from "@/lib/formato";
import type { LinhaDoHistorico } from "@/lib/types";

/**
 * Quantas linhas vao para a tela de cada vez. Cada linha renderizada pesa perto
 * de 1 KB de HTML; com os 1.000 eventos na tela, a pagina passava de 1 MB. O
 * dado de todos continua carregado, e os filtros valem sobre ele inteiro.
 */
const LINHAS_POR_VEZ = 100;

type Props = {
  /** Os eventos mais recentes, do pregao mais novo para o mais antigo. */
  eventos: LinhaDoHistorico[];
  limiarDoAlerta: number;
  minimo: number;
};

/**
 * Serve para revisitar eventos e ir construindo repertorio de padroes.
 *
 * Filtra por papel, faixa de z e periodo, como a Tela 3 do plano pede. O
 * periodo vai ate onde os eventos carregados alcancam; o cabecalho diz qual e.
 */
export function TabelaDoHistorico({ eventos, limiarDoAlerta, minimo }: Props) {
  const ate = eventos[0]?.tradeDate;
  const de = eventos.at(-1)?.tradeDate;
  // Quantos cruzaram o limiar do alerta. O rotulo ao lado diz "acima de Nσ",
  // e nao "notificados": o historico e carga retroativa, e evento antigo nunca
  // foi notificado.
  const acimaDoLimiar = useMemo(
    () => eventos.filter((e) => e.zLog >= limiarDoAlerta).length,
    [eventos, limiarDoAlerta],
  );

  const [corte, setCorte] = useState(minimo);
  const [busca, setBusca] = useState("");
  // "" = sem limite daquele lado. Datas ISO comparam certo como texto.
  const [desde, setDesde] = useState("");
  const [atePeriodo, setAtePeriodo] = useState("");
  // null = ordem padrao (pregao mais recente primeiro, ja vinda do banco).
  // Um clique no cabecalho "Desvio (z)" liga a ordenacao por esse valor;
  // outro clique inverte; o terceiro volta a ordem padrao.
  const [ordemZ, setOrdemZ] = useState<"desc" | "asc" | null>(null);
  // Quantas linhas mostrar, amarrado aos filtros: mudou um filtro, volta a
  // mostrar a primeira leva sem precisar zerar estado dentro de efeito.
  const chaveDosFiltros = `${corte}|${busca}|${desde}|${atePeriodo}|${ordemZ}`;
  const [leva, setLeva] = useState({ chave: chaveDosFiltros, linhas: LINHAS_POR_VEZ });
  const linhasNaTela = leva.chave === chaveDosFiltros ? leva.linhas : LINHAS_POR_VEZ;

  const visiveis = useMemo(() => {
    const alvo = busca.trim().toUpperCase();
    const filtrados = eventos.filter(
      (e) =>
        e.zLog >= corte &&
        (!alvo || e.ticker.includes(alvo)) &&
        (!desde || e.tradeDate >= desde) &&
        (!atePeriodo || e.tradeDate <= atePeriodo),
    );
    if (!ordemZ) return filtrados;
    const sinal = ordemZ === "desc" ? -1 : 1;
    return [...filtrados].sort((a, b) => sinal * (a.zLog - b.zLog));
  }, [eventos, corte, busca, desde, atePeriodo, ordemZ]);

  function alternarOrdemZ() {
    setOrdemZ((atual) => (atual === "desc" ? "asc" : atual === "asc" ? null : "desc"));
  }


  const corDoZ = (z: number) => (z >= limiarDoAlerta ? "text-evento-tinta" : "text-acento");
  const corDaVariacao = (v: number | null) => ((v ?? 0) >= 0 ? "text-alta" : "text-baixa");
  const campo =
    "num toque h-11 rounded-xl border border-linha bg-painel px-3 text-[13px] font-semibold outline-none placeholder:text-tinta-3 focus:border-acento";

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex min-w-0 flex-col gap-0.5">
            <h1 className="text-[22px] font-extrabold tracking-tight">Histórico de eventos</h1>
            <p className="num text-[13px] font-semibold text-tinta-3">
              {de && ate
                ? `${fmtData(de)} a ${fmtData(ate)} · os ${numero(eventos.length, 0)} eventos mais recentes`
                : "sem eventos no período"}
            </p>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-3 rounded-2xl bg-evento-fundo px-4 py-2.5">
            <span className="num text-[24px] font-extrabold text-evento-tinta">
              {numero(acimaDoLimiar, 0)}
            </span>
            <span className="text-[12px] font-bold leading-tight text-evento-tinta">
              acima de
              <br />
              {numero(limiarDoAlerta, 0)}σ
            </span>
          </div>
        </div>

        <div className="grid gap-3 rounded-2xl bg-painel-2 p-3.5 sm:grid-cols-2 lg:grid-cols-[180px_auto_minmax(220px,1fr)_auto] lg:items-end">
          <label className="flex flex-col gap-1.5">
            <span className="rotulo">Papel</span>
            <input
              type="text"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="todos"
              className={campo}
            />
          </label>

          <div className="flex gap-3">
            <label className="flex flex-1 flex-col gap-1.5">
              <span className="rotulo">De</span>
              <input
                type="date"
                value={desde}
                min={de}
                max={ate}
                onChange={(e) => setDesde(e.target.value)}
                className={`${campo} w-full min-w-[9.5rem]`}
              />
            </label>
            <label className="flex flex-1 flex-col gap-1.5">
              <span className="rotulo">Até</span>
              <input
                type="date"
                value={atePeriodo}
                min={de}
                max={ate}
                onChange={(e) => setAtePeriodo(e.target.value)}
                className={`${campo} w-full min-w-[9.5rem]`}
              />
            </label>
          </div>

          <div className="flex flex-col gap-1.5 sm:col-span-2 lg:col-span-1">
            <div className="flex justify-between">
              <span className="rotulo">z mínimo</span>
              <span className="num text-[13px] font-extrabold text-acento">{numero(corte, 1)}σ</span>
            </div>
            <input
              type="range"
              min={minimo}
              max={8}
              step={0.1}
              value={corte}
              onChange={(e) => setCorte(Number(e.target.value))}
              aria-label="z mínimo"
              className="h-11 w-full cursor-pointer bg-transparent"
            />
          </div>

          <span className="num self-center text-[12px] font-bold text-tinta-3 lg:pb-3">
            {numero(visiveis.length, 0)} de {numero(eventos.length, 0)}
          </span>
        </div>
      </section>

      {visiveis.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-linha-2 p-8 text-center text-[13px] font-semibold text-tinta-3">
          Nenhum evento com esses filtros.
        </div>
      ) : (
        <section className="cartao overflow-hidden p-2 md:p-3">
          <div className="hidden grid-cols-[104px_96px_92px_72px_84px_120px_110px_1fr] gap-2 px-3 py-2 md:grid">
            <span className="rotulo">Pregão</span>
            <span className="rotulo">Papel</span>
            <button
              type="button"
              onClick={alternarOrdemZ}
              aria-label={
                ordemZ === "desc"
                  ? "Ordenado por desvio, do maior para o menor. Clique para inverter."
                  : ordemZ === "asc"
                    ? "Ordenado por desvio, do menor para o maior. Clique para voltar ao padrão."
                    : "Ordenar por desvio"
              }
              className="rotulo flex items-center justify-end gap-1 text-right transition-colors hover:text-acento"
            >
              Desvio (z)
              <span className="num text-[10px]">
                {ordemZ === "desc" ? "↓" : ordemZ === "asc" ? "↑" : "↕"}
              </span>
            </button>
            <span className="rotulo text-right">rvol</span>
            <span className="rotulo text-right">Var.</span>
            <span className="rotulo text-right">Desvio líquido (z)</span>
            <span className="rotulo text-right">Ticket</span>
            <span className="rotulo text-right">Volume</span>
          </div>

          <div className="flex flex-col gap-0.5">
            {visiveis.slice(0, linhasNaTela).map((e) => (
              <Link
                key={`${e.ticker}-${e.tradeDate}`}
                href={`/papel/${e.ticker}?data=${e.tradeDate}`}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-xl px-3 py-2.5 transition-colors hover:bg-painel-2 md:grid-cols-[104px_96px_92px_72px_84px_120px_110px_1fr] md:gap-2"
              >
                <span className="order-1 text-[15px] font-extrabold md:order-2 md:text-[14px]">
                  {e.ticker}
                </span>
                <span
                  className={`num order-2 text-right text-[16px] font-extrabold md:order-3 md:text-[14px] ${corDoZ(e.zLog)}`}
                >
                  {numero(e.zLog)}
                </span>
                <span className="num order-3 col-span-2 text-[12px] font-semibold text-tinta-3 md:order-1 md:col-span-1 md:text-[13px] md:text-tinta-2">
                  {fmtData(e.tradeDate)}
                  <span className="md:hidden">
                    {" · "}
                    {multiplo(e.rvol)}
                    {" · "}
                    <span className={`font-bold ${corDaVariacao(e.retDay)}`}>
                      {percentual(e.retDay)}
                    </span>
                    {" · "}
                    {dinheiro(e.volumeFinancial)}
                  </span>
                </span>
                <span className="num order-4 hidden text-right text-[13px] font-semibold text-tinta-2 md:block">
                  {multiplo(e.rvol)}
                </span>
                <span
                  className={`num order-5 hidden text-right text-[13px] font-bold md:block ${corDaVariacao(e.retDay)}`}
                >
                  {percentual(e.retDay)}
                </span>
                <span className="num order-6 hidden text-right text-[13px] font-semibold md:block">
                  {numero(e.zExcess)}
                </span>
                <span className="num order-7 hidden text-right text-[13px] font-semibold text-tinta-2 md:block">
                  {reais(e.avgTicket, 0)}
                </span>
                <span className="num order-8 hidden text-right text-[13px] font-semibold md:block">
                  {dinheiro(e.volumeFinancial)}
                </span>
              </Link>
            ))}
          </div>

          {visiveis.length > linhasNaTela && (
            <button
              type="button"
              onClick={() => setLeva({ chave: chaveDosFiltros, linhas: linhasNaTela + LINHAS_POR_VEZ })}
              className="toque mt-2 w-full rounded-xl bg-painel-2 px-4 py-3 text-[13px] font-bold text-tinta-2 transition-colors hover:text-acento"
            >
              mostrar mais {Math.min(LINHAS_POR_VEZ, visiveis.length - linhasNaTela)} · faltam{" "}
              <span className="num">{numero(visiveis.length - linhasNaTela, 0)}</span>
            </button>
          )}
        </section>
      )}
    </div>
  );
}
