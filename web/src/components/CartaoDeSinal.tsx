import Link from "next/link";
import { fmtR } from "@/lib/backtest-tela";
import { horaEmBrasilia } from "@/lib/cripto-hoje";
import { calcularLoteFracionado, calcularLoteFracionadoVenda, type Perfil } from "@/lib/lote";
import { preco, quantidade, valor } from "@/lib/mercado";
import type { SinalDoEstudo } from "@/lib/sinais-estudo";
import {
  aberturaDaEntrada,
  explicacaoDaNota,
  fimDoPrazo,
  SETUPS_DO_ESTUDO,
} from "@/lib/sinais-estudo-tela";
import { Semaforo } from "./CartaoDeEntrada";

const MERCADO = "cripto" as const;

/** "17/11 21:00", no horario de Brasilia. */
function quando(iso: string): string {
  const d = new Date(iso);
  const dia = new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "America/Sao_Paulo",
  }).format(d);
  return `${dia} ${horaEmBrasilia(iso)}`;
}

function pct(v: number): string {
  return `${(v * 100).toFixed(1).replace(".", ",")}%`;
}

/**
 * O cartao de um sinal dos setups do estudo (entrada na abertura do candle
 * seguinte). Diferente do cartao de entrada da aba: aqui nao ha "compra acima
 * de", porque a entrada ja e a abertura; o que importa e onde ela foi, o stop,
 * o alvo, ate quando o trade pode ficar aberto e como ele esta agora.
 */
export function CartaoDeSinal({ s, perfil }: { s: SinalDoEstudo; perfil: Perfil | null }) {
  const setup = SETUPS_DO_ESTUDO[s.setup];
  if (!setup) return null;
  const venda = s.lado === "venda";
  const base = s.entrada ?? s.fechamento;
  const distancia = Math.abs(base - s.stop) / base;
  const lote = perfil
    ? (venda ? calcularLoteFracionadoVenda : calcularLoteFracionado)({ ...perfil, entrada: base, stop: s.stop })
    : null;
  const quadro = s.timeframe === "1d" ? "diário" : "4h";
  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-2xl bg-painel-2 p-4">
      <header className="flex flex-wrap items-baseline gap-2">
        <Link
          href={`/cripto/${s.moeda}?foco=${s.sinalEm.slice(0, 10)}`}
          className="text-[20px] font-extrabold transition-colors hover:text-acento"
        >
          {s.moeda}
        </Link>
        <span
          className={`rounded-md px-2 py-0.5 text-[11px] font-extrabold ${
            venda ? "bg-baixa-fundo text-baixa" : "bg-alta-fundo text-alta"
          }`}
        >
          {venda ? "VENDA" : "COMPRA"} · {quadro}
        </span>
        <span className="flex-1" />
        <span className="text-right text-[13px] font-bold text-tinta-2">{setup.titulo}</span>
      </header>

      <p className="flex items-baseline justify-between gap-3">
        <span className="text-[14px] font-bold text-tinta-2">
          {s.entrada === null
            ? `${venda ? "Vende" : "Compra"} na próxima abertura`
            : `${venda ? "Vendeu" : "Comprou"} na abertura de ${quando(aberturaDaEntrada(s.sinalEm, s.timeframe))}`}
        </span>
        <span className="num whitespace-nowrap text-[20px] font-extrabold text-acento">
          {preco(MERCADO, base)}
        </span>
      </p>

      <dl className="num grid grid-cols-3 gap-2 text-[12px]">
        <div className="flex flex-col">
          <dt className="font-semibold text-tinta-3">Stop</dt>
          <dd className="font-extrabold text-baixa">{preco(MERCADO, s.stop)}</dd>
          <dd className="font-semibold text-tinta-3">{pct(distancia)}</dd>
        </div>
        <div className="flex flex-col">
          <dt className="font-semibold text-tinta-3">Alvo (3R)</dt>
          <dd className="font-extrabold text-alta">{preco(MERCADO, s.alvo)}</dd>
        </div>
        <div className="flex flex-col">
          <dt className="font-semibold text-tinta-3">Sai até</dt>
          <dd className="font-extrabold">{quando(fimDoPrazo(s.sinalEm, s.timeframe, s.prazoCandles))}</dd>
        </div>
      </dl>

      {s.resultadoR !== null && (
        <p className="num flex items-baseline justify-between text-[13px] font-bold text-tinta-2">
          Até agora
          <span className={`text-[16px] font-extrabold ${s.resultadoR >= 0 ? "text-alta" : "text-baixa"}`}>
            {fmtR(s.resultadoR)}
          </span>
        </p>
      )}

      <Semaforo cor={setup.cor} mercado={MERCADO} explicacao={explicacaoDaNota(setup)} />

      {venda && (
        <p className="rounded-xl bg-painel px-3 py-2 text-[12px] font-semibold text-tinta-2">
          Venda: precisa de futuros ou margem na Binance (no à vista não dá para vender o que
          não tem).
        </p>
      )}

      <footer className="num text-[12px] font-semibold text-tinta-3">
        {lote && lote.quantidade > 0
          ? `${quantidade(MERCADO, lote.quantidade, s.moeda)} (${valor(MERCADO, lote.valorPosicao, 0)}) · perde ${valor(MERCADO, lote.perdaMaxima)} no stop`
          : perfil
            ? "não cabe no seu risco (posição abaixo de US$ 5)"
            : "defina seu capital para ver o lote"}
        {" · "}atualizado às {horaEmBrasilia(s.atualizadoEm)}
      </footer>
    </article>
  );
}

const ESTADO: Record<string, string> = { alvo: "alvo", stop: "stop", prazo: "prazo" };

export function LinhaDeSinalEncerrado({ s }: { s: SinalDoEstudo }) {
  const setup = SETUPS_DO_ESTUDO[s.setup];
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
      <Link href={`/cripto/${s.moeda}?foco=${s.sinalEm.slice(0, 10)}`} className="w-16 text-[14px] font-extrabold hover:text-acento">
        {s.moeda}
      </Link>
      <span className="min-w-0 flex-1 text-[13px] font-semibold text-tinta-2">
        <span className="font-bold">{setup?.titulo ?? s.setup}</span> · saiu no {ESTADO[s.estado] ?? s.estado}
        {s.saidaEm && ` (candle de ${quando(s.saidaEm)})`}
      </span>
      <span className={`num text-[13px] font-bold ${(s.resultadoR ?? 0) >= 0 ? "text-alta" : "text-baixa"}`}>
        {s.resultadoR === null ? "—" : fmtR(s.resultadoR)}
      </span>
    </li>
  );
}
