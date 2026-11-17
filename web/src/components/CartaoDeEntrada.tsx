import Link from "next/link";
import type { Saida } from "@/lib/backtest-tela";
import {
  type Candle,
  type Cor,
  desenharCandles,
  type Entrada,
  TEXTO_DA_COR,
  textoDaDuracao,
} from "@/lib/entradas";
import { numero as numeroBr, percentual } from "@/lib/formato";
import {
  casasDoPreco,
  linkDaFichaNoMercado,
  type Mercado,
  preco,
  quantidade,
  textos,
  valor,
  valorComSinal,
} from "@/lib/mercado";
import { horaEmBrasilia, type SituacaoDeHoje } from "@/lib/cripto-hoje";
import { type ContextoDoDiario, NOME_DO_SETUP } from "@/lib/setups-tela";
import { BotaoEntrei } from "./FormularioEntrei";

/**
 * O cartao simples de uma entrada (pedido de 11/11/2026). Cinco coisas, nesta
 * ordem: o que e, onde entra, quanto perde se der errado, quanto ganha se der
 * certo e o que o setup fez no passado (o semaforo). O resto da leitura
 * (suporte, toques, resistencia, contexto) esta na ficha do papel, a um toque.
 */

/** Como o trade termina nas saidas sem alvo, em palavras simples. */
const COMO_SAI: Partial<Record<Saida, string>> = {
  mme9: "sai quando a média de 9 virar para baixo",
  minimas: "o stop sobe junto com o preço",
};

const LARGURA = 300;
const ALTURA = 64;

/** Os ultimos candles, com as linhas de entrada, stop e alvo. So desenho: o grafico de verdade e a ficha. */
function MiniGrafico({ candles, e }: { candles: Candle[]; e: Entrada }) {
  if (candles.length < 2) return null;
  const marcas = [e.gatilho, e.stop, ...(e.alvo === null ? [] : [e.alvo])];
  const d = desenharCandles(candles, marcas, LARGURA, ALTURA);
  const linha = (preco: number, cor: string) => (
    <line
      x1={0}
      x2={LARGURA}
      y1={d.y(preco)}
      y2={d.y(preco)}
      stroke={cor}
      strokeWidth={1}
      strokeDasharray="4 3"
      vectorEffect="non-scaling-stroke"
    />
  );
  return (
    <svg
      viewBox={`0 -2 ${LARGURA} ${ALTURA + 4}`}
      preserveAspectRatio="none"
      className="h-16 w-full"
      role="img"
      aria-label={`Últimos ${candles.length} candles de ${e.setup.ticker}, com entrada e stop`}
    >
      {e.alvo !== null && linha(e.alvo, "var(--alta)")}
      {linha(e.gatilho, "var(--acento)")}
      {linha(e.stop, "var(--baixa)")}
      {d.candles.map((c, i) => {
        const cor = c.subiu ? "var(--alta)" : "var(--baixa)";
        const meio = c.x + c.largura / 2;
        return (
          <g key={candles[i].dia}>
            <line
              x1={meio}
              x2={meio}
              y1={c.pavioDe}
              y2={c.pavioAte}
              stroke={cor}
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
            <rect x={c.x} y={c.corpoDe} width={c.largura} height={c.corpoAte - c.corpoDe} fill={cor} />
          </g>
        );
      })}
    </svg>
  );
}

/**
 * A regua: o trecho vermelho vai da entrada ao stop, o verde da entrada ao
 * alvo, na proporcao certa. Sem alvo fixo, o verde vai ate o ganho medio
 * historico e termina esmaecido -- nao ha um preco de saida marcado.
 */
function Regua({ e, mercado }: { e: Entrada; mercado: Mercado }) {
  // Em cripto o preco tem as casas da moeda (0,0000042); na B3, centavos.
  const numero = (v: number) => numeroBr(v, mercado === "b3" ? 2 : casasDoPreco(v));
  const ganhoEmR =
    e.multiplo ?? (e.ganhoMedioPct !== null && e.riscoPct > 0 ? e.ganhoMedioPct / e.riscoPct : 1);
  // teto de 4: um ganho medio muito alto nao pode espremer o vermelho ate sumir
  const verde = Math.min(Math.max(ganhoEmR, 0.5), 4);
  return (
    <div className="flex flex-col gap-1" aria-hidden>
      <div className="flex h-2.5 overflow-hidden rounded-full">
        <span className="bg-baixa" style={{ flex: 1 }} />
        <span className="w-0.5 bg-tinta" />
        <span
          className={e.alvo === null ? "bg-gradient-to-r from-alta to-alta-fundo" : "bg-alta"}
          style={{ flex: verde }}
        />
      </div>
      <div className="num flex text-[11px] font-bold text-tinta-3">
        <span style={{ flex: 1 }}>{numero(e.stop)}</span>
        <span className="flex justify-between" style={{ flex: verde }}>
          <span className="text-tinta">{numero(e.gatilho)}</span>
          <span>{e.alvo === null ? "sem alvo fixo" : numero(e.alvo)}</span>
        </span>
      </div>
    </div>
  );
}

