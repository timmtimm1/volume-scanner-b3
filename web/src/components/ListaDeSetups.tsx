"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { diaCurto, multiplo, percentual, reais } from "@/lib/formato";
import {
  contraOMercado,
  desdeAEntrada,
  folgaAteOStop,
  HORIZONTES,
  linkDaFicha,
  NOME_DO_CONTEXTO,
  nomeDaMedia,
  nomeDosPadroes,
  resumoDoHistorico,
  rotuloDoEstado,
  type Setup,
  separar,
  situacaoDoAlerta,
} from "@/lib/setups-tela";

type Props = { setups: Setup[]; hoje: string };

/**
 * A aba Setups: armados, em andamento, o candle de forca a parte e o
 * historico com o resultado contra o mercado.
 */
export function ListaDeSetups({ setups, hoje }: Props) {
  // Na estreia o historico ao vivo esta vazio: os retroativos aparecem de
  // inicio, marcados, e um toque deixa so o que foi visto na hora.
  const [comRetroativos, setComRetroativos] = useState(true);
  const secoes = useMemo(() => separar(setups, comRetroativos), [setups, comRetroativos]);
  const aoVivo = useMemo(() => resumoDoHistorico(separar(setups, false).historico), [setups]);
  const retroativos = useMemo(
    () => resumoDoHistorico(separar(setups, true).historico.filter((s) => !s.aoVivo)),
    [setups],
  );
  const mediaAoVivo = useMemo(
    () => resumoDoHistorico(separar(setups, false).historico, "media"),
    [setups],
  );
  const ultimoPregao = setups.find((s) => s.ultimoPregao)?.ultimoPregao ?? null;

  return (
    <div className="flex flex-col gap-4">
      <Secao
        titulo="Armados"
        subtitulo={
          ultimoPregao
            ? `Candles do pregão de ${diaCurto(ultimoPregao)}: confirmam se o pregão seguinte passar da máxima.`
            : "Confirmam se o pregão seguinte passar da máxima do candle."
        }
        vazio="Nenhum setup armado no último pregão."
      >
        {secoes.armados.map((s) => (
          <CartaoArmado key={s.id} s={s} hoje={hoje} />
        ))}
      </Secao>

      <Secao
        titulo="Em andamento"
        subtitulo="Confirmados: ficam aqui até fechar abaixo da mínima do padrão ou completar 20 pregões."
        vazio="Nenhum setup em andamento."
      >
        {secoes.emAndamento.map((s) => (
          <CartaoEmAndamento key={s.id} s={s} hoje={hoje} />
        ))}
      </Secao>

      <Secao
        titulo="Na média"
        subtitulo="Tendência de alta: o candle encostou na MME 9 ou na MMA 20 subindo, com o preço vindo de cima. Seção própria: no estudo, foi bem no trade de referência nos dois períodos, mas perdeu para o mercado em 2016–2026."
        vazio="Nenhum setup na média armado ou em andamento."
      >
        {secoes.media.map((s) =>
          s.estado === "armado" ? (
            <CartaoArmado key={s.id} s={s} hoje={hoje} />
          ) : (
            <CartaoEmAndamento key={s.id} s={s} hoje={hoje} />
          ),
        )}
      </Secao>

      {secoes.forca.length > 0 && (
        <section className="cartao flex flex-col gap-3 p-4 md:p-5">
          <div className="flex flex-col gap-1">
            <h2 className="text-[18px] font-extrabold">
              Candle de força
              <span className="num ml-2 text-[13px] font-bold text-tinta-3">{secoes.forca.length}</span>
            </h2>
            <p className="text-[13px] font-semibold text-tinta-3">
              À parte: com os mesmos filtros, foi bem em 1995–2015 e mal em 2016–2026 no estudo.
              Aparece para leitura, sem alerta de confirmação.
            </p>
          </div>
          <ul className="flex flex-col divide-y divide-linha">
            {secoes.forca.map((s) => (
              <LinhaDeForca key={s.id} s={s} />
            ))}
          </ul>
        </section>
      )}

      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <div className="flex flex-wrap items-start gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <h2 className="text-[18px] font-extrabold">Histórico</h2>
            <p className="max-w-[70ch] text-[13px] font-semibold text-tinta-3">
              Contra o mercado: quanto o papel andou além da média dos papéis líquidos no
              mesmo período. É o que aconteceu, não uma promessa.
            </p>
          </div>
          <div className="flex-1" />
          <button
            type="button"
            onClick={() => setComRetroativos((v) => !v)}
            aria-pressed={!comRetroativos}
            className={`inline-flex h-9 items-center rounded-full px-3.5 text-[12px] font-bold transition-colors ${
              comRetroativos ? "bg-painel-2 text-tinta-2" : "bg-selecao text-acento"
            }`}
          >
            Só ao vivo
          </button>
        </div>

        <div className="grid gap-2 md:grid-cols-3">
          <Resumo rotulo="No suporte, ao vivo" r={aoVivo} />
          <Resumo rotulo="Na média, ao vivo" r={mediaAoVivo} />
          <Resumo rotulo="No suporte, retroativos" r={retroativos} />
        </div>

        {secoes.historico.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-linha-2 p-6 text-center text-[13px] font-semibold text-tinta-3">
            Nenhum setup encerrado ainda. Cada um entra aqui quando não confirma, para no stop ou
            completa os 20 pregões.
          </p>
        ) : (
          <Historico lista={secoes.historico} />
        )}
      </section>
    </div>
  );
}

