"use client";

/**
 * A tabela da Analise: uma linha por moeda, uma coluna por ano com o quanto a
 * moeda andou a mais (ou a menos) que o Bitcoin. A busca, o grupo e a ordem
 * moram aqui; as contas, em `lib/analise.ts`. O BTC fica sempre no topo, como
 * regua, mostrando o retorno dele mesmo em dolar.
 */

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  BTC,
  corDaCelula,
  filtrarLinhas,
  ordenarLinhas,
  pctCurto,
  type CelulaAnual,
  type ChaveDeOrdem,
  type Grupo,
  type LinhaDaTabela,
  type Sentido,
} from "@/lib/analise";
import { commodityDe } from "@/lib/commodities";
import { data, numero } from "@/lib/formato";

const PASSO = 100;

const GRUPOS: { valor: Grupo; nome: string }[] = [
  { valor: "todas", nome: "Todas" },
  { valor: "negociando", nome: "Negociando hoje" },
  { valor: "top50", nome: "As 50 da aba Cripto" },
];

const igual = (a: ChaveDeOrdem, b: ChaveDeOrdem) => a === b;
const textoDaChave = (c: ChaveDeOrdem) => String(c);
const chaveDoTexto = (t: string): ChaveDeOrdem =>
  t === "volume" || t === "total" || t === "beta" || t === "correlacao" ? t : Number(t);

function dica(c: CelulaAnual, moeda: string): string {
  return `de ${data(c.inicio)} a ${data(c.fim)} · ${moeda} ${pctCurto(c.retorno)} · BTC ${pctCurto(c.retornoBtc)}${
    c.parcial ? " · período incompleto" : ""
  }`;
}

function CelulaDeAno({ c, moeda }: { c: CelulaAnual | null | undefined; moeda: string }) {
  if (!c) return <td className="px-2 py-1.5 text-center font-semibold text-tinta-3">—</td>;
  const eBtc = moeda === BTC;
  const valor = eBtc ? c.retorno : c.relativo;
  if (valor === null || valor === undefined) {
    return <td className="px-2 py-1.5 text-center font-semibold text-tinta-3">—</td>;
  }
  return (
    <td
      title={dica(c, moeda)}
      style={{ background: eBtc ? undefined : corDaCelula(valor, "ano") }}
      className={`num whitespace-nowrap px-2 py-1.5 text-center font-semibold ${
        eBtc ? "text-tinta-2" : "text-tinta"
      } ${c.parcial ? "italic" : ""}`}
    >
      {pctCurto(valor)}
      {c.parcial && "*"}
    </td>
  );
}

