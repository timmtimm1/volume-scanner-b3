/**
 * A regua do grafico: medir um nivel a partir de agora, ou o movimento entre
 * dois pontos tocados no candle. O calculo puro, sem React nem lightweight-charts.
 *
 * Modulo puro de proposito: sem import de runtime (so `import type`), porque e
 * testado com `node --experimental-strip-types`, sem bundler nenhum no meio
 * (mesmo padrao de `posicao.ts` e `medias.ts`, veja `posicao.test.mjs`). Por
 * isso o formato do trade e um tipo local igual a `EstadoDaPosicao` de
 * `posicao.ts`, em vez de importado de la -- um import de valor entre modulos
 * quebraria o `node --test`, e aqui so o formato dos campos importa.
 */

import type { Direcao } from "./alertas";

export type TradeDaRegua = {
  quantidade: number;
  precoMedio: number;
  custoComprado: number;
  realizado: number;
};

export type ResultadoDoNivel = {
  agora: number;
  nivel: number;
  /** `(nivel - agora) / agora`. */
  variacaoPct: number;
  /** `nivel - agora`, em reais por acao. */
  porAcao: number;
  /** Para a direcao do alerta: "acima" se nivel > agora, senao "abaixo". */
  direcao: Direcao;
  /** Null sem trade aberto ou com posicao zerada -- nao ha o que medir. */
  trade: {
    /** `quantidade * porAcao`: quanto muda o resultado do trade ate o nivel. */
    ateLa: number;
    /** O trade inteiro (realizado + nao realizado) se o preco fosse o nivel. */
    inteiro: {
      resultado: number;
      /** `resultado / custoComprado`. Null so sem custo (nao deveria acontecer). */
      resultadoPct: number | null;
    };
  } | null;
};

/**
 * Mede a distancia de "agora" ate um nivel tocado no grafico. `trade`, quando
 * presente e com quantidade positiva, tambem mede o efeito no trade aberto do
 * papel -- mesma formula de `marcarAgora` em `posicao.ts`, aplicada ao preco
 * do nivel em vez do preco de agora.
 */
export function medirNivel(entrada: {
  agora: number;
  nivel: number;
  trade?: TradeDaRegua | null;
}): ResultadoDoNivel {
  const { agora, nivel, trade = null } = entrada;
  const porAcao = nivel - agora;
  const variacaoPct = agora !== 0 ? porAcao / agora : 0;
  const direcao: Direcao = nivel > agora ? "acima" : "abaixo";

  let resultadoDoTrade: ResultadoDoNivel["trade"] = null;
  if (trade && trade.quantidade > 0) {
    const ateLa = trade.quantidade * porAcao;
    const resultado = trade.realizado + trade.quantidade * (nivel - trade.precoMedio);
    resultadoDoTrade = {
      ateLa,
      inteiro: {
        resultado,
        resultadoPct: trade.custoComprado > 0 ? resultado / trade.custoComprado : null,
      },
    };
  }

  return { agora, nivel, variacaoPct, porAcao, direcao, trade: resultadoDoTrade };
}

export type PontoDaRegua = { data: string; preco: number };

export type ResultadoDoMovimento = {
  /** Sempre o ponto mais antigo -- em data igual, o primeiro tocado. */
  de: PontoDaRegua;
  /** Sempre o ponto mais novo -- em data igual, o segundo tocado. */
  ate: PontoDaRegua;
  variacaoPct: number;
  porAcao: number;
  /** Quantidade de datas de `datas` em `(de, ate]`. */
  pregoes: number;
};

/**
 * Mede o movimento entre dois pontos tocados no grafico, sempre do mais
 * antigo para o mais novo. Em data igual (dois toques no mesmo pregao), a
 * ordem fica a dos toques -- `a` e sempre o primeiro toque, `b` o segundo.
 */
export function medirMovimento(entrada: {
  a: PontoDaRegua;
  b: PontoDaRegua;
  /** Pregoes conhecidos do grafico, em qualquer ordem -- so para contar. */
  datas: string[];
}): ResultadoDoMovimento {
  const { a, b, datas } = entrada;
  const [de, ate] = a.data <= b.data ? [a, b] : [b, a];
  const pregoes = datas.filter((d) => d > de.data && d <= ate.data).length;
  const porAcao = ate.preco - de.preco;
  const variacaoPct = de.preco !== 0 ? porAcao / de.preco : 0;
  return { de, ate, variacaoPct, porAcao, pregoes };
}