function Secao({
  titulo,
  subtitulo,
  vazio,
  children,
}: {
  titulo: string;
  subtitulo: string;
  vazio: string;
  children: React.ReactNode[];
}) {
  return (
    <section className="cartao flex flex-col gap-3 p-4 md:p-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-[18px] font-extrabold">
          {titulo}
          {children.length > 0 && (
            <span className="num ml-2 text-[13px] font-bold text-tinta-3">{children.length}</span>
          )}
        </h2>
        <p className="text-[13px] font-semibold text-tinta-3">{subtitulo}</p>
      </div>
      {children.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-linha-2 p-6 text-center text-[13px] font-semibold text-tinta-3">
          {vazio}
        </p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{children}</div>
      )}
    </section>
  );
}

function Cabecalho({ s }: { s: Setup }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Link
        href={linkDaFicha(s)}
        className="text-[18px] font-extrabold transition-colors hover:text-acento"
      >
        {s.ticker}
      </Link>
      <span className="text-[13px] font-bold text-tinta-2">
        {nomeDosPadroes(s)}
        {s.categoria === "media" && ` na ${nomeDaMedia(s.suporteTipo)}`}
      </span>
      <span className="num text-[12px] font-semibold text-tinta-3">{diaCurto(s.tradeDate)}</span>
      <span className="flex-1" />
      <span
        className={`num inline-flex h-7 items-center rounded-full px-2.5 text-[12px] font-bold ${
          s.destaque ? "bg-selecao text-acento" : "bg-painel text-tinta-2"
        }`}
        title="Volume do dia sobre a mediana dos 20 pregões anteriores"
      >
        {s.destaque ? "★ " : ""}
        volume {multiplo(s.rvol)}
      </span>
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

function Resistencia({ s }: { s: Setup }) {
  return (
    <Linha rotulo="Resistência">
      {s.resistencia === null ? (
        "nenhuma acima"
      ) : (
        <>
          {reais(s.resistencia)}
          {s.espacoR !== null && (
            <span className="font-semibold text-tinta-3"> · {s.espacoR.toFixed(1).replace(".", ",")}R</span>
          )}
        </>
      )}
    </Linha>
  );
}

function Rodape({ s, hoje }: { s: Setup; hoje: string }) {
  const alerta = situacaoDoAlerta(s, hoje);
  const contexto = s.contexto.map((c) => NOME_DO_CONTEXTO[c] ?? c);
  if (!alerta && contexto.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[12px] font-semibold text-tinta-3">
      {contexto.map((c) => (
        <span key={c} className="rounded-md bg-painel px-2 py-0.5 text-tinta-2">
          {c}
        </span>
      ))}
      {alerta && <span>{alerta}</span>}
    </div>
  );
}

function CartaoArmado({ s, hoje }: { s: Setup; hoje: string }) {
  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-2xl bg-painel-2 p-4">
      <Cabecalho s={s} />
      <p className="text-[15px] font-extrabold">
        Confirma acima de <span className="num text-acento">{reais(s.maxima)}</span>
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Linha rotulo="Mínima do padrão">
          {reais(s.minima)}
          <span className="font-semibold text-tinta-3"> · risco {s.riscoPct.toFixed(1).replace(".", ",")}%</span>
        </Linha>
        <Resistencia s={s} />
        <Suporte s={s} />
        <Linha rotulo="Fechamento do candle">{reais(s.fechamento)}</Linha>
      </div>
      <Rodape s={s} hoje={hoje} />
    </article>
  );
}

function CartaoEmAndamento({ s, hoje }: { s: Setup; hoje: string }) {
  const desde = desdeAEntrada(s);
  const folga = folgaAteOStop(s);
  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-2xl bg-painel-2 p-4">
      <Cabecalho s={s} />
      <p className="num text-[13px] font-semibold text-tinta-2">
        confirmado em {s.confirmadoEm ? diaCurto(s.confirmadoEm) : "—"}
        {s.pregoesDesde !== null && <> · pregão {s.pregoesDesde} de 20</>}
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Linha rotulo="Entrada">{reais(s.entrada)}</Linha>
        <Linha rotulo={`Último fechamento${s.ultimoPregao ? ` (${diaCurto(s.ultimoPregao)})` : ""}`}>
          {reais(s.ultimoFechamento)}
          {desde !== null && (
            <span className={desde >= 0 ? "text-alta" : "text-baixa"}> {percentual(desde)}</span>
          )}
        </Linha>
        <Linha rotulo="Mínima do padrão">
          {reais(s.minima)}
          {folga !== null && <span className="font-semibold text-tinta-3"> · {percentual(folga)}</span>}
        </Linha>
        <Resistencia s={s} />
      </div>
      <Rodape s={s} hoje={hoje} />
    </article>
  );
}

