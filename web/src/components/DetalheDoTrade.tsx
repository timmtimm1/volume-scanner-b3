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
import { fmtR } from "@/lib/backtest-tela";
import { resultadoEmRDoTrade, riscoEmReais } from "@/lib/diario";
import { data as fmtData, percentual } from "@/lib/formato";
import { numeroDoTexto } from "@/lib/lote";
import {
  diaDoMercado,
  linkDaFichaNoMercado,
  numeroDaQuantidade,
  preco,
  precoParaCampo,
  quantidadeExata,
  quantidadeParaCampo,
  regrasDoDiario,
  sufixoDoMercado,
  textos,
  valor,
  type Mercado,
} from "@/lib/mercado";
import { marcarAgora, type TipoDeOperacao } from "@/lib/posicao";
import { precoDeAgora } from "@/lib/preco-de-agora";
import { NOME_NO_DIARIO, ordemNoDiario } from "@/lib/setups-tela";
import { useTema } from "@/lib/tema";
import type { OperacaoDoTrade, SnapshotDoTrade, TradeDetalhe } from "@/lib/trades";
import { useCandleDeHoje } from "@/lib/useCandleDeHoje";
import { ArranjoDaPagina, GradeDeCaixas } from "./OrganizarCaixas";

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

const primeiraMaiuscula = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

/** O resultado por pregao, em area acima/abaixo de zero. */
function GraficoDeResultado({ snapshots, dia }: { snapshots: SnapshotDoTrade[]; dia: string }) {
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
        Ainda sem {dia} marcado para este trade.
      </div>
    );
  }

  return <div ref={alvo} className="h-[220px] w-full md:h-[280px]" />;
}

type CamposDeOperacao = { tipo: TipoDeOperacao; data: string; quantidade: string; preco: string };

function paraCampos(mercado: Mercado, op: OperacaoDoTrade): CamposDeOperacao {
  return {
    tipo: op.tipo,
    data: op.data,
    quantidade: quantidadeParaCampo(mercado, op.quantidade),
    preco: precoParaCampo(mercado, op.preco),
  };
}

/** O numero digitado, ou o proprio texto: o servidor recusa com a mensagem certa. */
const doCampo = (texto: string): number | string => numeroDoTexto(texto) ?? texto;

const campoInput =
  "num toque h-10 rounded-xl border border-linha-2 bg-painel px-2.5 text-[13px] font-bold outline-none focus:border-acento";

