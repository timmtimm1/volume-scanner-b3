/**
 * Trades reais (compras e vendas parciais de uma acao) do lado do site.
 *
 * Mesma divisao de responsabilidade de `alertas.ts`: e a unica parte do
 * sistema, alem dos alertas, em que o navegador escreve no banco, entao a
 * validacao mora aqui, nao so na rota. Toda funcao daqui e chamada apenas
 * depois de `ehDono()`.
 *
 * Decisao de arquitetura (repetida do comentario de `0006_trades.py`): quem
 * grava a operacao -- este modulo -- calcula a posicao e guarda o estado nas
 * colunas `*_apos` de cada linha; e, ao gravar, reescreve os snapshots
 * retroativos daquele trade. O job noturno em Python (`scanner.trades`) so
 * LE esse estado e marca a mercado os pregoes novos -- nunca recalcula media.
 * `posicao.ts` e o calculo puro dos dois lados desta divisao; aqui e so
 * leitura/escrita do Postgres em cima dele.
 */

import type { PoolClient } from "pg";
import { conexaoDeAlertas } from "./db";
import { diaNaB3 } from "./candle-de-hoje";
import {
  OperacaoInvalida,
  aplicarOperacoes,
  marcarAMercado,
  validarCampos,
  type EntradaDeOperacao,
  type OperacaoOrdenavel,
  type TipoDeOperacao,
} from "./posicao";
import { TICKER } from "./ticker";

export { OperacaoInvalida } from "./posicao";

export type OperacaoDoTrade = {
  id: number;
  tradeId: number;
  tipo: TipoDeOperacao;
  data: string;
  quantidade: number;
  preco: number;
  quantidadeApos: number;
  precoMedioApos: number;
  custoCompradoApos: number;
  realizadoApos: number;
};

