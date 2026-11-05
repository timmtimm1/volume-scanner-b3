"use client";

import Link from "next/link";
import { fmtR } from "@/lib/backtest-tela";
import { diaCurto, percentual, reais } from "@/lib/formato";
import {
  alvoDoSetup,
  contraOMercado,
  ehClassico,
  etiquetasDoSetup,
  gatilho,
  linkDaFicha,
  multiploDoAlvo,
  NOME_DO_CONTEXTO,
  NOME_DO_SETUP,
  nomeDaMedia,
  nomeDosPadroes,
  resultadoEmR,
  rotuloDoEstado,
  SAIDA_EM_TEXTO,
  type ContextoDoDiario,
  type Setup,
  situacaoDoAlerta,
  stopDoSetup,
} from "@/lib/setups-tela";
import { BotaoEntrei } from "./FormularioEntrei";
import { LoteDoSetup } from "./LoteDoSetup";

/** O que o cartao chama o setup: o nome, ou os padroes quando ha. */
function titulo(s: Setup): string {
  if (ehClassico(s.categoria) || s.padroes.length === 0) return NOME_DO_SETUP[s.categoria];
  return `${nomeDosPadroes(s)}${s.categoria === "media" ? ` na ${nomeDaMedia(s.suporteTipo)}` : ""}`;
}

/** A saida do setup em texto; a linha antiga (sem saida escolhida) tem a regra antiga. */
function saidaEmTexto(s: Setup): string {
  return s.saidaRegra === null
    ? "regra antiga: fecha abaixo da mínima ou em 20 pregões"
    : SAIDA_EM_TEXTO[s.saidaRegra];
}

function Cabecalho({ s }: { s: Setup }) {
  const etiquetas = etiquetasDoSetup(s);
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
      <Link
        href={linkDaFicha(s)}
        className="text-[18px] font-extrabold transition-colors hover:text-acento"
      >
        {s.ticker}
      </Link>
      <span className="text-[13px] font-bold text-tinta-2">{titulo(s)}</span>
      <span className="num text-[12px] font-semibold text-tinta-3">{diaCurto(s.tradeDate)}</span>
      <span className="flex-1" />
      {etiquetas.map((e) => (
        <span
          key={e.texto}
          className={`num inline-flex h-7 items-center rounded-full px-2.5 text-[12px] font-bold ${
            e.tipo === "volume" && s.destaque ? "bg-selecao text-acento" : "bg-painel text-tinta-2"
          }`}
        >
          {e.texto}
        </span>
      ))}
    </div>
  );
}

function Linha({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="rotulo">{rotulo}</span>
      <span className="num text-[13px] font-bold">{children}</span>
    </div>
  );
}

function Alvo({ s }: { s: Setup }) {
  const alvo = alvoDoSetup(s);
  const k = multiploDoAlvo(s.saidaRegra);
  if (alvo === null || k === null) return null;
  return (
    <Linha rotulo={`Alvo de ${k}R`}>
      {reais(alvo)}
      {s.entrada === null && (
        <span className="block text-[11px] font-semibold text-tinta-3">a partir do gatilho</span>
      )}
    </Linha>
  );
}

/** A referencia dos classicos: a media, o nivel ou a minima que o setup usa. */
function Referencia({ s }: { s: Setup }) {
  const media = nomeDaMedia(s.suporteTipo);
  const nome = media ?? (s.suporteTipo === "minima" ? "mínima" : "nível");
  return (
    <Linha rotulo="Referência">
      {reais(s.suporte)}
      <span className="font-semibold text-tinta-3"> · {nome}</span>
    </Linha>
  );
}

function Resistencia({ s }: { s: Setup }) {
  return (
    <Linha rotulo="Resistência">
      {s.resistencia === null ? (
        "nenhuma acima"
      ) : (
        <>
          {reais(s.resistencia)}
          {s.espacoR !== null && (
            <span className="font-semibold text-tinta-3">
              {" "}
              · {s.espacoR.toFixed(1).replace(".", ",")}R
            </span>
          )}
        </>
      )}
    </Linha>
  );
}

/** Suporte de quem nasce de suporte ou de media: toques, e o que o candle tinha de especial. */
function Suporte({ s }: { s: Setup }) {
  const extra = [s.virou ? "era resistência" : null, s.furou ? "furou e voltou" : null]
    .filter(Boolean)
    .join(" · ");
  const media = nomeDaMedia(s.suporteTipo);
  return (
    <Linha rotulo={media ? "Suporte na média" : "Suporte"}>
      {reais(s.suporte)} · {media ?? `${s.toques} toques`}
      {extra && <span className="block text-[11px] font-semibold text-tinta-3">{extra}</span>}
    </Linha>
  );
}