export function TabelaDaAnalise({
  anos,
  linhas,
  commodities = false,
}: {
  anos: number[];
  linhas: LinhaDaTabela[];
  /** Na visão de commodities, o nome da commodity aparece ao lado do ticker. */
  commodities?: boolean;
}) {
  const [busca, setBusca] = useState("");
  const [grupo, setGrupo] = useState<Grupo>("todas");
  const [chave, setChave] = useState<ChaveDeOrdem>("volume");
  const [sentido, setSentido] = useState<Sentido>("desc");
  const [limite, setLimite] = useState(PASSO);

  const filtradas = useMemo(() => filtrarLinhas(linhas, { busca, grupo }), [linhas, busca, grupo]);
  const ordenadas = useMemo(
    () => ordenarLinhas(filtradas, chave, sentido),
    [filtradas, chave, sentido],
  );
  const visiveis = ordenadas.slice(0, limite);

  const ordenarPor = (nova: ChaveDeOrdem) => {
    if (igual(nova, chave)) setSentido((s) => (s === "desc" ? "asc" : "desc"));
    else {
      setChave(nova);
      setSentido("desc");
    }
    setLimite(PASSO);
  };

  const cabeca = (
    nova: ChaveDeOrdem,
    nome: string,
    classe = "px-2 py-1.5 text-center",
    titulo?: string,
  ) => {
    const on = igual(nova, chave);
    return (
      <th
        key={textoDaChave(nova)}
        scope="col"
        aria-sort={on ? (sentido === "desc" ? "descending" : "ascending") : "none"}
        className={`font-bold ${classe}`}
      >
        <button
          type="button"
          onClick={() => ordenarPor(nova)}
          title={titulo}
          className={`toque whitespace-nowrap font-bold transition-colors ${
            on ? "text-acento" : "text-tinta-3 hover:text-tinta"
          }`}
        >
          {nome}
          {on && <span aria-hidden>{sentido === "desc" ? " ▾" : " ▴"}</span>}
        </button>
      </th>
    );
  };

  const contagem =
    filtradas.length === linhas.length
      ? `${linhas.length} moedas`
      : `${filtradas.length} de ${linhas.length} moedas`;

  return (
    <section className="cartao flex flex-col gap-3 p-4 md:p-5">
      <div className="flex flex-col gap-2 md:flex-row md:items-center">
        <input
          type="search"
          value={busca}
          onChange={(e) => {
            setBusca(e.target.value);
            setLimite(PASSO);
          }}
          placeholder="Buscar moeda"
          aria-label="Buscar moeda"
          className="toque h-10 min-w-0 rounded-full border border-linha-2 bg-painel px-4 text-[14px] font-semibold text-tinta placeholder:text-tinta-3 md:w-56"
        />
        <div role="group" aria-label="Grupo de moedas" className="flex flex-wrap gap-1.5">
          {GRUPOS.filter((g) => !commodities || g.valor !== "top50").map((g) => (
            <button
              key={g.valor}
              type="button"
              onClick={() => {
                setGrupo(g.valor);
                setLimite(PASSO);
              }}
              aria-pressed={grupo === g.valor}
              className={`toque h-9 rounded-full border px-3.5 text-[12px] font-bold transition-colors md:text-[13px] ${
                grupo === g.valor
                  ? "border-acento bg-selecao text-acento"
                  : "border-linha-2 text-tinta-3 hover:text-tinta"
              }`}
            >
              {g.nome}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 md:ml-auto">
          <label htmlFor="ordem-da-analise" className="rotulo">
            Ordenar
          </label>
          <select
            id="ordem-da-analise"
            value={textoDaChave(chave)}
            onChange={(e) => {
              setChave(chaveDoTexto(e.target.value));
              setSentido("desc");
              setLimite(PASSO);
            }}
            className="toque h-10 min-w-0 flex-1 rounded-xl border border-linha-2 bg-painel px-3 text-[13px] font-bold text-tinta"
          >
            <option value="volume">Mais negociadas</option>
            {anos.map((a) => (
              <option key={a} value={a}>
                {a}: mais fortes
              </option>
            ))}
            <option value="total">Período todo</option>
            <option value="beta">Beta</option>
            <option value="correlacao">Correlação</option>
          </select>
        </div>
      </div>

      <p className="num text-[12px] font-semibold text-tinta-3" aria-live="polite">
        {contagem}
      </p>

      <div className="-mx-4 overflow-x-auto md:-mx-5">
        <table className="w-full border-collapse text-[12px] md:text-[13px]">
          <thead>
            <tr className="border-b border-linha">
              {cabeca(
                "volume",
                "Moeda",
                "sticky left-0 z-10 bg-painel px-3 py-1.5 text-left md:px-4",
                "Ordenar pelas mais negociadas",
              )}
              {anos.map((a) => cabeca(a, String(a)))}
              {cabeca("total", "Período todo")}
              {cabeca("beta", "Beta")}
              {cabeca("correlacao", "Correlação")}
            </tr>
          </thead>
          <tbody className="divide-y divide-linha">
            {visiveis.map((l) => {
              const eBtc = l.moeda === BTC;
              return (
                <tr key={l.moeda} className={eBtc ? "bg-painel-2" : undefined}>
                  <th
                    scope="row"
                    className={`sticky left-0 z-10 whitespace-nowrap px-3 py-1.5 text-left font-extrabold md:px-4 ${
                      eBtc ? "bg-painel-2" : "bg-painel"
                    }`}
                  >
                    <Link
                      href={`/analise/${encodeURIComponent(l.moeda)}`}
                      className="text-tinta hover:text-acento"
                    >
                      {eBtc ? "BTC (régua)" : l.moeda}
                    </Link>
                    {commodities && !eBtc && (
                      <span className="ml-1.5 text-[11px] font-semibold text-tinta-3">
                        {commodityDe(l.moeda)?.nome}
                      </span>
                    )}
                    {!l.negociando && (
                      <span
                        title="Esta moeda não é mais negociada na Binance"
                        className="ml-1.5 rounded-md bg-painel-2 px-1.5 py-0.5 text-[10px] font-extrabold text-tinta-3"
                      >
                        parada
                      </span>
                    )}
                  </th>
                  {anos.map((a) => (
                    <CelulaDeAno key={a} c={l.porAno[a]} moeda={l.moeda} />
                  ))}
                  <CelulaDeAno c={l.total} moeda={l.moeda} />
                  <td className="num px-2 py-1.5 text-center font-semibold">
                    {l.total?.beta == null ? <span className="text-tinta-3">—</span> : numero(l.total.beta, 2)}
                  </td>
                  <td className="num px-2 py-1.5 text-center font-semibold">
                    {l.total?.correlacao == null ? (
                      <span className="text-tinta-3">—</span>
                    ) : (
                      numero(l.total.correlacao, 2)
                    )}
                  </td>
                </tr>
              );
            })}
            {visiveis.length === 0 && (
              <tr>
                <td colSpan={anos.length + 4} className="p-6 text-center text-[13px] font-semibold text-tinta-3">
                  Nenhuma moeda com esse filtro.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {ordenadas.length > limite && (
        <button
          type="button"
          onClick={() => setLimite((n) => n + PASSO)}
          className="toque h-11 self-center rounded-full border border-linha-2 px-5 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
        >
          Mostrar mais {PASSO}
        </button>
      )}
    </section>
  );
}