const LUZ: Record<Cor, string> = {
  verde: "bg-alta",
  amarelo: "bg-evento",
  vermelho: "bg-baixa",
  cinza: "bg-tinta-3",
};

const ORDEM_DAS_LUZES: readonly Cor[] = ["vermelho", "amarelo", "verde"];

/** As tres luzes, so a da nota acesa, com a palavra e a explicacao de uma linha. */
export function Semaforo({ cor, mercado = "b3" }: { cor: Cor; mercado?: Mercado }) {
  const t = textos(mercado);
  // O texto da B3 e a base; em cripto trocam os anos da nota e o que e sorteado.
  const texto = {
    nome: TEXTO_DA_COR[cor].nome,
    explicacao: TEXTO_DA_COR[cor].explicacao
      .replace("2016–2026", t.periodoDaNotaTexto)
      .replace("um papel sorteado", t.sorteado),
  };
  return (
    <div className="flex items-center gap-3 rounded-xl bg-painel px-3 py-2.5">
      <span className="flex shrink-0 gap-1.5 rounded-full bg-painel-2 p-1.5" aria-hidden>
        {ORDEM_DAS_LUZES.map((c) => (
          <span
            key={c}
            className={`h-3.5 w-3.5 rounded-full ${c === cor ? LUZ[c] : "bg-linha-2"}`}
          />
        ))}
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="text-[13px] font-extrabold">{texto.nome}</span>
        <span className="text-[11px] font-semibold leading-snug text-tinta-3">
          {texto.explicacao}
        </span>
      </span>
    </div>
  );
}

function Cenario({
  rotulo,
  pct,
  emReais,
  cor,
  mercado,
  children,
}: {
  rotulo: string;
  pct: number | null;
  /** Na moeda do mercado: reais na B3, dolares em cripto. */
  emReais: number | null;
  cor: string;
  mercado: Mercado;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-bold text-tinta-2">{rotulo}</span>
        <span className={`num text-[16px] font-extrabold ${cor}`}>
          {percentual(pct)}
          {emReais !== null && (
            <span className="whitespace-nowrap text-[13px] font-bold">
              {" "}
              ({valorComSinal(mercado, emReais)})
            </span>
          )}
        </span>
      </div>
      {children && (
        <p className="num text-right text-[11px] font-semibold text-tinta-3">{children}</p>
      )}
    </div>
  );
}

/** "9 perdas seguidas (−R$ 150,00)": a pior fase do setup, ou nada sem o numero. */
function PiorFase({ e, mercado }: { e: Entrada; mercado: Mercado }) {
  if (e.piorSequencia === null) return null;
  const n = Math.round(e.piorSequencia);
  return (
    <>
      pior fase em {textos(mercado).historico}: {n} {n === 1 ? "perda seguida" : "perdas seguidas"}
      {e.piorRecuoEmReais !== null && (
        <span className="whitespace-nowrap">
          {" "}
          (−{valor(mercado, Math.abs(e.piorRecuoEmReais), 0)})
        </span>
      )}
    </>
  );
}

const NOME_CURTO: Record<Cor, [string, string]> = {
  verde: ["bom", "bons"],
  amarelo: ["duvidoso", "duvidosos"],
  vermelho: ["ruim", "ruins"],
  cinza: ["sem histórico", "sem histórico"],
};

/** "● 2 bons  ● 5 duvidosos  ● 73 ruins": o retrato do dia antes de rolar a lista. */
export function ResumoDasCores({ contagem }: { contagem: { cor: Cor; n: number }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
      {contagem.map(({ cor, n }) => (
        <li key={cor} className="num flex items-center gap-1.5 text-[13px] font-bold text-tinta-2">
          <span aria-hidden className={`h-3 w-3 rounded-full ${LUZ[cor]}`} />
          {n} {NOME_CURTO[cor][n === 1 ? 0 : 1]}
        </li>
      ))}
    </ul>
  );
}

type Props = {
  e: Entrada;
  candles: Candle[];
  diario: ContextoDoDiario;
  /** Cripto: como esta o dia de hoje em relacao ao preco de compra (Binance, ao abrir). */
  hoje?: SituacaoDeHoje | null;
};

