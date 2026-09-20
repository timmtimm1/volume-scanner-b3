"use client";

import { type ReactNode, useMemo, useState } from "react";
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

/** Largura do balao do trimestre, em pixels -- o clamp precisa dela para
 *  prender o balao dentro do grafico nas colunas das pontas. */
const LARGURA_DO_BALAO = 168;

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

type BarraDoGrafico = {
  valor: number | null;
  /** Classe de fundo quando o valor e positivo. */
  cor: string;
  /** Classe de fundo quando e negativo. Sem ela, vale `cor` nos dois lados. */
  corNegativa?: string;
};

type Coluna = {
  chave: string;
  /** O que o trimestre diz, para o leitor de tela e para o rotulo do toque. */
  descricao: string;
  rotulo: string;
  valores: { nome: string; texto: string }[];
  barras: BarraDoGrafico[];
};

/**
 * Barras de trimestre com a linha do zero no lugar certo.
 *
 * Valor negativo desce ABAIXO da linha. Prejuizo nao e um lucro pequeno pintado
 * de vermelho -- e a outra direcao, e o grafico tem de mostrar isso. Por isso a
 * altura acima e abaixo da linha e proporcional ao maior positivo e ao maior
 * negativo da serie: a linha do zero flutua conforme o dado.
 *
 * Serve tanto para receita/lucro quanto para divida/EBITDA, e em divida o
 * negativo e caixa liquido -- bom, nao ruim. Por isso a cor de cada lado e de
 * quem chama, e nao uma regra fixa aqui dentro.
 */
function BarrasComZero({
  colunas,
  altura = 72,
  selecionada,
  aoSelecionar,
}: {
  colunas: Coluna[];
  altura?: number;
  selecionada: string | null;
  aoSelecionar: (chave: string | null) => void;
}) {
  const valores = colunas.flatMap((c) => c.barras.map((b) => b.valor ?? 0));
  const teto = Math.max(0, ...valores);
  const piso = Math.min(0, ...valores);
  const amplitude = teto - piso || 1;
  const acima = (teto / amplitude) * 100;

  const fatia = (b: BarraDoGrafico, lado: "cima" | "baixo") => {
    const v = b.valor;
    if (v === null || v === 0) return { altura: 0, cor: "" };
    if (lado === "cima") {
      return v > 0 && teto > 0
        ? { altura: (v / teto) * 100, cor: b.cor }
        : { altura: 0, cor: "" };
    }
    return v < 0 && piso < 0
      ? { altura: (v / piso) * 100, cor: b.corNegativa ?? b.cor }
      : { altura: 0, cor: "" };
  };

  return (
    <div className="flex items-stretch gap-1" style={{ height: altura }}>
      {colunas.map((coluna) => (
        <button
          key={coluna.chave}
          type="button"
          aria-label={coluna.descricao}
          aria-pressed={selecionada === coluna.chave}
          onClick={() =>
            aoSelecionar(selecionada === coluna.chave ? null : coluna.chave)
          }
          // No desktop o gesto natural e o ponteiro; o clique e o foco ficam
          // para teclado. No celular nada disso aparece -- ver o comentario do
          // balao --, mas o botao continua, porque o `aria-label` dele e como o
          // leitor de tela da os valores do trimestre em qualquer largura.
          onMouseEnter={() => aoSelecionar(coluna.chave)}
          onMouseLeave={() => aoSelecionar(null)}
          onFocus={() => aoSelecionar(coluna.chave)}
          onBlur={() => aoSelecionar(null)}
          className={`flex flex-1 flex-col rounded-[3px] transition-colors ${
            selecionada === coluna.chave ? "lg:bg-selecao" : ""
          }`}
        >
          <div className="flex w-full items-end gap-[2px]" style={{ height: `${acima}%` }}>
            {coluna.barras.map((b, i) => {
              const f = fatia(b, "cima");
              return (
                <span
                  key={`${coluna.chave}-cima-${i}`}
                  className={`flex-1 rounded-t-[2px] ${f.cor}`}
                  style={{ height: `${f.altura}%` }}
                />
              );
            })}
          </div>
          <span className="h-px w-full shrink-0 bg-tinta-3/40" />
          <div className="flex w-full items-start gap-[2px]" style={{ height: `${100 - acima}%` }}>
            {coluna.barras.map((b, i) => {
              const f = fatia(b, "baixo");
              return (
                <span
                  key={`${coluna.chave}-baixo-${i}`}
                  className={`flex-1 rounded-b-[2px] ${f.cor}`}
                  style={{ height: `${f.altura}%` }}
                />
              );
            })}
          </div>
        </button>
      ))}
    </div>
  );
}

