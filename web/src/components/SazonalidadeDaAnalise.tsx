"use client";

/**
 * A tabela de sazonalidade: uma linha por moeda, uma coluna por mes do
 * calendario, com a mediana do mes ao longo dos anos. As duas primeiras linhas
 * ficam fixas: o Mercado (a moeda tipica) e o BTC (a regua). As contas moram em
 * `lib/analise.ts`.
 */

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  BTC,
  MINIMO_DE_ANOS,
  corDaCelula,
  filtrarLinhas,
  ordenarSazonalidade,
  pctCurto,
  type CelulaSazonal,
  type ChaveSazonal,
  type Grupo,
  type LinhaSazonal,
  type ModoSazonal,
  type Sentido,
} from "@/lib/analise";
import { commodityDe } from "@/lib/commodities";

const PASSO = 100;

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

const MODOS: { valor: ModoSazonal; nome: string }[] = [
  { valor: "retorno", nome: "Em dólar" },
  { valor: "relativo", nome: "Contra o BTC" },
];

const GRUPOS: { valor: Grupo; nome: string }[] = [
  { valor: "todas", nome: "Todas" },
  { valor: "negociando", nome: "Negociando hoje" },
  { valor: "top50", nome: "As 50 da aba Cripto" },
];

const textoDaChave = (c: ChaveSazonal) => String(c);
const chaveDoTexto = (t: string): ChaveSazonal => (t === "volume" ? "volume" : Number(t));

function Celula({ c, modo }: { c: CelulaSazonal | null | undefined; modo: ModoSazonal }) {
  const vazia = <td className="px-2 py-1.5 text-center font-semibold text-tinta-3">—</td>;
  if (!c) return vazia;
  const valor = c[modo];
  if (valor === null || valor === undefined) return vazia;
  const quantos = modo === "retorno" ? c.subiu : c.ganhou;
  const pouco = c.anos < MINIMO_DE_ANOS;
  const verbo = modo === "retorno" ? "subiu" : "ganhou do BTC";
  return (
    <td
      title={`${c.anos} ${c.anos === 1 ? "ano" : "anos"} com o mês completo · ${verbo} em ${quantos}${
        pouco ? " · poucos anos para tirar conclusão" : ""
      }`}
      style={{ background: pouco ? undefined : corDaCelula(valor, "mes") }}
      className={`num whitespace-nowrap px-2 py-1 text-center font-semibold ${
        pouco ? "text-tinta-3" : "text-tinta"
      }`}
    >
      <div>{pctCurto(valor)}</div>
      <div className={`text-[10px] font-semibold leading-tight ${pouco ? "" : "text-tinta-2"}`}>
        {quantos}/{c.anos}
      </div>
    </td>
  );
}

