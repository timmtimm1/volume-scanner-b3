/**
 * A regua do grafico, estilo Profit: medir o preco de um nivel a partir de
 * agora, ou o movimento entre o inicio e a ponta de um gesto (clique + clique
 * no mouse, toque + arraste no touch). O calculo puro, sem React nem
 * lightweight-charts.
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
 * Mede a distancia de "agora" ate um nivel -- o preco do ponto final de uma
 * medicao fixada, no painel da regua. `trade`, quando presente e com
 * quantidade positiva, tambem mede o efeito no trade aberto do papel -- mesma
 * formula de `marcarAgora` em `posicao.ts`, aplicada ao preco do nivel em vez
 * do preco de agora.
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

/**
 * Um ponto da regua: o indice logico da barra tocada (nao a data -- o mesmo
 * indice que `timeScale().coordinateToLogical` devolve) e o preco tocado.
 */
export type PontoDaRegua = { indice: number; preco: number };

export type ResultadoDoMovimento = {
  variacaoPct: number;
  porAcao: number;
  /** `|fim.indice - inicio.indice|` -- quantas barras entre os dois pontos. */
  candles: number;
};

/**
 * Mede o movimento de um gesto da regua, sempre do inicio para a ponta --
 * nunca reordenado por data ou indice, diferente da regua antiga. Arrastar
 * para a esquerda (ponta com indice menor que o inicio) vale igual: e a
 * mesma leitura do Profit, onde a regua mede o gesto, nao o tempo.
 */
export function medirMovimento(entrada: {
  inicio: PontoDaRegua;
  fim: PontoDaRegua;
}): ResultadoDoMovimento {
  const { inicio, fim } = entrada;
  const porAcao = fim.preco - inicio.preco;
  const variacaoPct = inicio.preco !== 0 ? porAcao / inicio.preco : 0;
  const candles = Math.abs(fim.indice - inicio.indice);
  return { variacaoPct, porAcao, candles };
}
