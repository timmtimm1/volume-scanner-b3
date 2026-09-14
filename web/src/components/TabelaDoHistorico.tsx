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

  return (
    <>
      <header className="flex flex-wrap items-center gap-4 border-b border-linha bg-painel px-4 py-3.5 md:px-6">
        <div>
          <h1 className="text-[17px] font-bold">Histórico de eventos</h1>
          <p className="num mt-0.5 text-[11px] text-tinta-3">
            {de && ate
              ? `${fmtData(de)} a ${fmtData(ate)} · os ${numero(eventos.length, 0)} eventos mais recentes`
              : "sem eventos no período"}
          </p>
        </div>
        <div className="flex-1" />
        <div className="flex items-baseline gap-2">
          <span className="num text-[22px] font-semibold text-ambar">{acimaDoLimiar}</span>
          <span className="text-[11px] leading-tight text-tinta-2">
            acima de
            <br />
            {numero(limiarDoAlerta, 0)}σ
          </span>
        </div>
      </header>

      <div className="flex flex-wrap items-end gap-4 border-b border-linha bg-painel-2 px-4 py-3 md:px-6">
        <label className="block">
          <span className="rotulo mb-1.5 block">Papel</span>
          <input
            type="text"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="todos"
            className="toque w-36 rounded border border-linha-2 bg-painel px-2.5 py-1.5 text-[12px] outline-none placeholder:text-tinta-3 focus:border-ambar"
          />
        </label>

        <div className="flex gap-3">
          <label className="block">
            <span className="rotulo mb-1.5 block">De</span>
            <input
              type="date"
              value={desde}
              min={de}
              max={ate}
              onChange={(e) => setDesde(e.target.value)}
              className="num toque w-[9.5rem] rounded border border-linha-2 bg-painel px-2 py-1.5 text-[12px] outline-none focus:border-ambar"
            />
          </label>
          <label className="block">
            <span className="rotulo mb-1.5 block">Até</span>
            <input
              type="date"
              value={atePeriodo}
              min={de}
              max={ate}
              onChange={(e) => setAtePeriodo(e.target.value)}
              className="num toque w-[9.5rem] rounded border border-linha-2 bg-painel px-2 py-1.5 text-[12px] outline-none focus:border-ambar"
            />
          </label>
        </div>

        <div className="min-w-[180px] flex-1 md:max-w-[280px]">
          <div className="mb-1.5 flex justify-between">
            <span className="rotulo">z mínimo</span>
            <span className="num text-[11px] font-semibold text-ambar">
              {numero(corte, 1)}σ
            </span>
          </div>
          <input
            type="range"
            min={minimo}
            max={8}
            step={0.1}
            value={corte}
            onChange={(e) => setCorte(Number(e.target.value))}
            aria-label="z mínimo"
            className="h-6 w-full cursor-pointer bg-transparent"
          />
        </div>

        <span className="num self-end text-[11px] text-tinta-3">
          {numero(visiveis.length, 0)} de {numero(eventos.length, 0)}
        </span>
      </div>

      <div className="p-4 md:p-6">
        {visiveis.length === 0 ? (
          <div className="rounded-md border border-dashed border-linha-2 p-8 text-center text-[13px] text-tinta-3">
            Nenhum evento com esses filtros.
          </div>
        ) : (
          <div className="overflow-hidden rounded-md border border-linha bg-painel">
            <div className="hidden grid-cols-[96px_88px_68px_74px_82px_92px_110px_1fr] border-b border-linha bg-painel-2 px-3.5 py-2 md:grid">
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
                className="rotulo toque flex items-center justify-end gap-0.5 text-right transition-colors hover:text-tinta"
              >
                Desvio (z)
                <span className="num text-[9px]">
                  {ordemZ === "desc" ? "↓" : ordemZ === "asc" ? "↑" : "↕"}
                </span>
              </button>
              <span className="rotulo text-right">rvol</span>
              <span className="rotulo text-right">Var.</span>
              <span className="rotulo text-right">Desvio líquido (z)</span>
              <span className="rotulo text-right">Ticket</span>
              <span className="rotulo text-right">Volume</span>
            </div>

            {visiveis.slice(0, linhasNaTela).map((e) => (
              <Link
                key={`${e.ticker}-${e.tradeDate}`}
                href={`/papel/${e.ticker}?data=${e.tradeDate}`}
                className="toque flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-linha px-3.5 py-2.5 transition-colors last:border-b-0 hover:bg-painel-2 md:grid md:grid-cols-[96px_88px_68px_74px_82px_92px_110px_1fr] md:gap-0 md:py-2"
              >
                <span className="num order-2 text-[11px] text-tinta-3 md:order-none md:text-[12px] md:text-tinta-2">
                  {fmtData(e.tradeDate)}
                </span>
                <span className="order-1 text-[14px] font-semibold md:order-none md:text-[13px]">
                  {e.ticker}
                </span>
                <span className="num order-1 ml-auto text-right text-[15px] font-semibold md:order-none md:ml-0 md:text-[13px]">
                  {numero(e.zLog)}
                </span>
                <span className="num order-3 text-right text-[11px] text-tinta-2 md:order-none md:text-[12px]">
                  {multiplo(e.rvol)}
                </span>
                <span
                  className={`num order-3 text-right text-[11px] font-semibold md:order-none md:text-[12px] ${
                    (e.retDay ?? 0) >= 0 ? "text-alta" : "text-baixa"
                  }`}
                >
                  {percentual(e.retDay)}
                </span>
                <span className="num order-4 hidden text-right text-[12px] md:order-none md:block">
                  {numero(e.zExcess)}
                </span>
                <span className="num order-4 hidden text-right text-[12px] text-tinta-2 md:order-none md:block">
                  {reais(e.avgTicket, 0)}
                </span>
                <span className="num order-3 ml-auto text-right text-[11px] md:order-none md:ml-0 md:text-[12px]">
                  {dinheiro(e.volumeFinancial)}
                </span>
              </Link>
            ))}
          </div>
        )}

        {visiveis.length > linhasNaTela && (
          <button
            type="button"
            onClick={() =>
              setLeva({ chave: chaveDosFiltros, linhas: linhasNaTela + LINHAS_POR_VEZ })
            }
            className="toque mt-3 w-full rounded-md border border-linha-2 bg-painel px-4 py-2.5 text-[12px] text-tinta-2 transition-colors hover:text-tinta"
          >
            mostrar mais {Math.min(LINHAS_POR_VEZ, visiveis.length - linhasNaTela)} · faltam{" "}
            <span className="num">{visiveis.length - linhasNaTela}</span>
          </button>
        )}
      </div>
    </>
  );
}