export type SnapshotDoTrade = {
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

export type TradeResumo = {
  id: number;
  ticker: string;
  abertoEm: string;
  encerradoEm: string | null;
  /** Estado da ULTIMA operacao -- a posicao agora, sem marcar a mercado. */
  quantidade: number;
  precoMedio: number;
  custoComprado: number;
  realizado: number;
  /** O snapshot mais recente gravado, ou null se nenhum pregao ainda marcou. */
  ultimoSnapshot: SnapshotDoTrade | null;
  operacoes: OperacaoDoTrade[];
};

export type TradeDetalhe = TradeResumo & {
  /** Ordem crescente de data. */
  snapshots: SnapshotDoTrade[];
};

// Mesmo helper de `alertas.ts`, repetido aqui e nao importado: cada lado que
// le data do Postgres precisa dele, e `alertas.ts` nao o exporta -- e
// deliberadamente pequeno, sem estado, sem razao para virar dependencia
// cruzada entre os dois modulos de escrita.
function dia(v: Date | string): string {
  if (v instanceof Date) {
    // Sem toISOString: ele converte para UTC e pode recuar um dia.
    const m = `${v.getMonth() + 1}`.padStart(2, "0");
    const d = `${v.getDate()}`.padStart(2, "0");
    return `${v.getFullYear()}-${m}-${d}`;
  }
  return String(v).slice(0, 10);
}

function comoObjeto(v: unknown): Record<string, unknown> {
  return v !== null && typeof v === "object" ? (v as Record<string, unknown>) : {};
}

function ehViolacaoDeUnicidade(erro: unknown): boolean {
  return Boolean(
    erro &&
      typeof erro === "object" &&
      "code" in erro &&
      (erro as { code?: unknown }).code === "23505",
  );
}

function maxData(datas: (string | null)[]): string {
  const validas = datas.filter((d): d is string => d !== null);
  if (validas.length === 0) throw new Error("maxData sem nenhuma data valida");
  return validas.reduce((a, b) => (b > a ? b : a));
}

function minData(datas: (string | null)[]): string {
  const validas = datas.filter((d): d is string => d !== null);
  if (validas.length === 0) throw new Error("minData sem nenhuma data valida");
  return validas.reduce((a, b) => (b < a ? b : a));
}

type LinhaTrade = {
  id: string | number;
  ticker: string;
  aberto_em: Date | string;
  encerrado_em: Date | string | null;
};

type LinhaOperacao = {
  id: string | number;
  trade_id: string | number;
  tipo: string;
  data: Date | string;
  quantidade: number;
  preco: string | number;
  quantidade_apos: number;
  preco_medio_apos: string | number;
  custo_comprado_apos: string | number;
  realizado_apos: string | number;
};

type LinhaSnapshot = {
  trade_id: string | number;
  trade_date: Date | string;
  quantidade: number;
  preco_medio: string | number;
  custo_comprado: string | number;
  realizado: string | number;
  fechamento: string | number;
  valor_posicao: string | number;
  resultado: string | number;
  sem_negocio: boolean;
};

const COLUNAS_OPERACAO = `id, trade_id, tipo, data, quantidade, preco,
  quantidade_apos, preco_medio_apos, custo_comprado_apos, realizado_apos`;

const COLUNAS_SNAPSHOT = `trade_id, trade_date, quantidade, preco_medio, custo_comprado,
  realizado, fechamento, valor_posicao, resultado, sem_negocio`;

function paraOperacao(r: LinhaOperacao): OperacaoDoTrade {
  return {
    id: Number(r.id),
    tradeId: Number(r.trade_id),
    tipo: r.tipo === "compra" ? "compra" : "venda",
    data: dia(r.data),
    quantidade: Number(r.quantidade),
    preco: Number(r.preco),
    quantidadeApos: Number(r.quantidade_apos),
    precoMedioApos: Number(r.preco_medio_apos),
    custoCompradoApos: Number(r.custo_comprado_apos),
    realizadoApos: Number(r.realizado_apos),
  };
}

function paraSnapshot(r: LinhaSnapshot): SnapshotDoTrade {
  return {
    data: dia(r.trade_date),
    quantidade: Number(r.quantidade),
    precoMedio: Number(r.preco_medio),
    custoComprado: Number(r.custo_comprado),
    realizado: Number(r.realizado),
    fechamento: Number(r.fechamento),
    valorPosicao: Number(r.valor_posicao),
    resultado: Number(r.resultado),
    semNegocio: r.sem_negocio,
  };
}

function montarResumo(
  r: LinhaTrade,
  operacoes: OperacaoDoTrade[],
  ultimoSnapshot: SnapshotDoTrade | null,
): TradeResumo {
  const ultimaOp = operacoes.at(-1);
  return {
    id: Number(r.id),
    ticker: r.ticker,
    abertoEm: dia(r.aberto_em),
    encerradoEm: r.encerrado_em === null ? null : dia(r.encerrado_em),
    quantidade: ultimaOp?.quantidadeApos ?? 0,
    precoMedio: ultimaOp?.precoMedioApos ?? 0,
    custoComprado: ultimaOp?.custoCompradoApos ?? 0,
    realizado: ultimaOp?.realizadoApos ?? 0,
    ultimoSnapshot,
    operacoes,
  };
}

/** Trades, abertos primeiro; entre encerrados, os mais recentes primeiro. */
export async function listarTrades(ticker?: string): Promise<TradeResumo[]> {
  const pool = conexaoDeAlertas();
  const filtro = ticker ? "WHERE ticker = $1" : "";
  const { rows: tradeRows } = await pool.query<LinhaTrade>(
    `SELECT id, ticker, aberto_em, encerrado_em
       FROM volume_scanner.trades
       ${filtro}
      ORDER BY (encerrado_em IS NULL) DESC, COALESCE(encerrado_em, aberto_em) DESC, id DESC`,
    ticker ? [ticker.toUpperCase()] : [],
  );
  if (tradeRows.length === 0) return [];

  const ids = tradeRows.map((r) => Number(r.id));
  const [{ rows: opRows }, { rows: snapRows }] = await Promise.all([
    pool.query<LinhaOperacao>(
      `SELECT ${COLUNAS_OPERACAO} FROM volume_scanner.trade_operacoes
        WHERE trade_id = ANY($1) ORDER BY trade_id, data, id`,
      [ids],
    ),
    // DISTINCT ON traz so o snapshot mais recente de cada trade, numa consulta
    // em vez de uma por trade.
    pool.query<LinhaSnapshot>(
      `SELECT DISTINCT ON (trade_id) ${COLUNAS_SNAPSHOT}
         FROM volume_scanner.trade_snapshots
        WHERE trade_id = ANY($1)
        ORDER BY trade_id, trade_date DESC`,
      [ids],
    ),
  ]);

  const operacoesPorTrade = new Map<number, OperacaoDoTrade[]>();
  for (const r of opRows) {
    const op = paraOperacao(r);
    const lista = operacoesPorTrade.get(op.tradeId);
    if (lista) lista.push(op);
    else operacoesPorTrade.set(op.tradeId, [op]);
  }
  const ultimoSnapshotPorTrade = new Map<number, SnapshotDoTrade>();
  for (const r of snapRows) ultimoSnapshotPorTrade.set(Number(r.trade_id), paraSnapshot(r));

  return tradeRows.map((r) =>
    montarResumo(
      r,
      operacoesPorTrade.get(Number(r.id)) ?? [],
      ultimoSnapshotPorTrade.get(Number(r.id)) ?? null,
    ),
  );
}

export async function detalharTrade(id: number): Promise<TradeDetalhe | null> {
  const pool = conexaoDeAlertas();
  const { rows } = await pool.query<LinhaTrade>(
    `SELECT id, ticker, aberto_em, encerrado_em FROM volume_scanner.trades WHERE id = $1`,
    [id],
  );
  if (rows.length === 0) return null;

  const [{ rows: opRows }, { rows: snapRows }] = await Promise.all([
    pool.query<LinhaOperacao>(
      `SELECT ${COLUNAS_OPERACAO} FROM volume_scanner.trade_operacoes
        WHERE trade_id = $1 ORDER BY data, id`,
      [id],
    ),
    pool.query<LinhaSnapshot>(
      `SELECT ${COLUNAS_SNAPSHOT} FROM volume_scanner.trade_snapshots
        WHERE trade_id = $1 ORDER BY trade_date`,
      [id],
    ),
  ]);

  const operacoes = opRows.map(paraOperacao);
  const snapshots = snapRows.map(paraSnapshot);
  const resumo = montarResumo(rows[0], operacoes, snapshots.at(-1) ?? null);
  return { ...resumo, snapshots };
}

/** BEGIN/COMMIT/ROLLBACK ao redor de `fn`, com o client sempre devolvido ao pool. */
async function comTransacao<T>(fn: (client: PoolClient) => Promise<T>): Promise<T> {
  const client = await conexaoDeAlertas().connect();
  try {
    await client.query("BEGIN");
    const resultado = await fn(client);
    await client.query("COMMIT");
    return resultado;
  } catch (erro) {
    await client.query("ROLLBACK");
    throw erro;
  } finally {
    client.release();
  }
}

/**
 * Reconta a posicao do trade a partir de todas as suas operacoes, grava o
 * estado (`*_apos`) de cada uma, ajusta `aberto_em`/`encerrado_em` e
 * reescreve os snapshots a partir de `desde`. Roda dentro da transacao do
 * chamador -- qualquer erro aqui (posicao invalida, trade aberto duplicado)
 * desfaz a operacao inteira, nao so o recalculo.
 */
async function recalcular(client: PoolClient, tradeId: number, desde: string): Promise<void> {
  const { rows: tradeRows } = await client.query<{ ticker: string }>(
    `SELECT ticker FROM volume_scanner.trades WHERE id = $1`,
    [tradeId],
  );
  if (tradeRows.length === 0) {
    throw new Error(`trade ${tradeId} nao encontrado ao recalcular`);
  }
  const ticker = tradeRows[0].ticker;

  const { rows: opRows } = await client.query<LinhaOperacao>(
    `SELECT ${COLUNAS_OPERACAO} FROM volume_scanner.trade_operacoes
      WHERE trade_id = $1 ORDER BY data, id`,
    [tradeId],
  );
  const operacoes: OperacaoOrdenavel[] = opRows.map((r) => ({
    id: Number(r.id),
    tipo: r.tipo === "compra" ? "compra" : "venda",
    data: dia(r.data),
    quantidade: Number(r.quantidade),
    preco: Number(r.preco),
  }));

  // Se a lista estiver vazia ou a sequencia for invalida, `aplicarOperacoes`
  // lanca `OperacaoInvalida` e o catch de `comTransacao` desfaz tudo -- nada
  // de posicao errada fica gravado.
  const { ordenadas, estados, abertoEm, encerradoEm } = aplicarOperacoes(operacoes);

  for (let i = 0; i < ordenadas.length; i++) {
    const est = estados[i];
    await client.query(
      `UPDATE volume_scanner.trade_operacoes
          SET quantidade_apos = $1, preco_medio_apos = $2,
              custo_comprado_apos = $3, realizado_apos = $4
        WHERE id = $5`,
      [est.quantidade, est.precoMedio, est.custoComprado, est.realizado, ordenadas[i].id],
    );
  }

  try {
    await client.query(
      `UPDATE volume_scanner.trades SET aberto_em = $1, encerrado_em = $2 WHERE id = $3`,
      [abertoEm, encerradoEm, tradeId],
    );
  } catch (erro) {
    // Indice parcial unico (um aberto por ticker): editar/apagar uma
    // operacao pode reabrir um trade encerrado -- e ai colidir com outro
    // trade do mesmo papel que ja esta aberto.
    if (ehViolacaoDeUnicidade(erro)) {
      throw new OperacaoInvalida(`ja existe um trade aberto de ${ticker}`);
    }
    throw erro;
  }

  const { rows: extremos } = await client.query<{ minima: Date | null; maxima: Date | null }>(
    `SELECT MIN(trade_date) AS minima, MAX(trade_date) AS maxima FROM volume_scanner.daily_bars`,
  );
  const globalMin = extremos[0]?.minima ? dia(extremos[0].minima) : null;
  const globalMax = extremos[0]?.maxima ? dia(extremos[0].maxima) : null;

  if (globalMin === null || globalMax === null) {
    // Banco sem carga nenhuma de barras: nao ha fechamento para marcar nada,
    // igual ao `bars.empty` do lado Python. So sobra apagar o que existia.
    await client.query(
      `DELETE FROM volume_scanner.trade_snapshots WHERE trade_id = $1 AND trade_date >= $2`,
      [tradeId, desde],
    );
    return;
  }

  // Apaga o que ficou invalido: tudo dentro do intervalo recalculado, mais
  // qualquer snapshot fora dos novos limites do trade (a edicao pode ter
  // encurtado o trade nas duas pontas).
  await client.query(
    `DELETE FROM volume_scanner.trade_snapshots
       WHERE trade_id = $1
         AND (trade_date >= $2 OR trade_date < $3
              OR ($4::date IS NOT NULL AND trade_date > $4::date))`,
    [tradeId, maxData([desde, globalMin]), abertoEm, encerradoEm],
  );

  const inicio = maxData([desde, abertoEm, globalMin]);
  const fim = minData([encerradoEm ?? globalMax, globalMax]);
  if (inicio > fim) return; // nada de pregao no intervalo recalculado

  const { rows: pregaoRows } = await client.query<{ trade_date: Date }>(
    `SELECT DISTINCT trade_date FROM volume_scanner.daily_bars
      WHERE trade_date >= $1 AND trade_date <= $2 ORDER BY trade_date`,
    [inicio, fim],
  );
  const pregoes = pregaoRows.map((r) => dia(r.trade_date));

  // Fechamentos so do papel do trade, mas sem piso em `inicio`: o ffill do
  // primeiro pregao do intervalo pode precisar de um close anterior.
  const { rows: closeRows } = await client.query<{ trade_date: Date; close: string | number }>(
    `SELECT trade_date, close FROM volume_scanner.daily_bars
      WHERE ticker = $1 AND trade_date <= $2 ORDER BY trade_date`,
    [ticker, fim],
  );
  const fechamentos = closeRows.map((r) => ({ data: dia(r.trade_date), close: Number(r.close) }));

  const operacoesParaMarcar = ordenadas.map((op, i) => ({ data: op.data, estado: estados[i] }));
  const snapshots = marcarAMercado({
    operacoes: operacoesParaMarcar,
    pregoes,
    fechamentos,
    desde: inicio,
    ate: fim,
  });

  if (snapshots.length === 0) return;

  // Um INSERT so, com as colunas como arrays: um trade registrado com meses de
  // atraso gera centenas de snapshots, e uma ida ao Neon por linha deixaria o
  // "salvar" esperando segundos.
  await client.query(
    `INSERT INTO volume_scanner.trade_snapshots
       (trade_id, trade_date, quantidade, preco_medio, custo_comprado,
        realizado, fechamento, valor_posicao, resultado, sem_negocio)
     SELECT $1, * FROM unnest(
       $2::date[], $3::int[], $4::numeric[], $5::numeric[],
       $6::numeric[], $7::numeric[], $8::numeric[], $9::numeric[], $10::boolean[])
     ON CONFLICT (trade_id, trade_date) DO UPDATE SET
       quantidade = EXCLUDED.quantidade, preco_medio = EXCLUDED.preco_medio,
       custo_comprado = EXCLUDED.custo_comprado, realizado = EXCLUDED.realizado,
       fechamento = EXCLUDED.fechamento, valor_posicao = EXCLUDED.valor_posicao,
       resultado = EXCLUDED.resultado, sem_negocio = EXCLUDED.sem_negocio`,
    [
      tradeId,
      snapshots.map((s) => s.data),
      snapshots.map((s) => s.quantidade),
      snapshots.map((s) => s.precoMedio),
      snapshots.map((s) => s.custoComprado),
      snapshots.map((s) => s.realizado),
      snapshots.map((s) => s.fechamento),
      snapshots.map((s) => s.valorPosicao),
      snapshots.map((s) => s.resultado),
      snapshots.map((s) => s.semNegocio),
    ],
  );
}

/**
 * A data de uma operacao precisa ser um pregao que ja aconteceu. Vale para
 * registrar e para editar: mover uma operacao para um sabado quebraria a
 * marcacao do mesmo jeito que registra-la ali.
 */
async function garantirPregao(client: PoolClient, data: string): Promise<void> {
  const hoje = diaNaB3(new Date());
  if (data > hoje) throw new OperacaoInvalida("data da operacao nao pode ser futura");

  const { rows } = await client.query<{ existe: boolean }>(
    `SELECT EXISTS (SELECT 1 FROM volume_scanner.daily_bars WHERE trade_date = $1) AS existe`,
    [data],
  );
  const [ano, mes, diaDoMes] = data.split("-").map(Number);
  const semana = new Date(Date.UTC(ano, mes - 1, diaDoMes)).getUTCDay();
  const eDiaUtil = semana >= 1 && semana <= 5;
  // A barra de hoje so entra a noite (carga do fim do pregao): sem ela no
  // banco, um dia util de hoje ainda vale como pregao.
  if (!rows[0].existe && !(data === hoje && eDiaUtil)) {
    throw new OperacaoInvalida(`${data} nao e um pregao da B3`);
  }
}

/**
 * Registra uma compra ou venda. Compra sem trade aberto do papel abre um;
 * venda sem trade aberto e erro -- nao ha posicao para vender.
 */
export async function registrarOperacao(entrada: unknown): Promise<TradeDetalhe> {
  const e = comoObjeto(entrada);

  const ticker = String(e.ticker ?? "").toUpperCase();
  // Validado aqui e nao so na rota: e o ponto de entrada do dado, e o ticker
  // salvo entra depois em consultas por (ticker, data) do resto do site.
  if (!TICKER.test(ticker)) throw new OperacaoInvalida("ticker fora do formato da B3");

  const pool = conexaoDeAlertas();
  const { rows: papelRows } = await pool.query<{ existe: boolean }>(
    `SELECT EXISTS (SELECT 1 FROM volume_scanner.daily_bars WHERE ticker = $1) AS existe`,
    [ticker],
  );
  if (!papelRows[0].existe) {
    throw new OperacaoInvalida(`papel ${ticker} nao tem barra nenhuma carregada`);
  }

  const { tipo, data, quantidade, preco } = validarCampos(e as EntradaDeOperacao);

  const tradeId = await comTransacao(async (client) => {
    await garantirPregao(client, data);

    const { rows: abertoRows } = await client.query<{ id: string }>(
      `SELECT id FROM volume_scanner.trades
        WHERE ticker = $1 AND encerrado_em IS NULL FOR UPDATE`,
      [ticker],
    );

    let id: number;
    if (abertoRows.length > 0) {
      id = Number(abertoRows[0].id);
    } else {
      if (tipo === "venda") {
        throw new OperacaoInvalida(`nao ha trade aberto de ${ticker} para vender`);
      }
      try {
        const { rows: novoRows } = await client.query<{ id: string }>(
          `INSERT INTO volume_scanner.trades (ticker, aberto_em) VALUES ($1, $2) RETURNING id`,
          [ticker, data],
        );
        id = Number(novoRows[0].id);
      } catch (erro) {
        if (ehViolacaoDeUnicidade(erro)) {
          throw new OperacaoInvalida(`ja existe um trade aberto de ${ticker}`);
        }
        throw erro;
      }
    }

    // *_apos entram provisorios em 0: `recalcular` reescreve com o estado
    // real logo em seguida, na mesma transacao.
    await client.query(
      `INSERT INTO volume_scanner.trade_operacoes
         (trade_id, tipo, data, quantidade, preco,
          quantidade_apos, preco_medio_apos, custo_comprado_apos, realizado_apos)
       VALUES ($1, $2, $3, $4, $5, 0, 0, 0, 0)`,
      [id, tipo, data, quantidade, preco],
    );

    await recalcular(client, id, data);
    return id;
  });

  const detalhe = await detalharTrade(tradeId);
  if (!detalhe) throw new Error("trade sumiu logo depois de gravado");
  return detalhe;
}

/** Edita uma operacao existente. O ticker do trade nao muda. */
export async function editarOperacao(id: number, campos: unknown): Promise<TradeDetalhe | null> {
  const c = comoObjeto(campos);

  const tradeId = await comTransacao(async (client) => {
    const { rows } = await client.query<LinhaOperacao>(
      `SELECT ${COLUNAS_OPERACAO} FROM volume_scanner.trade_operacoes
        WHERE id = $1 FOR UPDATE`,
      [id],
    );
    if (rows.length === 0) return null;
    const atual = paraOperacao(rows[0]);

    const normalizado = validarCampos({
      tipo: c.tipo ?? atual.tipo,
      data: c.data ?? atual.data,
      quantidade: c.quantidade ?? atual.quantidade,
      preco: c.preco ?? atual.preco,
    });
    if (normalizado.data !== atual.data) await garantirPregao(client, normalizado.data);

    await client.query(
      `UPDATE volume_scanner.trade_operacoes
          SET tipo = $1, data = $2, quantidade = $3, preco = $4
        WHERE id = $5`,
      [normalizado.tipo, normalizado.data, normalizado.quantidade, normalizado.preco, id],
    );

    const desde = normalizado.data < atual.data ? normalizado.data : atual.data;
    await recalcular(client, atual.tradeId, desde);
    return atual.tradeId;
  });

  return tradeId === null ? null : await detalharTrade(tradeId);
}

/**
 * Apaga uma operacao. Se o trade fica sem nenhuma, o trade inteiro e apagado
 * (cascade leva as demais operacoes e os snapshots) -- um trade sem operacao
 * nao faz sentido.
 */
export async function apagarOperacao(
  id: number,
): Promise<{ apagado: boolean; trade: TradeDetalhe | null }> {
  const tradeId = await comTransacao(async (client) => {
    const { rows } = await client.query<{ trade_id: string | number; data: Date | string }>(
      `SELECT trade_id, data FROM volume_scanner.trade_operacoes WHERE id = $1 FOR UPDATE`,
      [id],
    );
    if (rows.length === 0) return null;
    const idDoTrade = Number(rows[0].trade_id);
    const dataApagada = dia(rows[0].data);

    await client.query(`DELETE FROM volume_scanner.trade_operacoes WHERE id = $1`, [id]);

    const { rows: restantes } = await client.query<{ n: string }>(
      `SELECT COUNT(*) AS n FROM volume_scanner.trade_operacoes WHERE trade_id = $1`,
      [idDoTrade],
    );
    if (Number(restantes[0].n) === 0) {
      await client.query(`DELETE FROM volume_scanner.trades WHERE id = $1`, [idDoTrade]);
      return idDoTrade;
    }

    await recalcular(client, idDoTrade, dataApagada);
    return idDoTrade;
  });

  if (tradeId === null) return { apagado: false, trade: null };
  // Se o trade foi apagado junto (ficou sem operacao), `detalharTrade` acha
  // nada e devolve null -- o mesmo caminho serve os dois casos.
  return { apagado: true, trade: await detalharTrade(tradeId) };
}