function Legenda({ itens }: { itens: { cor: string; nome: string }[] }) {
  return (
    <span className="flex items-center gap-2.5">
      {itens.map((i) => (
        <span key={i.nome} className="flex items-center gap-1">
          <span className={`h-2 w-2 rounded-[2px] ${i.cor}`} /> {i.nome}
        </span>
      ))}
    </span>
  );
}

/**
 * Os trimestres em grafico, com um seletor entre resultado e endividamento.
 *
 * O de endividamento poe divida liquida e EBITDA de 12 meses lado a lado de
 * proposito: e a leitura visual da alavancagem, que a razao no rodape confirma
 * em numero. Divida negativa e caixa liquido e desce em verde, porque ali para
 * baixo e bom -- o contrario do prejuizo.
 *
 * Em banco o seletor nem aparece: nao ha divida liquida nem EBITDA no sentido
 * usual, e uma aba vazia so confundiria.
 */
function GraficosDoTrimestre({ indicadores }: { indicadores: Indicadores }) {
  const [grafico, setGrafico] = useState<"resultado" | "endividamento">(
    "resultado",
  );
  const [selecionada, setSelecionada] = useState<string | null>(null);
  const serie = indicadores.serie;

  const temEndividamento =
    !indicadores.ehBanco &&
    serie.some((t) => t.dividaLiquida !== null || t.ebitda12m !== null);

  if (serie.length < 2) return null;
  const ver = temEndividamento ? grafico : "resultado";

  const colunas: Coluna[] =
    ver === "resultado"
      ? serie.map((t) => ({
          chave: t.dtFim,
          rotulo: t.rotulo,
          valores: [
            { nome: "receita", texto: dinheiro(t.receitaTri) },
            { nome: "lucro", texto: dinheiro(t.lucroTri) },
          ],
          descricao: `${t.rotulo}: receita ${dinheiro(t.receitaTri)}, lucro ${dinheiro(t.lucroTri)}`,
          barras: [
            { valor: t.receitaTri, cor: "bg-acento/70" },
            { valor: t.lucroTri, cor: "bg-alta", corNegativa: "bg-baixa" },
          ],
        }))
      : serie.map((t) => ({
          chave: t.dtFim,
          rotulo: t.rotulo,
          valores: [
            { nome: "dívida líq.", texto: dinheiro(t.dividaLiquida) },
            { nome: "EBITDA 12m", texto: dinheiro(t.ebitda12m) },
          ],
          descricao: `${t.rotulo}: dívida líquida ${dinheiro(t.dividaLiquida)}, EBITDA de 12 meses ${dinheiro(t.ebitda12m)}`,
          barras: [
            {
              valor: t.dividaLiquida,
              cor: "bg-baixa/80",
              corNegativa: "bg-alta/80",
            },
            { valor: t.ebitda12m, cor: "bg-acento/70" },
          ],
        }));

  // Trocar de grafico nao pode deixar uma selecao do outro para tras.
  const aberta = colunas.some((c) => c.chave === selecionada) ? selecionada : null;
  const detalhe = colunas.find((c) => c.chave === aberta);
  const indiceAberto = colunas.findIndex((c) => c.chave === aberta);

  const legenda =
    ver === "resultado"
      ? [
          { cor: "bg-acento/70", nome: "receita" },
          { cor: "bg-alta", nome: "lucro" },
        ]
      : [
          { cor: "bg-baixa/80", nome: "dívida líq." },
          { cor: "bg-acento/70", nome: "EBITDA 12m" },
        ];

  const ultimo = serie[serie.length - 1];
  const alavancagem =
    ultimo.dividaLiquida !== null && ultimo.ebitda12m !== null && ultimo.ebitda12m > 0
      ? ultimo.dividaLiquida / ultimo.ebitda12m
      : null;

  return (
    <div className="flex flex-col gap-2 pt-3">
      {temEndividamento && (
        <div className="flex items-center gap-1" role="tablist" aria-label="Qual gráfico">
          {(["resultado", "endividamento"] as const).map((chave) => (
            <button
              key={chave}
              type="button"
              role="tab"
              aria-selected={ver === chave}
              onClick={() => setGrafico(chave)}
              className={`rounded-full px-2.5 py-1 text-[11px] font-bold transition-colors ${
                ver === chave ? "bg-selecao text-acento" : "text-tinta-3 hover:text-tinta"
              }`}
            >
              {chave === "resultado" ? "Resultado" : "Endividamento"}
            </button>
          ))}
        </div>
      )}

      <div className="relative">
        {detalhe && (
          <div
            className="pointer-events-none absolute bottom-full z-10 mb-1.5 hidden w-[168px] -translate-x-1/2 rounded-lg bg-painel px-2.5 py-1.5 text-[11px] font-semibold shadow-lg ring-1 ring-linha lg:block"
            // So no desktop: em 390px o balao cobriria o grafico que ele
            // explica. La o dado sai pelo `aria-label` da coluna e pelos
            // numeros da tabela de resultados, que ja estao logo acima.
            //
            // Centrado na coluna, mas preso dentro do grafico. O limite e meia
            // largura do balao, em PIXEL: um clamp em porcentagem nao sabe o
            // tamanho dele, e a coluna da direita fica a 360px na ficha.
            style={{
              left: `clamp(${LARGURA_DO_BALAO / 2}px, ${((indiceAberto + 0.5) / colunas.length) * 100}%, calc(100% - ${LARGURA_DO_BALAO / 2}px))`,
            }}
            role="status"
          >
            <span className="num block pb-0.5 font-extrabold">
              {detalhe.rotulo}
            </span>
            {detalhe.valores.map((v) => (
              <span key={v.nome} className="flex justify-between gap-3">
                <span className="text-tinta-3">{v.nome}</span>
                <span className="num font-extrabold">{v.texto}</span>
              </span>
            ))}
          </div>
        )}
        <BarrasComZero
          colunas={colunas}
          selecionada={aberta}
          aoSelecionar={setSelecionada}
        />
      </div>

      <div className="flex items-center justify-between text-[10px] font-semibold text-tinta-3">
        <span>{serie[0].rotulo}</span>
        <Legenda itens={legenda} />
        <span>{ultimo.rotulo}</span>
      </div>
      <p className="hidden text-[10px] font-semibold text-tinta-3 lg:block">
        Passe o ponteiro numa coluna para ver os valores do trimestre.
      </p>

      {ver === "endividamento" && (
        <p className="text-[11px] leading-relaxed text-tinta-3">
          {alavancagem === null
            ? "Dívida líquida sobre EBITDA: não dá para calcular neste trimestre."
            : `Dívida líquida sobre EBITDA de 12 meses: ${numero(alavancagem, 2)}× em ${ultimo.rotulo}.`}
          {(ultimo.dividaLiquida ?? 0) < 0 &&
            " A barra abaixo da linha é caixa líquido: a empresa tem mais caixa que dívida."}
        </p>
      )}
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
  // Qual camada barrou a contagem de acoes. Dizer qual foi e melhor que um
  // travessao mudo: o numero nao sumiu por acaso, e da para conferir.
  const reprovada = indicadores.conferencias.find((c) => !c.passou);

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

      {reprovada && (
        <p className="pt-2 text-[11px] leading-relaxed text-tinta-3">
          A quantidade de ações que a CVM publica não passou na conferência:{" "}
          {reprovada.porque}. Os múltiplos que dividem por ação ficam de fora —
          o resto do balanço vale.
        </p>
      )}

      {indicadores.escalaCorrigida && (
        <p className="pt-2 text-[11px] leading-relaxed text-tinta-3">
          A CVM publicou a quantidade de ações desta empresa em milhares.
          Corrigida e reconferida antes de entrar nas contas.
        </p>
      )}

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
        <GraficosDoTrimestre indicadores={indicadores} />
      </div>

      <p className="pb-3 text-[11px] leading-relaxed text-tinta-3">
        {ehBanco
          ? "Banco: EBITDA, dívida líquida e margem não se aplicam a esta estrutura de balanço."
          : "Dados da CVM. O EBITDA é calculado (resultado operacional + depreciação), e pode diferir do EBITDA ajustado que a empresa divulga."}
      </p>
    </div>
  );
}
