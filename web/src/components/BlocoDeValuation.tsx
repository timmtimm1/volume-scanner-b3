"use client";

import { useMemo, useState } from "react";
import { numero, reais } from "@/lib/formato";
import {
  ANOS_DE_PROVENTOS,
  type Avaliacao,
  avaliar,
  CONSTANTE_DE_GRAHAM,
  type DadosDoPapel,
  type Metodo,
  NOME_DO_METODO,
  type Premissas,
  RENDIMENTO_DE_BAZIN,
  resumir,
  type Sinal,
  textoDaDiferenca,
} from "@/lib/valuation";

/**
 * O bloco de valuation da ficha: tres contas de "preco justo", cada uma com o
 * seu semaforo, e a conta aberta para quem quiser conferir (pedido de
 * 16/11/2026).
 *
 * O semaforo compara o preco de hoje com o resultado de cada formula. Nao e
 * nota da empresa nem sugestao de compra: e onde o preco esta em relacao a
 * uma conta simples sobre o ultimo balanco.
 */

export const COR_DO_SINAL: Record<Sinal, { luz: string; texto: string; rotulo: string }> = {
  abaixo: { luz: "bg-alta", texto: "text-alta", rotulo: "preço abaixo do justo" },
  perto: { luz: "bg-evento", texto: "text-tinta-2", rotulo: "preço perto do justo" },
  acima: { luz: "bg-baixa", texto: "text-baixa", rotulo: "preço acima do justo" },
};

export function Luz({ sinal }: { sinal: Sinal | null }) {
  return (
    <span
      aria-hidden
      className={`inline-block h-3 w-3 shrink-0 rounded-full ${sinal ? COR_DO_SINAL[sinal].luz : "bg-linha-2"}`}
    />
  );
}

const pct = (v: number, casas = 1) => `${numero(v * 100, casas)}%`;

function Linha({ a }: { a: Avaliacao }) {
  return (
    <li className="flex items-center gap-3 py-2.5">
      <Luz sinal={a.sinal} />
      <span className="w-[104px] shrink-0 text-[14px] font-bold">{NOME_DO_METODO[a.metodo]}</span>
      {a.precoJusto === null ? (
        <span className="min-w-0 flex-1 text-right text-[12px] font-semibold text-tinta-3">
          não se aplica: {a.motivo}
        </span>
      ) : (
        <>
          <span className="num flex-1 whitespace-nowrap text-right text-[15px] font-extrabold">
            {reais(a.precoJusto)}
          </span>
          <span
            className={`num w-[88px] shrink-0 whitespace-nowrap text-right text-[13px] font-bold ${a.sinal ? COR_DO_SINAL[a.sinal].texto : ""}`}
            title={a.sinal ? COR_DO_SINAL[a.sinal].rotulo : undefined}
          >
            {textoDaDiferenca(a.diferenca)}
          </span>
        </>
      )}
    </li>
  );
}

function Deslizante({
  rotulo,
  valor,
  minimo,
  maximo,
  aoMudar,
}: {
  rotulo: string;
  valor: number;
  minimo: number;
  maximo: number;
  aoMudar: (v: number) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="flex items-baseline justify-between text-[12px] font-bold text-tinta-2">
        {rotulo}
        <span className="num text-[14px] font-extrabold text-tinta">{pct(valor)}</span>
      </span>
      <input
        type="range"
        min={minimo * 100}
        max={maximo * 100}
        step={0.5}
        value={Math.round(valor * 1000) / 10}
        onChange={(e) => aoMudar(Number(e.target.value) / 100)}
        className="toque h-8 w-full accent-[var(--acento)]"
      />
    </label>
  );
}

function Conta({ metodo, d, p }: { metodo: Metodo; d: DadosDoPapel; p: Premissas }) {
  const lpa = d.lucroPorAcao;
  const vpa = d.valorPatrimonialPorAcao;
  if (metodo === "graham") {
    return (
      <p>
        <strong className="font-extrabold text-tinta">Graham.</strong> Raiz de{" "}
        {numero(CONSTANTE_DE_GRAHAM, 1)} × lucro por ação ({reais(lpa)}) × valor patrimonial por
        ação ({reais(vpa)}). O 22,5 é o teto que Benjamin Graham aceitava pagar: 15 vezes o lucro
        e 1,5 vez o patrimônio. Não funciona para empresa com prejuízo.
      </p>
    );
  }
  if (metodo === "bazin") {
    return (
      <p>
        <strong className="font-extrabold text-tinta">Bazin.</strong> Provento médio por ação nos
        últimos {ANOS_DE_PROVENTOS} anos ({reais(d.proventoMedio)} por ano) dividido por{" "}
        {pct(RENDIMENTO_DE_BAZIN, 0)}: o preço em que esse provento rende 6% ao ano, o mínimo que
        Décio Bazin exigia. Olha só o que a empresa pagou, não o que ela lucrou; desdobramento
        recente distorce a média.
      </p>
    );
  }
  return (
    <p>
      <strong className="font-extrabold text-tinta">Fluxo de caixa.</strong> Parte do lucro por
      ação de hoje ({reais(lpa)}), faz ele crescer {pct(p.crescimento)} ao ano por {p.anos} anos e{" "}
      {pct(p.perpetuidade, 0)} ao ano daí em diante, e traz tudo a valor de hoje com{" "}
      {pct(p.desconto)} ao ano. É a versão mais simples do método: usa o lucro como se fosse o
      caixa do acionista, sem separar investimento nem dívida. Muda muito com as duas premissas;
      mexa nelas abaixo.
    </p>
  );
}