/** "Passou hoje" ou "falta X%": o dia em andamento contra o preco de compra (so cripto). */
function LinhaDeHoje({ hoje, mercado }: { hoje: SituacaoDeHoje; mercado: Mercado }) {
  const ate = `até ${horaEmBrasilia(hoje.hora)}`;
  if (hoje.passou) {
    return (
      <p className="num rounded-xl bg-alta-fundo px-3 py-2 text-[12px] font-bold text-alta">
        Passou hoje: máxima {preco(mercado, hoje.maxima)} ({ate}). Agora {preco(mercado, hoje.ultimo)}.
      </p>
    );
  }
  return (
    <p className="num rounded-xl bg-painel px-3 py-2 text-[12px] font-semibold text-tinta-2">
      Hoje, {ate}: máxima {preco(mercado, hoje.maxima)}, agora {preco(mercado, hoje.ultimo)}. Falta{" "}
      {percentual(hoje.falta).replace("+", "")} para o preço de compra.
    </p>
  );
}

export function CartaoDeEntrada({ e, candles, diario, hoje = null }: Props) {
  const s = e.setup;
  const mercado = diario.mercado ?? "b3";
  const temAlvo = e.alvoPct !== null;
  const duracao = textoDaDuracao(e.dias, textos(mercado).dia);
  const lote = e.lote && e.lote.quantidade > 0 ? e.lote : null;
  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-2xl bg-painel-2 p-4">
      <header className="flex items-baseline gap-2">
        <Link
          href={linkDaFichaNoMercado(mercado, s.ticker, s.tradeDate)}
          className="text-[20px] font-extrabold transition-colors hover:text-acento"
        >
          {s.ticker}
        </Link>
        <span className="flex-1" />
        <span className="text-right text-[13px] font-bold text-tinta-2">
          {NOME_DO_SETUP[s.categoria]}
          {s.alta !== null && (
            <span className="font-semibold text-tinta-3">
              {" "}
              · {s.alta ? "em alta" : "contra a tendência"}
            </span>
          )}
        </span>
      </header>

      <MiniGrafico candles={candles} e={e} />

      <p className="flex items-baseline justify-between gap-3">
        <span className="text-[14px] font-bold text-tinta-2">Compra acima de</span>
        <span className="num text-[22px] font-extrabold text-acento">{preco(mercado, e.gatilho)}</span>
      </p>

      {hoje && <LinhaDeHoje hoje={hoje} mercado={mercado} />}

      <Regua e={e} mercado={mercado} />

      <Cenario
        rotulo="Se der errado"
        pct={-e.riscoPct}
        emReais={e.perdaEmReais === null ? null : -e.perdaEmReais}
        cor="text-baixa"
        mercado={mercado}
      >
        <PiorFase e={e} mercado={mercado} />
      </Cenario>

      {temAlvo ? (
        <Cenario
          rotulo="Se der certo"
          pct={e.alvoPct}
          emReais={e.alvoEmReais}
          cor="text-alta"
          mercado={mercado}
        >
          {e.ganhoMedioPct !== null && (
            <>quem ganhou, ganhou em média {percentual(e.ganhoMedioPct)}</>
          )}
        </Cenario>
      ) : (
        <Cenario
          rotulo="Se der certo, em média"
          pct={e.ganhoMedioPct}
          emReais={e.ganhoMedioEmReais}
          cor="text-alta"
          mercado={mercado}
        >
          sem alvo fixo: {COMO_SAI[e.saida] ?? "sai pela regra do setup"}
        </Cenario>
      )}

      <Semaforo cor={e.cor} mercado={mercado} />

      <footer className="flex flex-wrap items-center gap-3">
        <span className="num min-w-0 flex-1 text-[12px] font-semibold text-tinta-3">
          {[
            duracao,
            lote &&
              `${quantidade(mercado, lote.quantidade, s.ticker)} (${valor(mercado, lote.valorPosicao, 0)})`,
          ]
            .filter(Boolean)
            .join(" · ")}
          {diario.perfil === null && (
            <>
              {duracao && " · "}
              <a href="#perfil" className="font-bold text-acento hover:underline">
                defina seu capital
              </a>{" "}
              para ver {textos(mercado).naMoeda}
            </>
          )}
        </span>
        {/* o diario de trades ainda e so da B3 (quantidade inteira, preco em centavos) */}
        {mercado === "b3" && <BotaoEntrei s={s} diario={diario} />}
      </footer>
    </article>
  );
}
