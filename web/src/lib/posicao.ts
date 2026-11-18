/**
 * Posicao de um trade real (compras e vendas parciais) e sua marcacao a
 * mercado -- o calculo puro, sem banco.
 *
 * Modulo puro de proposito: sem import de runtime (so `import type`), porque
 * e testado com `node --experimental-strip-types`, sem bundler nenhum no
 * meio (veja `medias.test.mjs`). Quem grava a operacao (`trades.ts`) e quem
 * chama isto dentro de uma transacao; este arquivo nao sabe que banco existe.
 *
 * Espelha `src/scanner/trades.py` (`marcar_a_mercado`) e as regras de conta
 * que o comentario de `0006_trades.py` descreve: quem grava a operacao
 * calcula a posicao e guarda nas colunas `*_apos`; o job noturno em Python so
 * le esse estado e marca a mercado. Aqui e o mesmo calculo, do lado de quem
 * grava.
 *
 * O que muda de um mercado para o outro (taxa, casas da quantidade e do preco)
 * chega em `regras` (`regrasDoDiario` de `mercado.ts`). Com as regras da B3
 * (taxa zero, acoes inteiras, centavos) as contas sao exatamente as de antes do
 * diario de cripto.
 */

import type { RegrasDoDiario } from "./mercado";

export class OperacaoInvalida extends Error {}

export type TipoDeOperacao = "compra" | "venda";

/**
 * O lado do trade, dado pela operacao que o abre: "compra" e o trade comprado
 * de sempre; "venda" e a venda a descoberto (so onde `regras.vendido` existe).
 */
export type LadoDoTrade = TipoDeOperacao;

export type EntradaDeOperacao = {
  tipo: unknown;
  data: unknown;
  quantidade: unknown;
  preco: unknown;
};

export type OperacaoValidada = {
  tipo: TipoDeOperacao;
  data: string;
  quantidade: number;
  preco: number;
};

/** Arredonda para `casas` casas decimais. */
function arredondar(v: number, casas: number): number {
  const fator = 10 ** casas;
  return Math.round((v + Number.EPSILON) * fator) / fator;
}

/** Arredonda para 2 casas, na base das colunas de dinheiro `numeric(16, 2)`. */
function r2(v: number): number {
  return arredondar(v, 2);
}

/**
 * Se `v` tem no maximo `casas` casas decimais. A comparacao e contra o
 * arredondado, com folga relativa ao tamanho do numero: `38.209999...` de ponto
 * flutuante passa como 38,21, e 0,123456789 nao passa como 8 casas.
 */
function temAteAsCasas(v: number, casas: number): boolean {
  return Math.abs(v - arredondar(v, casas)) <= Math.abs(v) * 1e-12;
}

const DATA = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Se `aaaa-mm-dd` e uma data de calendario valida (rejeita 2026-02-30). */
function dataValida(texto: string): boolean {
  const m = DATA.exec(texto);
  if (!m) return false;
  const ano = Number(m[1]);
  const mes = Number(m[2]);
  const dia = Number(m[3]);
  const d = new Date(Date.UTC(ano, mes - 1, dia));
  return (
    d.getUTCFullYear() === ano && d.getUTCMonth() === mes - 1 && d.getUTCDate() === dia
  );
}

/**
 * Valida e normaliza os campos de uma operacao. Lanca `OperacaoInvalida` com
 * mensagem em portugues (sem acento) quando algo nao bate. A quantidade e o
 * preco aceitam as casas do mercado: acoes inteiras e centavos na B3, ate 8
 * casas de moeda e 10 de preco em cripto.
 */
