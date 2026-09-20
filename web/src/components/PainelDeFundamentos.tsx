"use client";

import { type ReactNode, useMemo } from "react";
import {
  indicadoresNaData,
  type Indicadores,
  variacaoAnual,
} from "@/lib/fundamentos";
import {
  data as fmtData,
  dinheiro,
  numero,
  percentual,
  proporcao,
} from "@/lib/formato";
import type { Barra, Fundamentos } from "@/lib/types";

type Props = {
  dados: Fundamentos;
  barras: Barra[];
  /** Pregao que a ficha esta mostrando. */
  data: string;
};

const corDaDirecao = (v: number | null) =>
  (v ?? 0) >= 0 ? "text-alta" : "text-baixa";

/** Um numero da grade: rotulo pequeno em cima, valor grande embaixo. */
function Celula({
  rotulo,
  valor,
  cor,
}: {
  rotulo: string;
  valor: string;
  cor?: string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="truncate text-[11px] font-semibold text-tinta-3">
        {rotulo}
      </span>
      <span className={`num text-[15px] font-extrabold ${cor ?? "text-tinta"}`}>
        {valor}
      </span>
    </div>
  );
}

function Grupo({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 border-b border-linha py-3 last:border-b-0">
      <span className="text-[11px] font-extrabold uppercase tracking-wider text-tinta-3">
        {titulo}
      </span>
      <div className="grid grid-cols-2 gap-x-3 gap-y-2.5">{children}</div>
    </div>
  );
}

/**
 * Receita e lucro dos ultimos trimestres, lado a lado.
 *
 * Barra de lucro negativo desce abaixo da linha: prejuizo nao e uma barra
 * pequena, e outra direcao.
 */