export function SazonalidadeDaAnalise({
  linhas,
  mercado,
  commodities = false,
}: {
  linhas: LinhaSazonal[];
  mercado: Record<number, CelulaSazonal>;
  /** Na visão de commodities não há moeda típica, e o nome vem ao lado do ticker. */
  commodities?: boolean;
}) {
  const [modo, setModo] = useState<ModoSazonal>("retorno");
  const [busca, setBusca] = useState("");
  const [grupo, setGrupo] = useState<Grupo>("todas");
  const [chave, setChave] = useState<ChaveSazonal>("volume");
  const [sentido, setSentido] = useState<Sentido>("desc");
  const [limite, setLimite] = useState(PASSO);

  const btc = useMemo(() => linhas.find((l) => l.moeda === BTC) ?? null, [linhas]);
  const filtradas = useMemo(() => filtrarLinhas(linhas, { busca, grupo }), [linhas, busca, grupo]);
  const ordenadas = useMemo(
    () => ordenarSazonalidade(filtradas, chave, modo, sentido).filter((l) => l.moeda !== BTC),
    [filtradas, chave, modo, sentido],
  );
  const visiveis = ordenadas.slice(0, limite);

  const ordenarPor = (nova: ChaveSazonal) => {
    if (nova === chave) setSentido((s) => (s === "desc" ? "asc" : "desc"));
    else {
      setChave(nova);
      setSentido("desc");
    }
    setLimite(PASSO);
  };

  const contagem =
    filtradas.length === linhas.length
      ? `${linhas.length} moedas`
      : `${filtradas.length} de ${linhas.length} moedas`;

  const temMercado = Object.keys(mercado).length > 0;
  const qualEmCima = modo === "retorno" ? "subiu" : "ganhou do BTC";

  return (
    <section className="cartao flex flex-col gap-3 p-4 md:p-5">
      {/* Uma frase a vista e o resto recolhido: aberta, a explicacao ocupava a
          tela inteira do celular antes da tabela. */}
      <div className="flex flex-col gap-1.5 text-[13px] leading-relaxed text-tinta-2">
        <p>
          Cada célula é a <b className="text-tinta">mediana</b> daquele mês em todos os anos; o
          número pequeno diz em quantos deles o mês {qualEmCima}.
        </p>
        <details className="group">
          <summary className="toque flex cursor-pointer list-none items-center text-[13px] font-bold text-acento [&::-webkit-details-marker]:hidden">
            Como ler
            <span aria-hidden className="ml-1.5 transition-transform group-open:rotate-90">
              ›
            </span>
          </summary>
          <div className="flex flex-col gap-2 pt-1">
            <p>
              A mediana é o mês do meio de todos os anos em que o mês estava completo: um ano maluco
              não puxa a conta. Com menos de {MINIMO_DE_ANOS} anos, a célula fica cinza e a moeda vai
              para o fim da ordem: é pouco para falar em estação.
            </p>
            {temMercado ? (
              <p>
                A linha <b className="text-tinta">Mercado</b> é a moeda típica de cada mês (a mediana
                entre todas as moedas naquele mês), com cada ano pesando igual. A moeda típica perde em
                quase todos os meses: a maioria das moedas cai com o tempo. Compare cada moeda com a
                linha do Mercado e com a do BTC. É o que aconteceu no passado, não uma previsão.
              </p>
            ) : (
              <p>
                Compare cada commodity com a linha do BTC. É o que aconteceu no passado, não uma
                previsão.
              </p>
            )}
          </div>
        </details>
      </div>

      <div className="flex flex-col gap-2 md:flex-row md:flex-wrap md:items-center">
        <div role="group" aria-label="Medida" className="flex flex-wrap gap-1.5">
          {MODOS.map((m) => (
            <button
              key={m.valor}
              type="button"
              onClick={() => setModo(m.valor)}
              aria-pressed={modo === m.valor}
              className={`toque h-9 rounded-full border px-3.5 text-[12px] font-bold transition-colors md:text-[13px] ${
                modo === m.valor
                  ? "border-acento bg-selecao text-acento"
                  : "border-linha-2 text-tinta-3 hover:text-tinta"
              }`}
            >
              {m.nome}
            </button>
          ))}
        </div>
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
          <label htmlFor="ordem-da-sazonalidade" className="rotulo">
            Ordenar
          </label>
          <select
            id="ordem-da-sazonalidade"
            value={textoDaChave(chave)}
            onChange={(e) => {
              setChave(chaveDoTexto(e.target.value));
              setSentido("desc");
              setLimite(PASSO);
            }}
            className="toque h-10 min-w-0 flex-1 rounded-xl border border-linha-2 bg-painel px-3 text-[13px] font-bold text-tinta"
          >
            <option value="volume">Mais negociadas</option>
            {MESES.map((nome, i) => (
              <option key={nome} value={i + 1}>
                Melhores em {nome}
              </option>
            ))}
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
              <th
                scope="col"
                aria-sort={chave === "volume" ? (sentido === "desc" ? "descending" : "ascending") : "none"}
                className="sticky left-0 z-10 bg-painel px-3 py-1.5 text-left font-bold md:px-4"
              >
                <button
                  type="button"
                  onClick={() => ordenarPor("volume")}
                  title="Ordenar pelas mais negociadas"
                  className={`toque whitespace-nowrap font-bold transition-colors ${
                    chave === "volume" ? "text-acento" : "text-tinta-3 hover:text-tinta"
                  }`}
                >
                  Moeda
                  {chave === "volume" && <span aria-hidden>{sentido === "desc" ? " ▾" : " ▴"}</span>}
                </button>
              </th>
              {MESES.map((nome, i) => {
                const on = chave === i + 1;
                return (
                  <th
                    key={nome}
                    scope="col"
                    aria-sort={on ? (sentido === "desc" ? "descending" : "ascending") : "none"}
                    className="px-2 py-1.5 text-center font-bold"
                  >
                    <button
                      type="button"
                      onClick={() => ordenarPor(i + 1)}
                      title={`Ordenar pelo mês de ${nome}`}
                      className={`toque whitespace-nowrap font-bold transition-colors ${
                        on ? "text-acento" : "text-tinta-3 hover:text-tinta"
                      }`}
                    >
                      {nome}
                      {on && <span aria-hidden>{sentido === "desc" ? " ▾" : " ▴"}</span>}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-linha">
            {temMercado && (
              <tr className="bg-painel-2">
                <th
                  scope="row"
                  title="A moeda típica de cada mês: a mediana entre todas as moedas, sem o BTC"
                  className="sticky left-0 z-10 whitespace-nowrap bg-painel-2 px-3 py-1.5 text-left font-extrabold md:px-4"
                >
                  Mercado (moeda típica)
                </th>
                {MESES.map((nome, i) => (
                  <Celula key={nome} c={mercado[i + 1]} modo={modo} />
                ))}
              </tr>
            )}
            {btc && (
              <tr className="bg-painel-2">
                <th
                  scope="row"
                  className="sticky left-0 z-10 whitespace-nowrap bg-painel-2 px-3 py-1.5 text-left font-extrabold md:px-4"
                >
                  <Link href={`/analise/${encodeURIComponent(BTC)}`} className="text-tinta hover:text-acento">
                    {BTC}
                  </Link>
                </th>
                {MESES.map((nome, i) =>
                  modo === "relativo" ? (
                    <td key={nome} className="px-2 py-1.5 text-center font-semibold text-tinta-3">
                      —
                    </td>
                  ) : (
                    <Celula key={nome} c={btc.porMes[i + 1]} modo={modo} />
                  ),
                )}
              </tr>
            )}
            {visiveis.map((l) => (
              <tr key={l.moeda}>
                <th
                  scope="row"
                  className="sticky left-0 z-10 whitespace-nowrap bg-painel px-3 py-1.5 text-left font-extrabold md:px-4"
                >
                  <Link
                    href={`/analise/${encodeURIComponent(l.moeda)}`}
                    className="text-tinta hover:text-acento"
                  >
                    {l.moeda}
                  </Link>
                  {commodities && (
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
                {MESES.map((nome, i) => (
                  <Celula key={nome} c={l.porMes[i + 1]} modo={modo} />
                ))}
              </tr>
            ))}
            {visiveis.length === 0 && (
              <tr>
                <td colSpan={13} className="p-6 text-center text-[13px] font-semibold text-tinta-3">
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