export function validarCampos(
  entrada: EntradaDeOperacao,
  regras: RegrasDoDiario,
): OperacaoValidada {
  const tipo = entrada.tipo;
  if (tipo !== "compra" && tipo !== "venda") {
    throw new OperacaoInvalida("tipo tem de ser 'compra' ou 'venda'");
  }

  const data = String(entrada.data ?? "");
  if (!dataValida(data)) {
    throw new OperacaoInvalida("data fora do formato AAAA-MM-DD ou invalida no calendario");
  }

  const quantidade = Number(entrada.quantidade);
  if (regras.casasDaQuantidade === 0) {
    if (!Number.isInteger(quantidade) || quantidade <= 0) {
      throw new OperacaoInvalida("quantidade tem de ser um inteiro positivo");
    }
  } else {
    if (!Number.isFinite(quantidade) || quantidade <= 0) {
      throw new OperacaoInvalida("quantidade tem de ser um numero positivo");
    }
    if (!temAteAsCasas(quantidade, regras.casasDaQuantidade)) {
      throw new OperacaoInvalida(
        `quantidade aceita no maximo ${regras.casasDaQuantidade} casas decimais`,
      );
    }
  }

  const preco = Number(entrada.preco);
  if (!Number.isFinite(preco) || preco <= 0) {
    throw new OperacaoInvalida("preco tem de ser um numero positivo");
  }
  if (!temAteAsCasas(preco, regras.casasDoPreco)) {
    throw new OperacaoInvalida(`preco aceita no maximo ${regras.casasDoPreco} casas decimais`);
  }

  return {
    tipo,
    data,
    quantidade: arredondar(quantidade, regras.casasDaQuantidade),
    preco: arredondar(preco, regras.casasDoPreco),
  };
}

export type OperacaoOrdenavel = {
  id: number;
  tipo: TipoDeOperacao;
  data: string;
  quantidade: number;
  preco: number;
};

/**
 * A posicao depois de uma operacao. Na venda a descoberto a `quantidade` e
 * NEGATIVA (as moedas devidas), e e isso que deixa a mesma formula do
 * resultado -- `realizado + quantidade x (preco - precoMedio)` -- certa nos dois
 * lados: vendido, o resultado cresce quando o preco cai. `precoMedio` e sempre
 * positivo (na venda a descoberto, o preco medio de venda). `custoComprado` e o
 * valor negociado na abertura (compras no comprado, vendas no vendido): a base
 * do percentual.
 */
export type EstadoDaPosicao = {
  quantidade: number;
  precoMedio: number;
  custoComprado: number;
  realizado: number;
};

export type ResultadoDaAplicacao<T extends OperacaoOrdenavel> = {
  /** As operacoes recebidas, ordenadas por (data, id). */
  ordenadas: T[];
  /** `estados[i]` e a posicao depois de `ordenadas[i]`. */
  estados: EstadoDaPosicao[];
  abertoEm: string;
  encerradoEm: string | null;
  /** O lado do trade: o tipo da primeira operacao. */
  lado: LadoDoTrade;
};

/**
 * Aplica a sequencia de operacoes de um trade e devolve o estado apos cada
 * uma. Mesma conta que o `*_apos` de cada linha de `trade_operacoes` guarda.
 *
 * Ordena por (data, id) antes de aplicar: e a mesma ordem que `marcar_a_mercado`
 * usa no Python (merge_asof por data, desempate no maior id).
 *
 * Com taxa (cripto): a compra de q a p custa q x p e deixa q x (1 - taxa) na
 * posicao -- a taxa sai da moeda comprada, como a Binance cobra sem BNB --, e o
 * preco medio e o custo da posicao dividido pelas moedas que ficaram. A venda
 * de q a p realiza q x (p x (1 - taxa) - PM): a taxa sai dos dolares. Sem taxa
 * (B3), as duas contas sao as de sempre.
 *
 * Venda a descoberto (primeira operacao uma venda, so com `regras.vendido`):
 * a venda abre ou aumenta a posicao vendida, a compra recompra. A taxa e a dos
 * futuros, em dolar sobre o valor negociado: a venda de q a p entra no preco
 * medio como p x (1 - taxa), e a recompra de q a p realiza
 * q x (PM - p x (1 + taxa)). As moedas nao mudam com a taxa (nao ha moeda
 * recebida, so a devida).
 */