type Props = {
  dados: DadosDoPapel;
  /** As premissas com que o fluxo de caixa sai calculado antes de qualquer ajuste. */
  padrao: Premissas;
  /** De onde veio o crescimento padrao, para dizer na tela. */
  crescimentoMedido: boolean;
};

export function BlocoDeValuation({ dados, padrao, crescimentoMedido }: Props) {
  const [premissas, setPremissas] = useState(padrao);
  const avaliacoes = useMemo(() => avaliar(dados, premissas), [dados, premissas]);
  const resumo = resumir(avaliacoes);
  const mexeu =
    premissas.crescimento !== padrao.crescimento || premissas.desconto !== padrao.desconto;
  const temDcf = dados.acoesConfiaveis && (dados.lucroPorAcao ?? 0) > 0;

  return (
    <section className="flex flex-col gap-2 rounded-2xl bg-painel-2 p-4">
      <header className="flex flex-wrap items-baseline justify-between gap-x-3">
        <h3 className="text-[15px] font-extrabold">Preço justo</h3>
        <span className="num text-[12px] font-semibold text-tinta-3">
          preço hoje {reais(dados.preco)}
        </span>
      </header>

      <ul className="flex flex-col divide-y divide-linha">
        {avaliacoes.map((a) => (
          <Linha key={a.metodo} a={a} />
        ))}
      </ul>

      <p className="text-[13px] font-bold text-tinta-2">{resumo.texto}</p>

      <details className="group">
        <summary className="toque flex cursor-pointer list-none items-center text-[13px] font-bold text-acento [&::-webkit-details-marker]:hidden">
          ver a conta de cada método e ajustar o fluxo de caixa
          <span aria-hidden className="ml-2 transition-transform group-open:rotate-90">
            ›
          </span>
        </summary>
        <div className="flex flex-col gap-3 pt-3 text-[12px] font-semibold leading-relaxed text-tinta-3">
          <Conta metodo="graham" d={dados} p={premissas} />
          <Conta metodo="bazin" d={dados} p={premissas} />
          <Conta metodo="dcf" d={dados} p={premissas} />

          {temDcf && (
            <div className="flex flex-col gap-3 rounded-xl bg-painel p-3">
              <Deslizante
                rotulo="Crescimento do lucro nos próximos 5 anos"
                valor={premissas.crescimento}
                minimo={0}
                maximo={0.25}
                aoMudar={(crescimento) => setPremissas((p) => ({ ...p, crescimento }))}
              />
              <Deslizante
                rotulo="Taxa de desconto"
                valor={premissas.desconto}
                minimo={0.08}
                maximo={0.3}
                aoMudar={(desconto) => setPremissas((p) => ({ ...p, desconto }))}
              />
              <p>
                Padrão: crescimento de {pct(padrao.crescimento)} (
                {crescimentoMedido
                  ? "o do lucro da própria empresa nos últimos 2 anos, limitado entre 0% e 15%"
                  : "sem histórico suficiente para medir; vale o de longo prazo"}
                ) e desconto de {pct(padrao.desconto)} (o juro do Tesouro prefixado de 10 anos
                mais 5 pontos por ser ação).
              </p>
              {mexeu && (
                <button
                  type="button"
                  onClick={() => setPremissas(padrao)}
                  className="toque h-9 self-start rounded-full border border-linha-2 px-4 text-[12px] font-bold text-tinta-2 hover:text-tinta"
                >
                  Voltar ao padrão
                </button>
              )}
            </div>
          )}

          <p>
            O ponto colorido compara o preço de hoje com o resultado de cada fórmula: verde, mais
            de 10% abaixo; vermelho, mais de 10% acima; amarelo, perto. São contas sobre o último
            balanço publicado, não análise da empresa nem recomendação. É comum os três
            discordarem.
          </p>
        </div>
      </details>
    </section>
  );
}
