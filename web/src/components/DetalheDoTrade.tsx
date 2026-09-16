"use client";

import {
  BaselineSeries,
  ColorType,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { diaNaB3 } from "@/lib/candle-de-hoje";
import { data as fmtData, numero, percentual, reais } from "@/lib/formato";
import { marcarAgora, type TipoDeOperacao } from "@/lib/posicao";
import { precoDeAgora } from "@/lib/preco-de-agora";
import { useTema } from "@/lib/tema";
import type { OperacaoDoTrade, SnapshotDoTrade, TradeDetalhe } from "@/lib/trades";
import { useCandleDeHoje } from "@/lib/useCandleDeHoje";

// Mesmas cores fixas de alta/baixa do Grafico.tsx (SERIE.alta/baixa). Nao
// importadas de la porque o Grafico nao as exporta -- e as duas telas usam
// bibliotecas de grafico diferentes o bastante (candle vs baseline) para nao
// valer a pena acoplar por causa de duas cores.
const RESULTADO_ALTA = "#0E9F6E";
const RESULTADO_BAIXA = "#E0474C";

/** Mesmo helper de superficie do Grafico.tsx: le as cores do tema do CSS. */
function coresDaSuperficie() {
  const estilo = getComputedStyle(document.documentElement);
  const ler = (nome: string, reserva: string) => estilo.getPropertyValue(nome).trim() || reserva;
  return {
    fundo: ler("--painel", "#ffffff"),
    texto: ler("--tinta-3", "#666985"),
    grade: ler("--linha", "#e6e7f0"),
  };
}

/** O resultado por pregao, em area acima/abaixo de zero. */
function GraficoDeResultado({ snapshots }: { snapshots: SnapshotDoTrade[] }) {
  const { tema } = useTema();
  const alvo = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!alvo.current || snapshots.length === 0) return;
    const sup = coresDaSuperficie();
    const c = createChart(alvo.current, {
      layout: {
        background: { type: ColorType.Solid, color: sup.fundo },
        textColor: sup.texto,
        fontFamily: "var(--fonte-sans), system-ui, sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { color: sup.grade }, horzLines: { color: sup.grade } },
      rightPriceScale: { borderColor: sup.grade },
      timeScale: { borderColor: sup.grade, rightOffset: 3, fixLeftEdge: true },
      autoSize: true,
    });
    chart.current = c;

    const serie = c.addSeries(BaselineSeries, {
      baseValue: { type: "price", price: 0 },
      topLineColor: RESULTADO_ALTA,
      topFillColor1: RESULTADO_ALTA + "33",
      topFillColor2: RESULTADO_ALTA + "05",
      bottomLineColor: RESULTADO_BAIXA,
      bottomFillColor1: RESULTADO_BAIXA + "05",
      bottomFillColor2: RESULTADO_BAIXA + "33",
      lineWidth: 2,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    serie.setData(snapshots.map((s) => ({ time: s.data as Time, value: s.resultado })));
    c.timeScale().fitContent();

    return () => {
      c.remove();
      chart.current = null;
    };
  }, [snapshots]);

  // Superficie acompanha o tema sem reconstruir o grafico, igual ao Grafico.tsx.
  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    const sup = coresDaSuperficie();
    c.applyOptions({
      layout: { background: { type: ColorType.Solid, color: sup.fundo }, textColor: sup.texto },
      grid: { vertLines: { color: sup.grade }, horzLines: { color: sup.grade } },
      rightPriceScale: { borderColor: sup.grade },
      timeScale: { borderColor: sup.grade },
    });
  }, [tema, snapshots]);

  if (snapshots.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-linha-2 p-6 text-center text-[13px] text-tinta-3">
        Ainda sem pregão marcado para este trade.
      </div>
    );
  }

  return <div ref={alvo} className="h-[220px] w-full md:h-[280px]" />;
}

