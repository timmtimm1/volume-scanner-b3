import Link from "next/link";
import {
  type Ano,
  comoSaiu,
  type Escolha,
  fmtIntervalo,
  fmtNumero,
  fmtPct,
  fmtR,
  fmtVolume,
  GRUPOS,
  linkDaSelecao,
  linkDoTrade,
  MOTIVOS,
  ORDEM_DAS_SAIDAS,
  ORDEM_DOS_GRUPOS,
  PERIODOS,
  type PontoDaCurva,
  type Resultado,
  ROTULO_DO_PERIODO,
  SAIDAS,
  type Selecao,
  SETUPS,
  type TradeDoBacktest,
  volumeAlto,
} from "@/lib/backtest-tela";
import { data, reais } from "@/lib/formato";
import { AnosDoBacktest } from "./AnosDoBacktest";
import { CurvaDoBacktest } from "./CurvaDoBacktest";

type Props = {
  selecao: Selecao;
  escolha: Escolha | undefined;
  resultados: Resultado[];
  anos: Ano[];
  curva: PontoDaCurva[];
  trades: TradeDoBacktest[];
};

function Pilula({
  href,
  ativa,
  escolhida,
  children,
}: {
  href: string;
  ativa: boolean;
  escolhida: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      scroll={false}
      aria-current={ativa ? "true" : undefined}
      className={`toque inline-flex min-h-10 items-center gap-1.5 rounded-full border px-3.5 text-[13px] font-bold transition-colors ${
        ativa
          ? "border-acento bg-selecao text-acento"
          : "border-linha-2 text-tinta-2 hover:text-tinta"
      }`}
    >
      {children}
      {escolhida && (
        <span
          title="Combinação escolhida em 1995–2015"
          className="rounded-md bg-painel px-1.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wide text-tinta-3"
        >
          escolhida
        </span>
      )}
    </Link>
  );
}

const corDoR = (v: number | null) => (v === null ? "" : v > 0 ? "text-alta" : v < 0 ? "text-baixa" : "");

type Linha = {
  rotulo: string;
  celula: (r: Resultado | undefined) => React.ReactNode;
};

const dois = (principal: React.ReactNode, secundario?: React.ReactNode) => (
  <>
    <span className="block text-[13px] font-bold">{principal}</span>
    {secundario !== undefined && (
      <span className="block text-[11px] font-semibold text-tinta-3">{secundario}</span>
    )}
  </>
);

const LINHAS: Linha[] = [
  { rotulo: "Trades", celula: (r) => dois(r ? r.n.toLocaleString("pt-BR") : "—") },
  { rotulo: "Acerto", celula: (r) => dois(fmtPct(r?.acerto)) },
  { rotulo: "Ganho médio", celula: (r) => dois(fmtR(r?.ganhoMedio)) },
  { rotulo: "Perda média", celula: (r) => dois(fmtR(r?.perdaMedia)) },
  { rotulo: "Payoff", celula: (r) => dois(fmtNumero(r?.payoff)) },
  {
    rotulo: "R por trade",
    celula: (r) =>
      dois(
        <span className={corDoR(r?.expectativa ?? null)}>{fmtR(r?.expectativa)}</span>,
        fmtIntervalo(r?.icBaixo, r?.icAlto),
      ),
  },
  { rotulo: "Controle", celula: (r) => dois(fmtR(r?.controle)) },
  {
    rotulo: "Contra o controle",
    celula: (r) =>
      dois(
        <span className={corDoR(r?.diferenca ?? null)}>{fmtR(r?.diferenca)}</span>,
        fmtIntervalo(r?.difIcBaixo, r?.difIcAlto),
      ),
  },
  { rotulo: "Fator de lucro", celula: (r) => dois(fmtNumero(r?.fatorLucro)) },
  { rotulo: "Dias em média", celula: (r) => dois(fmtNumero(r?.diasMedio, 1)) },
];