export function aplicarOperacoes<T extends OperacaoOrdenavel>(
  operacoes: T[],
  regras: RegrasDoDiario,
): ResultadoDaAplicacao<T> {
  if (operacoes.length === 0) {
    throw new OperacaoInvalida("trade sem nenhuma operacao");
  }

  const ordenadas = [...operacoes].sort(
    (a, b) => a.data.localeCompare(b.data) || a.id - b.id,
  );

  const lado: LadoDoTrade = ordenadas[0].tipo;
  if (lado === "venda") {
    // `?? null`: regras sem o campo (de antes da venda a descoberto) nao deixam.
    const vendido = regras.vendido ?? null;
    if (vendido === null) {
      throw new OperacaoInvalida("a primeira operacao de um trade tem de ser uma compra");
    }
    return aplicarVendido(ordenadas, regras, vendido.taxa);
  }

  const estados: EstadoDaPosicao[] = [];
  let quantidade = 0;
  let precoMedio = 0;
  let custoComprado = 0;
  let realizado = 0;
  let encerradoNaOperacao = -1;

  for (let i = 0; i < ordenadas.length; i++) {
    const op = ordenadas[i];

    if (encerradoNaOperacao >= 0) {
      throw new OperacaoInvalida(
        "trade ja encerrado em " +
          ordenadas[encerradoNaOperacao].data +
          ": uma compra depois disso abre outro trade",
      );
    }

    if (op.tipo === "compra") {
      const recebida = arredondar(op.quantidade * (1 - regras.taxa), regras.casasDaPosicao);
      custoComprado = r2(custoComprado + op.quantidade * op.preco);
      precoMedio = arredondar(
        (quantidade * precoMedio + op.quantidade * op.preco) / (quantidade + recebida),
        regras.casasDoPrecoMedio,
      );
      quantidade = arredondar(quantidade + recebida, regras.casasDaPosicao);
    } else {
      // Folga de meia casa da posicao: "vender tudo" com o numero que a tela
      // mostrou nao pode falhar por sujeira de ponto flutuante.
      const folga = 0.5 * 10 ** -regras.casasDaPosicao;
      if (op.quantidade > quantidade + folga) {
        throw new OperacaoInvalida(
          `venda de ${op.quantidade} maior que a posicao de ${quantidade} em ${op.data}`,
        );
      }
      const vendida = Math.min(op.quantidade, quantidade);
      realizado = r2(realizado + vendida * (op.preco * (1 - regras.taxa) - precoMedio));
      quantidade = arredondar(quantidade - vendida, regras.casasDaPosicao);
    }

    estados.push({ quantidade, precoMedio, custoComprado, realizado });
    if (quantidade === 0) encerradoNaOperacao = i;
  }

  return {
    ordenadas,
    estados,
    abertoEm: ordenadas[0].data,
    encerradoEm: quantidade === 0 ? ordenadas[ordenadas.length - 1].data : null,
    lado,
  };
}

/**
 * A venda a descoberto: o espelho de `aplicarOperacoes`. A posicao guardada e
 * negativa; aqui a conta anda com o tamanho dela (`devidas`, positivo) e grava
 * o sinal so no estado.
 */
function aplicarVendido<T extends OperacaoOrdenavel>(
  ordenadas: T[],
  regras: RegrasDoDiario,
  taxa: number,
): ResultadoDaAplicacao<T> {
  const estados: EstadoDaPosicao[] = [];
  let devidas = 0;
  let precoMedio = 0;
  let custoComprado = 0;
  let realizado = 0;
  let encerradoNaOperacao = -1;
  const folga = 0.5 * 10 ** -regras.casasDaPosicao;

  for (let i = 0; i < ordenadas.length; i++) {
    const op = ordenadas[i];

    if (encerradoNaOperacao >= 0) {
      throw new OperacaoInvalida(
        "trade ja encerrado em " +
          ordenadas[encerradoNaOperacao].data +
          ": uma venda depois disso abre outro trade",
      );
    }

    if (op.tipo === "venda") {
      custoComprado = r2(custoComprado + op.quantidade * op.preco);
      precoMedio = arredondar(
        (devidas * precoMedio + op.quantidade * op.preco * (1 - taxa)) / (devidas + op.quantidade),
        regras.casasDoPrecoMedio,
      );
      devidas = arredondar(devidas + op.quantidade, regras.casasDaPosicao);
    } else {
      if (op.quantidade > devidas + folga) {
        throw new OperacaoInvalida(
          `recompra de ${op.quantidade} maior que a posicao vendida de ${devidas} em ${op.data}`,
        );
      }
      const recomprada = Math.min(op.quantidade, devidas);
      realizado = r2(realizado + recomprada * (precoMedio - op.preco * (1 + taxa)));
      devidas = arredondar(devidas - recomprada, regras.casasDaPosicao);
    }

    // `0 - 0` daria -0: o trade zerado tem de comparar igual a 0 em todo lugar.
    estados.push({ quantidade: devidas === 0 ? 0 : -devidas, precoMedio, custoComprado, realizado });
    if (devidas === 0) encerradoNaOperacao = i;
  }

  return {
    ordenadas,
    estados,
    abertoEm: ordenadas[0].data,
    encerradoEm: devidas === 0 ? ordenadas[ordenadas.length - 1].data : null,
    lado: "venda",
  };
}