/** O candle de forca numa linha so: fica a parte e nao disputa espaco com a regra. */
function LinhaDeForca({ s }: { s: Setup }) {
  const desde = desdeAEntrada(s);
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
      <Link
        href={linkDaFicha(s)}
        className="w-16 text-[14px] font-extrabold transition-colors hover:text-acento"
      >
        {s.ticker}
      </Link>
      <span className="num w-12 text-[12px] font-semibold text-tinta-3">{diaCurto(s.tradeDate)}</span>
      <span className="num text-[12px] font-bold text-tinta-2">
        {s.destaque ? "★ " : ""}
        {multiplo(s.rvol)}
      </span>
      <span className="num min-w-0 flex-1 text-right text-[13px] font-semibold text-tinta-2">
        {s.estado === "armado" ? (
          <>confirma acima de {reais(s.maxima)}</>
        ) : (
          <>
            entrada {reais(s.entrada)} →{" "}
            {desde === null ? (
              "—"
            ) : (
              <span className={desde >= 0 ? "text-alta" : "text-baixa"}>{percentual(desde)}</span>
            )}
          </>
        )}
      </span>
    </li>
  );
}

function Resumo({ rotulo, r }: { rotulo: string; r: ReturnType<typeof resumoDoHistorico> }) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl bg-painel-2 p-3">
      <span className="rotulo">{rotulo}</span>
      {r.setups === 0 ? (
        <span className="text-[13px] font-semibold text-tinta-3">nenhum encerrado ainda</span>
      ) : (
        <span className="num text-[13px] font-bold">
          {r.setups} setup{r.setups === 1 ? "" : "s"} · {r.confirmaram} confirmaram
          {r.media20 !== null && (
            <span className="block font-semibold text-tinta-2">
              20 pregões depois:{" "}
              <span className={r.media20 >= 0 ? "text-alta" : "text-baixa"}>{percentual(r.media20)}</span>{" "}
              contra o mercado, em média ({r.comResultado} com resultado)
            </span>
          )}
        </span>
      )}
    </div>
  );
}

function Retorno({ v }: { v: number | null }) {
  if (v === null) return <span className="text-tinta-3">—</span>;
  return <span className={v >= 0 ? "text-alta" : "text-baixa"}>{percentual(v)}</span>;
}

function Historico({ lista }: { lista: Setup[] }) {
  const colunas = "md:grid-cols-[80px_80px_minmax(0,1fr)_70px_minmax(0,1.2fr)_70px_70px_70px_90px]";
  return (
    <div className="flex flex-col gap-2 md:gap-0.5">
      <div className={`hidden gap-2 px-3 md:grid ${colunas}`}>
        <span className="rotulo">Candle</span>
        <span className="rotulo">Papel</span>
        <span className="rotulo">Padrão</span>
        <span className="rotulo text-right">Volume</span>
        <span className="rotulo">Situação</span>
        {HORIZONTES.map((h) => (
          <span key={h} className="rotulo text-right">
            {h} preg.
          </span>
        ))}
        <span className="rotulo text-right">Da entrada</span>
      </div>
      <ul className="flex flex-col gap-2 md:gap-0.5">
        {lista.map((s) => (
          <li
            key={s.id}
            className={`grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 rounded-2xl bg-painel-2 px-3.5 py-3 md:grid md:gap-2 md:bg-transparent md:py-2 md:hover:bg-painel-2 ${colunas}`}
          >
            <span className="num text-[12px] font-semibold text-tinta-3 md:text-[13px]">
              {diaCurto(s.tradeDate)}
              {!s.aoVivo && (
                <span className="ml-1.5 rounded bg-painel px-1 text-[10px] font-bold uppercase text-tinta-3">
                  retro
                </span>
              )}
            </span>
            <Link
              href={linkDaFicha(s)}
              className="text-[15px] font-extrabold transition-colors hover:text-acento md:text-[14px]"
            >
              {s.ticker}
            </Link>
            <span className="text-[13px] font-semibold text-tinta-2">
              {nomeDosPadroes(s)}
              {s.categoria === "forca" && <span className="text-tinta-3"> · à parte</span>}
              {s.categoria === "media" && (
                <span className="text-tinta-3"> · na {nomeDaMedia(s.suporteTipo)}</span>
              )}
            </span>
            <span className="num text-[13px] font-bold md:text-right">
              {s.destaque ? "★ " : ""}
              {multiplo(s.rvol)}
            </span>
            <span className="text-[13px] font-semibold text-tinta-2">{rotuloDoEstado(s.estado)}</span>
            {HORIZONTES.map((h) => (
              <span key={h} className="num text-[13px] font-bold md:text-right">
                <span className="text-[11px] font-semibold text-tinta-3 md:hidden">{h} preg. </span>
                <Retorno v={contraOMercado(s, h)} />
              </span>
            ))}
            <span className="num text-[13px] font-bold md:text-right">
              <span className="text-[11px] font-semibold text-tinta-3 md:hidden">da entrada </span>
              <Retorno v={s.confirmadoEm ? s.rc[20] : null} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