type CamposDeOperacao = { tipo: TipoDeOperacao; data: string; quantidade: string; preco: string };

function paraCampos(op: OperacaoDoTrade): CamposDeOperacao {
  return { tipo: op.tipo, data: op.data, quantidade: String(op.quantidade), preco: String(op.preco) };
}

const campoInput =
  "num toque h-10 rounded-xl border border-linha-2 bg-painel px-2.5 text-[13px] font-bold outline-none focus:border-acento";

/** O detalhe de um trade: cabecalho, grafico de resultado, snapshots e operacoes. */
export function DetalheDoTrade({ inicial }: { inicial: TradeDetalhe }) {
  const router = useRouter();
  const [trade, setTrade] = useState(inicial);
  const hoje = useCandleDeHoje(trade.ticker);

  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [campos, setCampos] = useState<CamposDeOperacao | null>(null);
  const [ocupado, setOcupado] = useState<number | "nova" | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const [novaAberta, setNovaAberta] = useState(false);
  const [novosCampos, setNovosCampos] = useState<CamposDeOperacao>({
    tipo: "compra",
    data: diaNaB3(new Date()),
    quantidade: "",
    preco: "",
  });

  const aberto = trade.encerradoEm === null;
  const precoInfo = aberto ? precoDeAgora(hoje, trade.ultimoSnapshot) : null;
  const marca = marcarAgora(trade, aberto ? (precoInfo?.preco ?? null) : null);
  const emAberto = marca.resultado - trade.realizado;

  function abrirNova() {
    setNovaAberta(true);
    setNovosCampos({
      tipo: "compra",
      data: diaNaB3(new Date()),
      quantidade: "",
      preco: precoInfo ? precoInfo.preco.toFixed(2) : "",
    });
    setErro(null);
  }

  async function enviarNova() {
    setOcupado("nova");
    setErro(null);
    try {
      const r = await fetch("/api/trades/operacoes/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: trade.ticker,
          tipo: novosCampos.tipo,
          data: novosCampos.data,
          quantidade: Number(novosCampos.quantidade),
          preco: Number(novosCampos.preco.replace(",", ".")),
        }),
      });
      const corpo = (await r.json().catch(() => null)) as { trade?: TradeDetalhe; erro?: string } | null;
      if (!r.ok || !corpo?.trade) throw new Error(corpo?.erro ?? "não foi possível salvar");
      setTrade(corpo.trade);
      setNovaAberta(false);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "algo deu errado");
    } finally {
      setOcupado(null);
    }
  }

  function iniciarEdicao(op: OperacaoDoTrade) {
    setEditandoId(op.id);
    setCampos(paraCampos(op));
    setErro(null);
  }

  async function salvarEdicao(id: number) {
    if (!campos) return;
    setOcupado(id);
    setErro(null);
    try {
      const r = await fetch(`/api/trades/operacoes/${id}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tipo: campos.tipo,
          data: campos.data,
          quantidade: Number(campos.quantidade),
          preco: Number(campos.preco.replace(",", ".")),
        }),
      });
      const corpo = (await r.json().catch(() => null)) as { trade?: TradeDetalhe; erro?: string } | null;
      if (!r.ok || !corpo?.trade) throw new Error(corpo?.erro ?? "não foi possível salvar");
      setTrade(corpo.trade);
      setEditandoId(null);
      setCampos(null);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "algo deu errado");
    } finally {
      setOcupado(null);
    }
  }

  async function apagar(id: number) {
    if (!window.confirm("Apagar esta operação? Isso recalcula todo o trade.")) return;
    setOcupado(id);
    setErro(null);
    try {
      const r = await fetch(`/api/trades/operacoes/${id}/`, { method: "DELETE" });
      const corpo = (await r.json().catch(() => null)) as
        | { apagado?: boolean; trade?: TradeDetalhe | null; erro?: string }
        | null;
      if (!r.ok || !corpo?.apagado) throw new Error(corpo?.erro ?? "não foi possível apagar");
      // `trade` volta null quando a operacao apagada era a ultima do trade --
      // o trade inteiro some junto, e nao ha mais nada para mostrar aqui.
      if (!corpo.trade) {
        router.push("/trades");
        return;
      }
      setTrade(corpo.trade);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "algo deu errado");
    } finally {
      setOcupado(null);
    }
  }

  const snapshotsRecentePrimeiro = [...trade.snapshots].reverse();

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <Link
              href={`/papel/${trade.ticker}`}
              className="text-[24px] font-extrabold leading-none tracking-tight transition-colors hover:text-acento"
            >
              {trade.ticker}
            </Link>
            <p className="num text-[13px] font-semibold text-tinta-3">
              {aberto
                ? `aberto desde ${fmtData(trade.abertoEm)}`
                : `encerrado em ${fmtData(trade.encerradoEm as string)}`}
            </p>
          </div>
          <div className="flex flex-col items-end gap-0.5">
            <span
              className={`num text-[24px] font-extrabold leading-none ${
                marca.resultado >= 0 ? "text-alta" : "text-baixa"
              }`}
            >
              {reais(marca.resultado)}
            </span>
            <span
              className={`num text-[13px] font-bold ${marca.resultado >= 0 ? "text-alta" : "text-baixa"}`}
            >
              {percentual(marca.resultadoPct)}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
          <div className="flex flex-col gap-1 rounded-2xl bg-painel-2 p-3">
            <span className="text-[11px] font-bold text-tinta-3">Quantidade</span>
            <span className="num text-[16px] font-extrabold">{numero(trade.quantidade, 0)}</span>
          </div>
          <div className="flex flex-col gap-1 rounded-2xl bg-painel-2 p-3">
            <span className="text-[11px] font-bold text-tinta-3">Preço médio</span>
            <span className="num text-[16px] font-extrabold">{reais(trade.precoMedio)}</span>
          </div>
          <div className="flex flex-col gap-1 rounded-2xl bg-painel-2 p-3">
            <span className="text-[11px] font-bold text-tinta-3">Custo</span>
            <span className="num text-[16px] font-extrabold">{reais(trade.custoComprado)}</span>
          </div>
          {precoInfo && (
            <div className="flex flex-col gap-1 rounded-2xl bg-painel-2 p-3">
              <span className="text-[11px] font-bold text-tinta-3">{precoInfo.rotulo}</span>
              <span className="num text-[16px] font-extrabold">{reais(precoInfo.preco)}</span>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between text-[12px] font-semibold text-tinta-3">
          <span>
            realizado <strong className="num text-tinta-2">{reais(trade.realizado)}</strong>
          </span>
          <span>
            em aberto <strong className="num text-tinta-2">{reais(emAberto)}</strong>
          </span>
        </div>
      </section>

      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <h2 className="text-[16px] font-extrabold">Resultado por pregão</h2>
        <GraficoDeResultado snapshots={trade.snapshots} />
      </section>

      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <h2 className="text-[16px] font-extrabold">Pregões marcados</h2>
        <div className="overflow-x-auto">
          {/* No celular sai Acoes e Valor: com as cinco colunas, Resultado -- o numero
              que interessa -- ficava escondido atras da rolagem horizontal. */}
          <table className="w-full border-collapse text-[13px] sm:min-w-[480px]">
            <thead>
              <tr className="text-left">
                <th className="rotulo pb-2 pr-3 font-bold">Pregão</th>
                <th className="rotulo hidden pb-2 pr-3 text-right font-bold sm:table-cell">Ações</th>
                <th className="rotulo pb-2 pr-3 text-right font-bold">Fechou</th>
                <th className="rotulo hidden pb-2 pr-3 text-right font-bold sm:table-cell">Valor</th>
                <th className="rotulo pb-2 text-right font-bold">Resultado</th>
              </tr>
            </thead>
            <tbody>
              {snapshotsRecentePrimeiro.map((s) => (
                <tr key={s.data} className="border-t border-linha">
                  <td className="num py-2 pr-3 font-semibold">{fmtData(s.data)}</td>
                  <td className="num hidden py-2 pr-3 text-right sm:table-cell">
                    {numero(s.quantidade, 0)}
                  </td>
                  <td className="num py-2 pr-3 text-right">
                    {reais(s.fechamento)}
                    {s.semNegocio && (
                      <span className="block text-[10px] font-semibold text-tinta-3">sem negócio</span>
                    )}
                  </td>
                  <td className="num hidden py-2 pr-3 text-right sm:table-cell">
                    {reais(s.valorPosicao)}
                  </td>
                  <td
                    className={`num py-2 text-right font-bold ${
                      s.resultado >= 0 ? "text-alta" : "text-baixa"
                    }`}
                  >
                    {reais(s.resultado)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[16px] font-extrabold">Operações</h2>
          {aberto && !novaAberta && (
            <button
              type="button"
              onClick={abrirNova}
              className="toque h-9 rounded-full bg-primario px-3.5 text-[12px] font-bold text-primario-tinta"
            >
              Nova operação
            </button>
          )}
        </div>

        {!aberto && (
          <p className="text-[12px] font-semibold text-tinta-3">
            Trade encerrado: uma nova compra na ficha do papel abre outro trade.
          </p>
        )}

        {novaAberta && (
          <div className="flex flex-col gap-2.5 rounded-2xl bg-painel-2 p-3.5">
            <div className="flex rounded-xl border border-linha-2 p-0.5">
              {(["compra", "venda"] as const).map((tipo) => (
                <button
                  key={tipo}
                  type="button"
                  onClick={() => setNovosCampos((c) => ({ ...c, tipo }))}
                  aria-pressed={novosCampos.tipo === tipo}
                  className={`toque h-9 flex-1 rounded-[10px] text-[12px] font-bold transition-colors ${
                    novosCampos.tipo === tipo ? "bg-painel text-acento shadow-sm" : "text-tinta-3"
                  }`}
                >
                  {tipo === "compra" ? "Compra" : "Venda"}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <label className="flex flex-col gap-1">
                <span className="rotulo">Data</span>
                <input
                  type="date"
                  value={novosCampos.data}
                  max={diaNaB3(new Date())}
                  onChange={(e) => setNovosCampos((c) => ({ ...c, data: e.target.value }))}
                  className={campoInput}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="rotulo">Quantidade</span>
                <input
                  type="text"
                  inputMode="numeric"
                  value={novosCampos.quantidade}
                  onChange={(e) => setNovosCampos((c) => ({ ...c, quantidade: e.target.value }))}
                  placeholder="100"
                  className={campoInput}
                />
              </label>
              <label className="col-span-2 flex flex-col gap-1">
                <span className="rotulo">Preço</span>
                <input
                  type="text"
                  inputMode="decimal"
                  value={novosCampos.preco}
                  onChange={(e) => setNovosCampos((c) => ({ ...c, preco: e.target.value }))}
                  placeholder="0,00"
                  className={campoInput}
                />
              </label>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={enviarNova}
                disabled={
                  ocupado === "nova" ||
                  novosCampos.quantidade.trim() === "" ||
                  novosCampos.preco.trim() === ""
                }
                className="toque h-10 flex-1 rounded-full bg-primario text-[13px] font-bold text-primario-tinta disabled:opacity-40"
              >
                {ocupado === "nova" ? "Salvando…" : "Confirmar"}
              </button>
              <button
                type="button"
                onClick={() => setNovaAberta(false)}
                className="toque h-10 rounded-full px-4 text-[13px] font-bold text-tinta-3 hover:text-tinta"
              >
                Cancelar
              </button>
            </div>
          </div>
        )}

        {erro && <p className="text-[12px] font-semibold text-baixa">{erro}</p>}

        <ul className="flex flex-col gap-2">
          {trade.operacoes.map((op) => (
            <li key={op.id} className="rounded-2xl bg-painel-2 px-3.5 py-3">
              {editandoId === op.id && campos ? (
                <div className="flex flex-col gap-2.5">
                  <div className="flex rounded-xl border border-linha-2 p-0.5">
                    {(["compra", "venda"] as const).map((tipo) => (
                      <button
                        key={tipo}
                        type="button"
                        onClick={() => setCampos((c) => (c ? { ...c, tipo } : c))}
                        aria-pressed={campos.tipo === tipo}
                        className={`toque h-9 flex-1 rounded-[10px] text-[12px] font-bold transition-colors ${
                          campos.tipo === tipo ? "bg-painel text-acento shadow-sm" : "text-tinta-3"
                        }`}
                      >
                        {tipo === "compra" ? "Compra" : "Venda"}
                      </button>
                    ))}
                  </div>
                  <div className="grid grid-cols-2 gap-2.5">
                    <label className="flex flex-col gap-1">
                      <span className="rotulo">Data</span>
                      <input
                        type="date"
                        value={campos.data}
                        max={diaNaB3(new Date())}
                        onChange={(e) => setCampos((c) => (c ? { ...c, data: e.target.value } : c))}
                        className={campoInput}
                      />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="rotulo">Quantidade</span>
                      <input
                        type="text"
                        inputMode="numeric"
                        value={campos.quantidade}
                        onChange={(e) =>
                          setCampos((c) => (c ? { ...c, quantidade: e.target.value } : c))
                        }
                        className={campoInput}
                      />
                    </label>
                    <label className="col-span-2 flex flex-col gap-1">
                      <span className="rotulo">Preço</span>
                      <input
                        type="text"
                        inputMode="decimal"
                        value={campos.preco}
                        onChange={(e) => setCampos((c) => (c ? { ...c, preco: e.target.value } : c))}
                        className={campoInput}
                      />
                    </label>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => salvarEdicao(op.id)}
                      disabled={ocupado === op.id}
                      className="toque h-10 flex-1 rounded-full bg-primario text-[13px] font-bold text-primario-tinta disabled:opacity-40"
                    >
                      {ocupado === op.id ? "Salvando…" : "Salvar"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setEditandoId(null);
                        setCampos(null);
                      }}
                      className="toque h-10 rounded-full px-4 text-[13px] font-bold text-tinta-3 hover:text-tinta"
                    >
                      Cancelar
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                  <span className="num text-[13px] font-bold">{fmtData(op.data)}</span>
                  <span
                    className={`text-[12px] font-bold ${
                      op.tipo === "compra" ? "text-acento" : "text-tinta-2"
                    }`}
                  >
                    {op.tipo === "compra" ? "Compra" : "Venda"}
                  </span>
                  <span className="num text-[13px] font-semibold text-tinta-2">
                    {numero(op.quantidade, 0)} × {reais(op.preco)}
                  </span>
                  <div className="ml-auto flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => iniciarEdicao(op)}
                      className="toque flex h-8 items-center rounded-full px-3 text-[11px] font-bold text-tinta-2 transition-colors hover:bg-linha hover:text-tinta"
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      onClick={() => apagar(op.id)}
                      disabled={ocupado === op.id}
                      className="toque flex h-8 items-center rounded-full px-3 text-[11px] font-bold text-tinta-2 transition-colors hover:bg-linha hover:text-baixa disabled:opacity-40"
                    >
                      Apagar
                    </button>
                  </div>
                  <span className="num w-full text-[11px] font-semibold text-tinta-3">
                    depois: {numero(op.quantidadeApos, 0)} · PM {reais(op.precoMedioApos)} · realizado{" "}
                    {reais(op.realizadoApos)}
                  </span>
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