function Rodape({ s, hoje }: { s: Setup; hoje: string }) {
  const alerta = situacaoDoAlerta(s, hoje);
  const contexto = s.contexto.map((c) => NOME_DO_CONTEXTO[c] ?? c);
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[12px] font-semibold text-tinta-3">
      {contexto.map((c) => (
        <span key={c} className="rounded-md bg-painel px-2 py-0.5 text-tinta-2">
          {c}
        </span>
      ))}
      <span>saída: {saidaEmTexto(s)}</span>
      {/* a situacao do alerta so diz algo enquanto o setup esta armado */}
      {alerta && s.estado === "armado" && <span>· {alerta}</span>}
    </div>
  );
}

export function CartaoArmado({
  s,
  hoje,
  diario,
}: {
  s: Setup;
  hoje: string;
  diario: ContextoDoDiario;
}) {
  const classico = ehClassico(s.categoria);
  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-2xl bg-painel-2 p-4">
      <Cabecalho s={s} />
      <p className="text-[15px] font-extrabold">
        Entra acima de <span className="num text-acento">{reais(gatilho(s))}</span>
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Linha rotulo="Stop">
          {reais(stopDoSetup(s))}
          <span className="font-semibold text-tinta-3">
            {" "}
            · risco {s.riscoPct.toFixed(1).replace(".", ",")}%
          </span>
        </Linha>
        <Alvo s={s} />
        {classico ? (
          <Referencia s={s} />
        ) : (
          <>
            <Resistencia s={s} />
            <Suporte s={s} />
          </>
        )}
        <Linha rotulo="Fechamento do candle">{reais(s.fechamento)}</Linha>
      </div>
      <LoteDoSetup perfil={diario.perfil} entrada={gatilho(s)} stop={stopDoSetup(s)} />
      <Rodape s={s} hoje={hoje} />
    </article>
  );
}

function ResultadoEmR({ r }: { r: number | null }) {
  if (r === null) return <span className="text-tinta-3">—</span>;
  return <span className={r >= 0 ? "text-alta" : "text-baixa"}>{fmtR(r)}</span>;
}

/**
 * Um em andamento numa linha: o papel, quando entrou, entrada e stop, o
 * resultado ate agora e as etiquetas. Em lista, nao em cartao: um setup com
 * saida pela MME 9 chega a ter duas dezenas abertas ao mesmo tempo.
 */
export function LinhaEmAndamento({ s, diario }: { s: Setup; diario: ContextoDoDiario }) {
  const alvo = alvoDoSetup(s);
  // Duas linhas: em cima o que se le de relance (papel, quando, R, Entrei);
  // embaixo os precos e as etiquetas. Numa linha so, com o botao, os precos
  // viravam uma coluna de cinco linhas no celular.
  return (
    <li className="flex flex-col gap-1.5 py-2.5">
      <div className="flex items-center gap-3">
        <Link
          href={linkDaFicha(s)}
          className="w-16 text-[14px] font-extrabold transition-colors hover:text-acento"
        >
          {s.ticker}
        </Link>
        <span className="num text-[12px] font-semibold text-tinta-3">
          entrou {s.confirmadoEm ? diaCurto(s.confirmadoEm) : "—"}
        </span>
        <span className="num ml-auto text-right text-[13px] font-bold">
          <ResultadoEmR r={resultadoEmR(s)} />
        </span>
        <BotaoEntrei s={s} diario={diario} />
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="num text-[12px] font-semibold text-tinta-2">
          entrada {reais(s.entrada)} · stop {reais(stopDoSetup(s))}
          {alvo !== null && <> · alvo {reais(alvo)}</>}
        </span>
        <span className="flex flex-wrap gap-1.5 text-[11px] font-semibold text-tinta-3">
          {etiquetasDoSetup(s).map((e) => (
            <span key={e.texto} className="rounded-md bg-painel px-2 py-0.5 text-tinta-2">
              {e.texto}
            </span>
          ))}
        </span>
      </div>
    </li>
  );
}

/** Um encerrado numa linha: o dia, o papel, como terminou e o resultado. */
export function LinhaDeEncerrado({ s }: { s: Setup }) {
  const contra = contraOMercado(s, 20);
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
      <Link
        href={linkDaFicha(s)}
        className="w-16 text-[14px] font-extrabold transition-colors hover:text-acento"
      >
        {s.ticker}
      </Link>
      <span className="num w-12 text-[12px] font-semibold text-tinta-3">{diaCurto(s.tradeDate)}</span>
      <span className="min-w-0 flex-1 text-[13px] font-semibold text-tinta-2">
        {rotuloDoEstado(s.estado, s.saidaRegra)}
      </span>
      <span className="num text-right text-[13px] font-bold">
        {s.saidaRegra !== null ? (
          <ResultadoEmR r={resultadoEmR(s)} />
        ) : contra !== null ? (
          <>
            <span className={contra >= 0 ? "text-alta" : "text-baixa"}>{percentual(contra)}</span>
            <span className="text-[11px] font-semibold text-tinta-3"> em 20 pregões, contra o mercado</span>
          </>
        ) : (
          <span className="text-tinta-3">—</span>
        )}
      </span>
    </li>
  );
}