function MiniSerie({ indicadores }: { indicadores: Indicadores }) {
  const serie = indicadores.serie;
  if (serie.length < 2) return null;

  const valores = serie.flatMap((t) => [t.receitaTri ?? 0, t.lucroTri ?? 0]);
  const teto = Math.max(...valores.map(Math.abs), 1);

  return (
    <div className="flex flex-col gap-1.5 pt-3">
      <div className="flex items-end gap-1" aria-hidden>
        {serie.map((t) => (
          <div
            key={t.dtFim}
            className="flex flex-1 flex-col items-center gap-[2px]"
          >
            <div className="flex h-12 w-full items-end justify-center gap-[2px]">
              <span
                className="w-1/2 rounded-t-[2px] bg-acento/70"
                style={{
                  height: `${(Math.abs(t.receitaTri ?? 0) / teto) * 100}%`,
                }}
              />
              <span
                className={`w-1/2 rounded-t-[2px] ${(t.lucroTri ?? 0) >= 0 ? "bg-alta" : "bg-baixa"}`}
                style={{
                  height: `${(Math.abs(t.lucroTri ?? 0) / teto) * 100}%`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between text-[10px] font-semibold text-tinta-3">
        <span>{serie[0].rotulo}</span>
        <span className="flex items-center gap-2.5">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-[2px] bg-acento/70" /> receita
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-[2px] bg-alta" /> lucro
          </span>
        </span>
        <span>{serie[serie.length - 1].rotulo}</span>
      </div>
    </div>
  );
}

/** Uma linha de resultado: trimestre, variação contra o ano anterior e 12 meses. */
function LinhaDeResultado({
  rotulo,
  trimestre,
  anoAnterior,
}: {
  rotulo: string;
  trimestre: number | null;
  anoAnterior: number | null;
}) {
  const variacao = variacaoAnual(trimestre, anoAnterior);
  return (
    <div className="grid grid-cols-[1fr_auto_auto] items-center gap-2 py-1.5">
      <span className="text-[12px] font-semibold text-tinta-2">{rotulo}</span>
      <span className="num w-[72px] text-right text-[13px] font-extrabold">
        {dinheiro(trimestre)}
      </span>
      <span
        className={`num w-[56px] text-right text-[12px] font-bold ${corDaDirecao(variacao)}`}
      >
        {percentual(variacao, 0)}
      </span>
    </div>
  );
}

/**
 * A aba Fundamentos da ficha: o que a empresa publicou ate o pregao que a
 * ficha esta mostrando, com os multiplos daquele dia.
 *
 * Numero que nao da para calcular vira travessao. Em banco, EBITDA, divida
 * liquida e margem nem aparecem -- nao existem no sentido usual, e mostrar
 * "—" em cinco linhas seguidas so encheria a tela.
 */
export function PainelDeFundamentos({ dados, barras, data }: Props) {
  const indicadores = useMemo(
    () => indicadoresNaData(dados, barras, data),
    [dados, barras, data],
  );

  if (indicadores === null) {
    return (
      <p className="py-6 text-[13px] text-tinta-3">
        Nenhum balanço publicado até este pregão.
      </p>
    );
  }

  const { trimestre, anoAnterior, ehBanco } = indicadores;

  return (
    <div className="flex flex-col">
      <p className="num pb-1 text-[12px] font-semibold text-tinta-3">
        {trimestre.rotulo} · publicado em{" "}
        {trimestre.publicadoEm === null ? "—" : fmtData(trimestre.publicadoEm)}
        {trimestre.origem === "derivado" && " · calculado do balanço anual"}
      </p>
      <p className="num pb-1 text-[12px] font-semibold text-tinta-3">
        múltiplos com o fechamento de {fmtData(data)}
      </p>

      <Grupo titulo="Valuation">
        <Celula rotulo="P/L" valor={numero(indicadores.precoLucro, 1)} />
        <Celula
          rotulo="P/VP"
          valor={numero(indicadores.precoValorPatrimonial, 1)}
        />
        {!ehBanco && (
          <Celula rotulo="EV/EBITDA" valor={numero(indicadores.evEbitda, 1)} />
        )}
        <Celula
          rotulo="Dividend yield 12m"
          valor={proporcao(indicadores.dividendYield, 1)}
        />
        <Celula
          rotulo="Valor de mercado"
          valor={dinheiro(indicadores.valorDeMercado)}
        />
      </Grupo>

      <Grupo titulo="Rentabilidade">
        <Celula
          rotulo="ROE"
          valor={proporcao(indicadores.retornoSobrePatrimonio, 1)}
        />
        {!ehBanco && (
          <Celula
            rotulo="Margem líquida"
            valor={proporcao(indicadores.margemLiquida, 1)}
          />
        )}
        <Celula
          rotulo="Patrimônio líquido"
          valor={dinheiro(trimestre.patrimonioLiquido)}
        />
      </Grupo>

      {!ehBanco && (
        <Grupo titulo="Endividamento">
          <Celula
            rotulo="Dív. líquida/patrimônio"
            valor={numero(indicadores.dividaLiquidaPatrimonio, 2)}
          />
          <Celula
            rotulo="Liquidez corrente"
            valor={numero(indicadores.liquidezCorrente, 2)}
          />
          <Celula
            rotulo="Dívida líquida"
            valor={dinheiro(indicadores.dividaLiquida)}
          />
        </Grupo>
      )}

      <div className="flex flex-col gap-1 py-3">
        <div className="grid grid-cols-[1fr_auto_auto] items-center gap-2">
          <span className="text-[11px] font-extrabold uppercase tracking-wider text-tinta-3">
            Resultados
          </span>
          <span className="w-[72px] text-right text-[10px] font-bold text-tinta-3">
            {trimestre.rotulo}
          </span>
          <span className="w-[56px] text-right text-[10px] font-bold text-tinta-3">
            {anoAnterior === null ? "vs ano ant." : `vs ${anoAnterior.rotulo}`}
          </span>
        </div>
        <LinhaDeResultado
          rotulo="Receita"
          trimestre={trimestre.receitaTri}
          anoAnterior={anoAnterior?.receitaTri ?? null}
        />
        {!ehBanco && (
          <LinhaDeResultado
            rotulo="EBITDA"
            trimestre={trimestre.ebitdaTri}
            anoAnterior={anoAnterior?.ebitdaTri ?? null}
          />
        )}
        <LinhaDeResultado
          rotulo="Lucro"
          trimestre={trimestre.lucroTri}
          anoAnterior={anoAnterior?.lucroTri ?? null}
        />
        <div className="mt-1 flex flex-col gap-1 rounded-xl bg-painel-2 px-3 py-2">
          <span className="text-[11px] font-semibold text-tinta-3">
            Últimos 12 meses
          </span>
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="num text-[13px] font-extrabold">
              receita {dinheiro(trimestre.receita12m)}
            </span>
            {!ehBanco && (
              <span className="num text-[13px] font-extrabold">
                EBITDA {dinheiro(trimestre.ebitda12m)}
              </span>
            )}
            <span className="num text-[13px] font-extrabold">
              lucro {dinheiro(trimestre.lucro12m)}
            </span>
          </div>
        </div>
        <MiniSerie indicadores={indicadores} />
      </div>

      <p className="pb-3 text-[11px] leading-relaxed text-tinta-3">
        {ehBanco
          ? "Banco: EBITDA, dívida líquida e margem não se aplicam a esta estrutura de balanço."
          : "Dados da CVM. O EBITDA é calculado (resultado operacional + depreciação), e pode diferir do EBITDA ajustado que a empresa divulga."}
      </p>
    </div>
  );
}