/** O detalhe de um trade: cabecalho, grafico de resultado, snapshots e operacoes. */
export function DetalheDoTrade({ inicial }: { inicial: TradeDetalhe }) {
  const router = useRouter();
  const [trade, setTrade] = useState(inicial);
  const mercado = trade.mercado;
  const t = textos(mercado);
  const regras = regrasDoDiario(mercado);
  const sufixo = sufixoDoMercado(mercado);
  const hoje = useCandleDeHoje(trade.ticker, mercado);
  const diaDeHoje = diaDoMercado(mercado, new Date());

  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [campos, setCampos] = useState<CamposDeOperacao | null>(null);
  const [ocupado, setOcupado] = useState<number | "nova" | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const [novaAberta, setNovaAberta] = useState(false);
  const [novosCampos, setNovosCampos] = useState<CamposDeOperacao>({
    tipo: "compra",
    data: diaDeHoje,
    quantidade: "",
    preco: "",
  });

  const aberto = trade.encerradoEm === null;
  const precoInfo = aberto ? precoDeAgora(hoje, trade.ultimoSnapshot, diaDeHoje) : null;
  const marca = marcarAgora(trade, aberto ? (precoInfo?.preco ?? null) : null);
  const emAberto = marca.resultado - trade.realizado;
  const emR = resultadoEmRDoTrade(trade, aberto ? (precoInfo?.preco ?? null) : null);
  const risco = riscoEmReais(trade);
  // Venda a descoberto: a posicao fica negativa; na tela mostramos sempre o tamanho (absoluto).
  const vendido = trade.lado === "venda";
  const taxaDoFuturo = vendido && regras.vendido ? regras.vendido.taxa : null;
  const textoDaTaxaDoFuturo =
    taxaDoFuturo === null
      ? null
      : `Nos futuros, ${(taxaDoFuturo * 100).toLocaleString("pt-BR")}% de taxa sai em dólar a cada venda e recompra.`;
  const rotuloDaOperacao = (tipo: TipoDeOperacao) =>
    tipo === "venda" ? "Venda" : vendido ? "Recompra" : "Compra";

  const [editandoDiario, setEditandoDiario] = useState(false);
  const [setupForm, setSetupForm] = useState("");
  const [stopForm, setStopForm] = useState("");
  const [salvandoDiario, setSalvandoDiario] = useState(false);
  const [erroDiario, setErroDiario] = useState<string | null>(null);

  function abrirDiario() {
    setSetupForm(trade.categoriaSetup ?? "");
    setStopForm(trade.stop === null ? "" : precoParaCampo(mercado, trade.stop));
    setErroDiario(null);
    setEditandoDiario(true);
  }

  async function salvarDiario() {
    setSalvandoDiario(true);
    setErroDiario(null);
    try {
      const texto = stopForm.trim();
      const r = await fetch(`/api/trades/${trade.id}/${sufixo}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          categoriaSetup: setupForm === "" ? null : setupForm,
          // Texto que nao e numero segue como esta: o servidor recusa com a mensagem certa.
          stop: texto === "" ? null : (numeroDoTexto(texto) ?? texto),
        }),
      });
      const corpo = (await r.json().catch(() => null)) as { trade?: TradeDetalhe; erro?: string } | null;
      if (!r.ok || !corpo?.trade) throw new Error(corpo?.erro ?? "não foi possível salvar");
      setTrade(corpo.trade);
      setEditandoDiario(false);
    } catch (e) {
      setErroDiario(e instanceof Error ? e.message : "algo deu errado");
    } finally {
      setSalvandoDiario(false);
    }
  }

  function abrirNova() {
    setNovaAberta(true);
    setNovosCampos({
      tipo: "compra",
      data: diaDeHoje,
      quantidade: "",
      preco: precoInfo ? precoParaCampo(mercado, precoInfo.preco) : "",
    });
    setErro(null);
  }

  async function enviarNova() {
    setOcupado("nova");
    setErro(null);
    try {
      const r = await fetch(`/api/trades/operacoes/${sufixo}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: trade.ticker,
          tipo: novosCampos.tipo,
          data: novosCampos.data,
          quantidade: doCampo(novosCampos.quantidade),
          preco: doCampo(novosCampos.preco),
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
    setCampos(paraCampos(mercado, op));
    setErro(null);
  }

  async function salvarEdicao(id: number) {
    if (!campos) return;
    setOcupado(id);
    setErro(null);
    try {
      const r = await fetch(`/api/trades/operacoes/${id}/${sufixo}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tipo: campos.tipo,
          data: campos.data,
          quantidade: doCampo(campos.quantidade),
          preco: doCampo(campos.preco),
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
      const r = await fetch(`/api/trades/operacoes/${id}/${sufixo}`, { method: "DELETE" });
      const corpo = (await r.json().catch(() => null)) as
        | { apagado?: boolean; trade?: TradeDetalhe | null; erro?: string }
        | null;
      if (!r.ok || !corpo?.apagado) throw new Error(corpo?.erro ?? "não foi possível apagar");
      // `trade` volta null quando a operacao apagada era a ultima do trade --
      // o trade inteiro some junto, e nao ha mais nada para mostrar aqui.
      if (!corpo.trade) {
        router.push(`/trades${sufixo}`);
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

  const caixaResultado = (
    <section className="cartao flex flex-col gap-3 p-4 md:p-5">
      <h2 className="text-[16px] font-extrabold">Resultado por {t.dia[0]}</h2>
      <GraficoDeResultado snapshots={trade.snapshots} dia={t.dia[0]} />
    </section>
  );

  const caixaPregoes = (
    <section className="cartao flex flex-col gap-3 p-4 md:p-5">
      <h2 className="text-[16px] font-extrabold">{primeiraMaiuscula(t.dia[1])} marcados</h2>
      <div className="overflow-x-auto">
        {/* No celular sai Acoes e Valor: com as cinco colunas, Resultado -- o numero
            que interessa -- ficava escondido atras da rolagem horizontal. */}
        <table className="w-full border-collapse text-[13px] sm:min-w-[480px]">
          <thead>
            <tr className="text-left">
              <th className="rotulo pb-2 pr-3 font-bold">{primeiraMaiuscula(t.dia[0])}</th>
              <th className="rotulo hidden pb-2 pr-3 text-right font-bold sm:table-cell">{t.unidades}</th>
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
                  {numeroDaQuantidade(mercado, Math.abs(s.quantidade))}
                </td>
                <td className="num py-2 pr-3 text-right">
                  {preco(mercado, s.fechamento)}
                  {s.semNegocio && (
                    <span className="block text-[10px] font-semibold text-tinta-3">sem negócio</span>
                  )}
                </td>
                <td className="num hidden py-2 pr-3 text-right sm:table-cell">
                  {valor(mercado, Math.abs(s.valorPosicao))}
                </td>
                <td
                  className={`num py-2 text-right font-bold ${
                    s.resultado >= 0 ? "text-alta" : "text-baixa"
                  }`}
                >
                  {valor(mercado, s.resultado)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );

  const caixaOperacoes = (
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
          {regras.vendido
            ? "Trade encerrado: uma nova compra ou venda abre outro trade."
            : "Trade encerrado: uma nova compra abre outro trade."}
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
                {rotuloDaOperacao(tipo)}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <label className="flex flex-col gap-1">
              <span className="rotulo">Data</span>
              <input
                type="date"
                value={novosCampos.data}
                max={diaDeHoje}
                onChange={(e) => setNovosCampos((c) => ({ ...c, data: e.target.value }))}
                className={campoInput}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="flex items-center justify-between gap-2">
                <span className="rotulo">Quantidade</span>
                {novosCampos.tipo === (vendido ? "compra" : "venda") && (
                  <button
                    type="button"
                    onClick={() =>
                      setNovosCampos((c) => ({
                        ...c,
                        quantidade: quantidadeParaCampo(mercado, Math.abs(trade.quantidade)),
                      }))
                    }
                    className="toque text-[11px] font-bold text-acento hover:underline"
                  >
                    tudo
                  </button>
                )}
              </span>
              <input
                type="text"
                inputMode={regras.casasDaQuantidade > 0 ? "decimal" : "numeric"}
                value={novosCampos.quantidade}
                onChange={(e) => setNovosCampos((c) => ({ ...c, quantidade: e.target.value }))}
                placeholder={regras.casasDaQuantidade > 0 ? "0,0153" : "100"}
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
          {textoDaTaxaDoFuturo ? (
            <p className="text-[11px] font-semibold text-tinta-3">{textoDaTaxaDoFuturo}</p>
          ) : (
            !vendido && novosCampos.tipo === "venda" && regras.taxa > 0 && (
            <p className="text-[11px] font-semibold text-tinta-3">
              Na venda, {(regras.taxa * 100).toLocaleString("pt-BR")}% sai dos dólares recebidos. Se a
              corretora deixar um resto pequeno demais para vender, use “tudo” para fechar o trade.
            </p>
            )
          )}
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
                      {rotuloDaOperacao(tipo)}
                    </button>
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  <label className="flex flex-col gap-1">
                    <span className="rotulo">Data</span>
                    <input
                      type="date"
                      value={campos.data}
                      max={diaDeHoje}
                      onChange={(e) => setCampos((c) => (c ? { ...c, data: e.target.value } : c))}
                      className={campoInput}
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="rotulo">Quantidade</span>
                    <input
                      type="text"
                      inputMode={regras.casasDaQuantidade > 0 ? "decimal" : "numeric"}
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
                  {rotuloDaOperacao(op.tipo)}
                </span>
                <span className="num text-[13px] font-semibold text-tinta-2">
                  {quantidadeExata(mercado, op.quantidade)} × {preco(mercado, op.preco)}
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
                  depois: {quantidadeExata(mercado, Math.abs(op.quantidadeApos))} · PM{" "}
                  {preco(mercado, op.precoMedioApos)} · realizado {valor(mercado, op.realizadoApos)}
                </span>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <Link
                href={linkDaFichaNoMercado(mercado, trade.ticker)}
                className="text-[24px] font-extrabold leading-none tracking-tight transition-colors hover:text-acento"
              >
                {trade.ticker}
              </Link>
              {vendido && (
                <span className="rounded-md bg-painel-2 px-2 py-0.5 text-[11px] font-extrabold uppercase text-tinta-2">
                  Vendido
                </span>
              )}
            </div>
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
              {valor(mercado, marca.resultado)}
            </span>
            <span
              className={`num text-[13px] font-bold ${marca.resultado >= 0 ? "text-alta" : "text-baixa"}`}
            >
              {percentual(marca.resultadoPct)}
            </span>
            <span
              className={`num text-[13px] font-bold ${
                emR === null ? "text-tinta-3" : emR >= 0 ? "text-alta" : "text-baixa"
              }`}
            >
              {emR === null ? "— em R" : fmtR(emR)}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
          <div className="flex flex-col gap-1 rounded-2xl bg-painel-2 p-3">
            <span className="text-[11px] font-bold text-tinta-3">Quantidade</span>
            <span className="num text-[16px] font-extrabold">
              {quantidadeExata(mercado, Math.abs(trade.quantidade))}
            </span>
          </div>
          <div className="flex flex-col gap-1 rounded-2xl bg-painel-2 p-3">
            <span className="text-[11px] font-bold text-tinta-3">
              {vendido ? "Preço médio de venda" : "Preço médio"}
            </span>
            <span className="num text-[16px] font-extrabold">{preco(mercado, trade.precoMedio)}</span>
          </div>
          <div className="flex flex-col gap-1 rounded-2xl bg-painel-2 p-3">
            <span className="text-[11px] font-bold text-tinta-3">
              {vendido ? "Valor vendido" : "Custo"}
            </span>
            <span className="num text-[16px] font-extrabold">{valor(mercado, trade.custoComprado)}</span>
          </div>
          {precoInfo && (
            <div className="flex flex-col gap-1 rounded-2xl bg-painel-2 p-3">
              <span className="text-[11px] font-bold text-tinta-3">{precoInfo.rotulo}</span>
              <span className="num text-[16px] font-extrabold">{preco(mercado, precoInfo.preco)}</span>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between text-[12px] font-semibold text-tinta-3">
          <span>
            realizado <strong className="num text-tinta-2">{valor(mercado, trade.realizado)}</strong>
          </span>
          <span>
            em aberto <strong className="num text-tinta-2">{valor(mercado, emAberto)}</strong>
          </span>
        </div>

        {textoDaTaxaDoFuturo && (
          <p className="text-[12px] font-semibold text-tinta-3">{textoDaTaxaDoFuturo}</p>
        )}
        {!vendido && regras.taxa > 0 && (
          <p className="text-[12px] font-semibold text-tinta-3">
            Com a taxa de {(regras.taxa * 100).toLocaleString("pt-BR")}% da Binance: na compra ela sai da
            moeda (a quantidade é a que fica na conta) e o preço médio já a inclui; na venda, sai dos
            dólares.
          </p>
        )}

        <div className="flex flex-col gap-2.5 rounded-2xl bg-painel-2 p-3.5">
          {editandoDiario ? (
            <>
              <div className="grid grid-cols-2 gap-2.5">
                <label className="flex min-w-0 flex-col gap-1">
                  <span className="rotulo">Setup</span>
                  <select
                    value={setupForm}
                    onChange={(e) => setSetupForm(e.target.value)}
                    className="toque h-10 w-full min-w-0 rounded-xl border border-linha-2 bg-painel px-2.5 text-[13px] font-bold outline-none focus:border-acento"
                  >
                    <option value="">Sem setup</option>
                    {ordemNoDiario(regras.categoriasDoEstudo).map((c) => (
                      <option key={c} value={c}>
                        {NOME_NO_DIARIO[c]}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex min-w-0 flex-col gap-1">
                  <span className="rotulo">Stop</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={stopForm}
                    onChange={(e) => setStopForm(e.target.value)}
                    placeholder="0,00"
                    className={campoInput}
                  />
                </label>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={salvarDiario}
                  disabled={salvandoDiario}
                  className="toque h-10 flex-1 rounded-full bg-primario text-[13px] font-bold text-primario-tinta disabled:opacity-40"
                >
                  {salvandoDiario ? "Salvando…" : "Salvar"}
                </button>
                <button
                  type="button"
                  onClick={() => setEditandoDiario(false)}
                  className="toque h-10 rounded-full px-4 text-[13px] font-bold text-tinta-3 hover:text-tinta"
                >
                  Cancelar
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12px] font-semibold text-tinta-3">
                <span>
                  setup{" "}
                  <strong className="text-[13px] text-tinta">
                    {trade.categoriaSetup ? NOME_NO_DIARIO[trade.categoriaSetup] : "sem setup"}
                  </strong>
                </span>
                <span>
                  stop{" "}
                  <strong className="num text-[13px] text-tinta">
                    {trade.stop === null ? "—" : preco(mercado, trade.stop)}
                  </strong>
                </span>
                <span>
                  risco{" "}
                  <strong className="num text-[13px] text-tinta">
                    {risco === null ? "—" : valor(mercado, risco)}
                  </strong>
                </span>
                <button
                  type="button"
                  onClick={abrirDiario}
                  className="toque ml-auto flex h-8 items-center rounded-full px-3 text-[11px] font-bold text-tinta-2 transition-colors hover:bg-linha hover:text-tinta"
                >
                  Editar
                </button>
              </div>
              {emR === null && (
                <p className="text-[12px] font-semibold text-tinta-3">
                  {trade.stop === null
                    ? "Defina o stop para ver o resultado em R."
                    : vendido
                      ? "Com esse stop o R não fecha: o stop precisa estar acima do preço da venda."
                      : "Com esse stop o R não fecha: ele precisa ficar abaixo do preço de todas as compras."}
                </p>
              )}
              {emR !== null && (
                <p className="text-[12px] font-semibold text-tinta-3">
                  R é o resultado dividido pelo risco: +1 R é ganhar o que se arriscava, −1 R é perder.
                </p>
              )}
            </>
          )}
          {erroDiario && <p className="text-[12px] font-semibold text-baixa">{erroDiario}</p>}
        </div>
      </section>

      {/* O cabecalho acima fica fixo; o Organizar muda a ordem do resto. */}
      <ArranjoDaPagina pagina="trade">
        <GradeDeCaixas
          caixas={{ resultado: caixaResultado, pregoes: caixaPregoes, operacoes: caixaOperacoes }}
        />
      </ArranjoDaPagina>
    </div>
  );
}