export type FechamentoDoPapel = {
  data: string;
  close: number;
};

export type EntradaDaMarcacao = {
  /** Operacoes ja ordenadas por (data, id), com o estado apos cada uma. */
  operacoes: { data: string; estado: EstadoDaPosicao }[];
  /** Pregoes (AAAA-MM-DD) em que marcar, ja ordenados. */
  pregoes: string[];
  /** Fechamentos do papel, ordenados por data -- inclui datas antes de `desde`. */
  fechamentos: FechamentoDoPapel[];
  desde: string;
  ate: string;
};

export type SnapshotCalculado = {
  data: string;
  quantidade: number;
  precoMedio: number;
  custoComprado: number;
  realizado: number;
  fechamento: number;
  valorPosicao: number;
  resultado: number;
  semNegocio: boolean;
};

/**
 * Marca a mercado cada pregao de `pregoes` entre `desde` e `ate` (inclusive).
 *
 * Para cada pregao D: o estado e o da ultima operacao com `data <= D` (sem
 * nenhuma, pula D); o fechamento e o ultimo close com `data <= D` (sem
 * nenhum, pula D) -- `semNegocio` marca quando esse close e de uma data
 * anterior a D. Mesma regra do `merge_asof` (direction="backward") do Python.
 */
export function marcarAMercado(entrada: EntradaDaMarcacao): SnapshotCalculado[] {
  const { operacoes, pregoes, fechamentos, desde, ate } = entrada;
  const saida: SnapshotCalculado[] = [];

  let iOp = 0;
  let iClose = 0;
  let estadoAtual: EstadoDaPosicao | null = null;
  let closeAtual: FechamentoDoPapel | null = null;

  for (const d of pregoes) {
    if (d < desde || d > ate) continue;

    while (iOp < operacoes.length && operacoes[iOp].data <= d) {
      estadoAtual = operacoes[iOp].estado;
      iOp++;
    }
    while (iClose < fechamentos.length && fechamentos[iClose].data <= d) {
      closeAtual = fechamentos[iClose];
      iClose++;
    }

    if (estadoAtual === null || closeAtual === null) continue;

    const { quantidade, precoMedio, custoComprado, realizado } = estadoAtual;
    const fechamento = closeAtual.close;

    saida.push({
      data: d,
      quantidade,
      precoMedio,
      custoComprado,
      realizado,
      fechamento,
      valorPosicao: r2(quantidade * fechamento),
      resultado: r2(realizado + quantidade * (fechamento - precoMedio)),
      semNegocio: closeAtual.data !== d,
    });
  }

  return saida;
}

export type MarcacaoDeAgora = {
  /** `realizado + quantidade * (preco - precoMedio)`, ou so `realizado` sem preco. */
  resultado: number;
  /** `resultado / custoComprado`. Null so quando nao ha custo (nunca deveria acontecer). */
  resultadoPct: number | null;
  /**
   * `quantidade * preco` (negativo na venda a descoberto: e o que se deve). Null
   * sem preco ou com a posicao zerada (trade encerrado).
   */
  valor: number | null;
};

/**
 * O "resultado de agora" mostrado na ficha, na lista e no detalhe do trade:
 * o realizado mais o nao realizado ao preco informado.
 *
 * `preco` nulo cobre os dois casos em que nao ha preco de agora para marcar --
 * trade encerrado (a posicao ja esta zerada, entao o termo nao realizado seria
 * zero de qualquer forma) e o raro caso de papel sem nenhuma cotacao nem
 * fechamento disponivel. Quem chama decide qual preco usar (candle de hoje ou
 * o ultimo snapshot); esta funcao so aplica a formula.
 */
export function marcarAgora(estado: EstadoDaPosicao, preco: number | null): MarcacaoDeAgora {
  const { quantidade, precoMedio, custoComprado, realizado } = estado;
  const resultado =
    preco === null ? r2(realizado) : r2(realizado + quantidade * (preco - precoMedio));
  return {
    resultado,
    resultadoPct: custoComprado > 0 ? resultado / custoComprado : null,
    valor: preco !== null && quantidade !== 0 ? r2(quantidade * preco) : null,
  };
}