function Grade({ resultados, selecao }: { resultados: Resultado[]; selecao: Selecao }) {
  const por = (p: (typeof PERIODOS)[number]) =>
    resultados.find((r) => r.saida === selecao.saida && r.grupo === selecao.grupo && r.periodo === p);
  const colunas = PERIODOS.map((p) => por(p));
  // "Como saiu": so os motivos que aparecem em algum periodo (alvo fixo nao tem MME 9).
  const motivos = comoSaiu(colunas[2] ?? colunas[1] ?? colunas[0] ?? vazio()).map((m, i) => ({
    rotulo: m.rotulo,
    valores: colunas.map((c) => (c ? comoSaiu(c)[i].v : null)),
  }));
  const usados = motivos.filter((m) => m.valores.some((v) => v !== null && v > 0));

  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <table className="w-full min-w-[320px] border-collapse text-left">
        <thead>
          <tr>
            <th className="w-[88px] pb-2" />
            {PERIODOS.map((p) => (
              <th key={p} className="rotulo pb-2 pl-1.5 text-right !text-[10px] !tracking-normal">
                {ROTULO_DO_PERIODO[p]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="num">
          {LINHAS.map((l) => (
            <tr key={l.rotulo} className="border-t border-linha">
              <th scope="row" className="py-2 pr-1 text-[12px] font-bold text-tinta-2">
                {l.rotulo}
              </th>
              {colunas.map((c, i) => (
                <td key={PERIODOS[i]} className="py-2 pl-1.5 text-right align-top">
                  {l.celula(c)}
                </td>
              ))}
            </tr>
          ))}
          {usados.length > 0 && (
            <tr className="border-t border-linha-2">
              <th colSpan={4} className="rotulo pb-1 pt-3 text-left">
                Como saiu
              </th>
            </tr>
          )}
          {usados.map((m) => (
            <tr key={m.rotulo}>
              <th scope="row" className="py-1 pr-2 text-[12px] font-bold text-tinta-2">
                {m.rotulo}
              </th>
              {m.valores.map((v, i) => (
                <td key={PERIODOS[i]} className="py-1 pl-1.5 text-right text-[13px] font-bold">
                  {fmtPct(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Resultado vazio so para `comoSaiu` nao receber undefined. */
function vazio(): Resultado {
  return {
    setup: "",
    saida: "mme9",
    grupo: "todos",
    periodo: "tudo",
    n: 0,
    acerto: null,
    ganhoMedio: null,
    perdaMedia: null,
    payoff: null,
    expectativa: null,
    icBaixo: null,
    icAlto: null,
    fatorLucro: null,
    diasMedio: null,
    rPorDia: null,
    controle: null,
    diferenca: null,
    difIcBaixo: null,
    difIcAlto: null,
    pctStop: null,
    pctMovel: null,
    pctAlvo: null,
    pctMme9: null,
    pctTeto: null,
  };
}

function Trades({ trades }: { trades: TradeDoBacktest[] }) {
  if (trades.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-linha-2 p-6 text-center text-[13px] font-semibold text-tinta-3">
        Nenhum trade guardado para esta saída.
      </p>
    );
  }
  const colunas =
    "md:grid-cols-[84px_88px_84px_84px_minmax(0,1.2fr)_minmax(0,1fr)_44px_72px_minmax(0,1fr)]";
  return (
    <div className="flex flex-col gap-2 md:gap-0.5">
      <div className={`hidden gap-2 px-3 md:grid ${colunas}`}>
        <span className="rotulo">Papel</span>
        <span className="rotulo">Sinal</span>
        <span className="rotulo text-right">Entrada</span>
        <span className="rotulo text-right">Stop</span>
        <span className="rotulo text-right">Saída</span>
        <span className="rotulo">Motivo</span>
        <span className="rotulo text-right">Dias</span>
        <span className="rotulo text-right">Resultado</span>
        <span className="rotulo">Etiquetas</span>
      </div>
      <ul className="flex flex-col gap-2 md:gap-0.5">
        {trades.map((t) => (
          <li
            key={t.id}
            className={`grid grid-cols-2 items-center gap-x-3 gap-y-1.5 rounded-2xl bg-painel-2 px-3.5 py-3 md:gap-2 md:bg-transparent md:py-2 md:hover:bg-painel-2 ${colunas}`}
          >
            <Link
              href={linkDoTrade(t)}
              className="order-1 text-[16px] font-extrabold transition-colors hover:text-acento md:order-none md:text-[14px]"
            >
              {t.ticker}
            </Link>
            <span className="num order-5 text-[12px] font-semibold text-tinta-3 md:order-none md:text-[13px]">
              <span className="md:hidden">sinal </span>
              {data(t.dataSinal)}
            </span>
            <span className="num order-6 text-right text-[13px] font-bold md:order-none">
              <span className="text-[11px] font-semibold text-tinta-3 md:hidden">entrada </span>
              {reais(t.entrada)}
            </span>
            <span className="num order-7 text-[13px] font-bold md:order-none md:text-right">
              <span className="text-[11px] font-semibold text-tinta-3 md:hidden">stop </span>
              {reais(t.stop)}
            </span>
            <span className="num order-8 text-right text-[13px] font-bold md:order-none">
              <span className="text-[11px] font-semibold text-tinta-3 md:hidden">saída </span>
              {t.precoSaida === null ? "—" : reais(t.precoSaida)}
              <span className="block text-[11px] font-semibold text-tinta-3">
                {t.dataSaida ? data(t.dataSaida) : ""}
              </span>
            </span>
            <span className="order-3 text-[13px] font-semibold text-tinta-2 md:order-none">
              {MOTIVOS[t.motivo]}
            </span>
            <span className="num order-4 text-right text-[12px] font-semibold text-tinta-3 md:order-none md:text-[13px]">
              {t.dias === null ? "—" : `${t.dias} d`}
            </span>
            <span
              className={`num order-2 text-right text-[16px] font-extrabold md:order-none md:text-[14px] ${corDoR(t.r)}`}
            >
              {fmtR(t.r)}
            </span>
            <span className="order-9 col-span-2 flex flex-wrap items-center gap-1.5 md:order-none md:col-span-1">
              {t.alta !== null && (
                <span className="rounded-md bg-painel px-2 py-0.5 text-[11px] font-bold text-tinta-2 md:bg-painel-2">
                  {t.alta ? "em alta" : "contra"}
                </span>
              )}
              {volumeAlto(t.rvol) && (
                <span
                  title="Volume do dia do sinal sobre a mediana dos 20 pregões anteriores"
                  className="num rounded-md bg-selecao px-2 py-0.5 text-[11px] font-bold text-acento"
                >
                  {fmtVolume(t.rvol)}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DetalheDoBacktest({ selecao, escolha, resultados, anos, curva, trades }: Props) {
  const info = SETUPS[selecao.setup];
  const combinacao = (saida: Selecao["saida"], grupo: Selecao["grupo"]) =>
    linkDaSelecao({ setup: selecao.setup, saida, grupo });

  return (
    // `#detalhe`: no celular o resumo tem 11 cartoes; tocar num setup leva direto aqui.
    <section id="detalhe" className="flex scroll-mt-4 flex-col gap-4">
      <div className="cartao flex flex-col gap-4 p-4 md:p-5">
        <div className="flex flex-col gap-1">
          <h2 className="text-[20px] font-extrabold tracking-tight">{info.nome}</h2>
          <p className="max-w-[75ch] text-[14px] leading-relaxed text-tinta-2">{info.regra}</p>
        </div>

        <div className="flex flex-col gap-2">
          <span className="rotulo">Como sai</span>
          <div className="flex flex-wrap gap-2">
            {ORDEM_DAS_SAIDAS.map((s) => (
              <Pilula
                key={s}
                href={combinacao(s, selecao.grupo)}
                ativa={s === selecao.saida}
                escolhida={escolha?.saida === s}
              >
                {SAIDAS[s]}
              </Pilula>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <span className="rotulo">Tendência</span>
          <div className="flex flex-wrap gap-2">
            {ORDEM_DOS_GRUPOS.map((g) => (
              <Pilula
                key={g}
                href={combinacao(selecao.saida, g)}
                ativa={g === selecao.grupo}
                escolhida={escolha?.grupo === g}
              >
                {GRUPOS[g]}
              </Pilula>
            ))}
          </div>
        </div>
        <p className="text-[12px] font-semibold text-tinta-3">
          {escolha?.saida && escolha.grupo
            ? `Escolhida em 1995–2015, entre ${escolha.combinacoes} combinações com pelo menos 100 trades: ${SAIDAS[escolha.saida]}, ${GRUPOS[escolha.grupo].toLowerCase()}.`
            : "Nenhuma combinação chegou a 100 trades em 1995–2015, então não houve escolha. Você pode olhar qualquer uma."}
          {escolha?.saida && escolha.grupo && (selecao.saida !== escolha.saida || selecao.grupo !== escolha.grupo)
            ? " Você está olhando outra: vale como curiosidade, não foi a que passou pela conferência."
            : ""}
        </p>
      </div>

      <div className="cartao flex flex-col gap-3 p-4 md:p-5">
        <h3 className="text-[16px] font-extrabold">Números</h3>
        <Grade resultados={resultados} selecao={selecao} />
      </div>

      <div className="cartao flex flex-col gap-3 p-4 md:p-5">
        <h3 className="text-[16px] font-extrabold">Curva de R acumulado</h3>
        <CurvaDoBacktest curva={curva} nomeDoSetup={info.nome} />
      </div>

      <div className="cartao flex flex-col gap-3 p-4 md:p-5">
        <h3 className="text-[16px] font-extrabold">Ano a ano</h3>
        <AnosDoBacktest anos={anos} />
      </div>

      <div className="cartao flex flex-col gap-3 p-4 md:p-5">
        <div className="flex flex-col gap-1">
          <h3 className="text-[16px] font-extrabold">Trades recentes</h3>
          <p className="text-[12px] font-semibold text-tinta-3">
            Amostra: os 50 trades mais recentes. Trade antigo pode não ter gráfico (o site guarda
            ~400 pregões). São os trades desta saída, de todas as tendências.
          </p>
        </div>
        <Trades trades={trades} />
      </div>
    </section>
  );
}
