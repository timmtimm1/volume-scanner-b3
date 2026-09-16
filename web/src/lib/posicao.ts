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
 */

export class OperacaoInvalida extends Error {}

export type TipoDeOperacao = "compra" | "venda";

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

/** Arredonda para 2 casas, na base das colunas `numeric(*, 2)`. */
function r2(v: number): number {
  return Math.round((v + Number.EPSILON) * 100) / 100;
}

/** Arredonda para 6 casas, na base de `preco_medio_apos numeric(18, 6)`. */
function r6(v: number): number {
  return Math.round((v + Number.EPSILON) * 1_000_000) / 1_000_000;
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
 * Preco com no maximo 2 casas decimais -- a precisao de `trade_operacoes.preco
 * numeric(12, 2)`. Comparar contra o arredondado evita que `38.209999...` de
 * ponto flutuante passe como se tivesse 2 casas.
 */
function precoComDuasCasas(v: number): boolean {
  return Math.abs(v - r2(v)) < 1e-9;
}

/**
 * Valida e normaliza os campos de uma operacao. Lanca `OperacaoInvalida` com
 * mensagem em portugues (sem acento) quando algo nao bate.
 */
export function validarCampos(entrada: EntradaDeOperacao): OperacaoValidada {
  const tipo = entrada.tipo;
  if (tipo !== "compra" && tipo !== "venda") {
    throw new OperacaoInvalida("tipo tem de ser 'compra' ou 'venda'");
  }

  const data = String(entrada.data ?? "");
  if (!dataValida(data)) {
    throw new OperacaoInvalida("data fora do formato AAAA-MM-DD ou invalida no calendario");
  }

  const quantidade = Number(entrada.quantidade);
  if (!Number.isInteger(quantidade) || quantidade <= 0) {
    throw new OperacaoInvalida("quantidade tem de ser um inteiro positivo");
  }

  const preco = Number(entrada.preco);
  if (!Number.isFinite(preco) || preco <= 0) {
    throw new OperacaoInvalida("preco tem de ser um numero positivo");
  }
  if (!precoComDuasCasas(preco)) {
    throw new OperacaoInvalida("preco aceita no maximo 2 casas decimais");
  }

  return { tipo, data, quantidade, preco };
}

export type OperacaoOrdenavel = {
  id: number;
  tipo: TipoDeOperacao;
  data: string;
  quantidade: number;
  preco: number;
};

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
};

/**
 * Aplica a sequencia de operacoes de um trade e devolve o estado apos cada
 * uma. Mesma conta que o `*_apos` de cada linha de `trade_operacoes` guarda.
 *
 * Ordena por (data, id) antes de aplicar: e a mesma ordem que `marcar_a_mercado`
 * usa no Python (merge_asof por data, desempate no maior id).
 */
export function aplicarOperacoes<T extends OperacaoOrdenavel>(
  operacoes: T[],
): ResultadoDaAplicacao<T> {
  if (operacoes.length === 0) {
    throw new OperacaoInvalida("trade sem nenhuma operacao");
  }

  const ordenadas = [...operacoes].sort(
    (a, b) => a.data.localeCompare(b.data) || a.id - b.id,
  );

  if (ordenadas[0].tipo !== "compra") {
    throw new OperacaoInvalida("a primeira operacao de um trade tem de ser uma compra");
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
      custoComprado = r2(custoComprado + op.quantidade * op.preco);
      precoMedio = r6(
        (quantidade * precoMedio + op.quantidade * op.preco) / (quantidade + op.quantidade),
      );
      quantidade += op.quantidade;
    } else {
      if (op.quantidade > quantidade) {
        throw new OperacaoInvalida(
          `venda de ${op.quantidade} maior que a posicao de ${quantidade} em ${op.data}`,
        );
      }
      realizado = r2(realizado + op.quantidade * (op.preco - precoMedio));
      quantidade -= op.quantidade;
    }

    estados.push({ quantidade, precoMedio, custoComprado, realizado });
    if (quantidade === 0) encerradoNaOperacao = i;
  }

  return {
    ordenadas,
    estados,
    abertoEm: ordenadas[0].data,
    encerradoEm: quantidade === 0 ? ordenadas[ordenadas.length - 1].data : null,
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
