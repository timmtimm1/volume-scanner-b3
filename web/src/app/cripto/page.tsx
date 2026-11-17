import Link from "next/link";
import { ehDono, signIn, signOut } from "@/auth";
import { CartaoDeEntrada, ResumoDasCores } from "@/components/CartaoDeEntrada";
import { CartaoDeSinal, LinhaDeSinalEncerrado } from "@/components/CartaoDeSinal";
import { LinhaDeEncerrado, LinhaEmAndamento } from "@/components/CartaoDeSetup";
import { PainelDeTendencia } from "@/components/PainelDeTendencia";
import { PerfilDeRisco } from "@/components/PerfilDeRisco";
import { SecaoRecolhida } from "@/components/SecaoRecolhida";
import { escolhasDa, rodadaAtual } from "@/lib/backtest";
import type { SaidaDoSetup } from "@/lib/config";
import { moedas as lerMoedas, semCripto, volumeDoDia } from "@/lib/cripto";
import { situacaoDaEntrada } from "@/lib/cripto-hoje";
import { diaDeHoje } from "@/lib/cripto-hoje-binance";
import {
  contarPorCor,
  type LinhaDoBacktest,
  montarEntrada,
  ordenarEntradas,
  separarPeloBolso,
} from "@/lib/entradas";
import { candlesDosPapeis, linhasDoBacktest } from "@/lib/entradas-dados";
import { data, numero, percentual } from "@/lib/formato";
import { calcularLoteFracionado } from "@/lib/lote";
import { arredondarPreco, gatilhoNoMercado, preco, stopNoMercado, textos } from "@/lib/mercado";
import { noMercado } from "@/lib/mercado-servidor";
import { lerPerfil } from "@/lib/perfil";
import { sinaisDoEstudo } from "@/lib/sinais-estudo";
import { listarSetups, preferenciasDosSetups } from "@/lib/setups";
import { lerTendencias } from "@/lib/tendencias";
import { tradesDosSetups } from "@/lib/trades";
import {
  type CategoriaDoSetup,
  categoriaDaChave,
  chaveDoBacktest,
  type ContextoDoDiario,
} from "@/lib/setups-tela";

const MERCADO = "cripto" as const;
const ENCERRADOS_NA_ABA = 30;
const GRADE = "grid gap-3 md:grid-cols-2 xl:grid-cols-3";

/**
 * Cripto: as mesmas "Entradas de hoje" da aba Setups, para as 50 maiores
 * criptomoedas (pedido de 16/11/2026). Mesmo motor, mesmo cartao, mesmo
 * semaforo; o que muda e a origem do dado (candle diario da Binance, em
 * dolar), o calendario (todo dia e dia) e a nota de cada setup, que vem do
 * backtest proprio de cripto.
 *
 * So para quem esta logado, como a aba Setups.
 */
export const dynamic = "force-dynamic";

function volumeCurto(v: number): string {
  if (v >= 1e9) return `US$ ${numero(v / 1e9, 1)} bi`;
  if (v >= 1e6) return `US$ ${numero(v / 1e6, 1)} mi`;
  return `US$ ${numero(v / 1e3, 0)} mil`;
}

async function ler() {
  const [setups, preferencias, rodada, perfil, nomes, volume, sinais, trades, tendencias] = await Promise.all([
    listarSetups(),
    preferenciasDosSetups(),
    rodadaAtual(),
    lerPerfil(),
    lerMoedas(),
    volumeDoDia(),
    sinaisDoEstudo(),
    tradesDosSetups(),
    lerTendencias(),
  ]);
  const saidasDoBacktest: Partial<Record<CategoriaDoSetup, SaidaDoSetup>> = {};
  let linhas: LinhaDoBacktest[] = [];
  if (rodada) {
    const [escolhas, grade] = await Promise.all([
      escolhasDa(rodada.id),
      linhasDoBacktest(rodada.id, textos(MERCADO).periodoDaNota),
    ]);
    linhas = grade;
    for (const e of escolhas) {
      const categoria = categoriaDaChave(e.setup);
      if (categoria && e.saida) saidasDoBacktest[categoria] = e.saida;
    }
  }
  // So as moedas que estao entre as maiores hoje: quem saiu da lista continua
  // sendo acompanhado ate encerrar, mas nao arma entrada nova na aba.
  const armados = setups.filter((s) => s.estado === "armado" && (nomes[s.ticker]?.noTop ?? true));
  // O dia em andamento de cada moeda armada, perguntado a Binance a cada abertura.
  const [candles, hoje] = await Promise.all([
    candlesDosPapeis(armados.map((s) => s.ticker)),
    diaDeHoje(armados.map((s) => s.ticker)),
  ]);
  return { setups, preferencias, rodada, perfil, nomes, volume, saidasDoBacktest, linhas, armados, candles, hoje, sinais, trades, tendencias };
}

export default async function Cripto() {
  if (!(await ehDono())) {
    return (
      <section className="cartao mx-auto flex max-w-[560px] flex-col gap-4 p-6 md:mt-8 md:p-8">
        <h1 className="text-[22px] font-extrabold tracking-tight">Cripto</h1>
        <p className="text-[14px] leading-relaxed text-tinta-2">
          Os mesmos setups das ações, nas 50 maiores criptomoedas: o que armou hoje, o que está
          em andamento e o que já terminou.
        </p>
        <form
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: "/cripto" });
          }}
        >
          <button
            type="submit"
            className="toque flex h-12 w-full items-center justify-center gap-2.5 rounded-full bg-primario text-[15px] font-extrabold text-primario-tinta"
          >
            Entrar com GitHub
          </button>
        </form>
        <p className="text-[12px] font-semibold text-tinta-3">
          Só a conta dona do projeto entra. Ter conta no GitHub não basta.
        </p>
      </section>
    );
  }

  let dados: Awaited<ReturnType<typeof ler>>;
  try {
    dados = await noMercado(MERCADO, ler);
  } catch (erro) {
    if (!semCripto(erro)) throw erro;
    return (
      <section className="cartao flex flex-col gap-3 p-5">
        <h1 className="text-[22px] font-extrabold tracking-tight">Cripto</h1>
        <p className="text-[14px] leading-relaxed text-tinta-2">
          Ainda não há dado de cripto neste banco. A primeira carga roda pelo workflow{" "}
          <span className="num font-bold">cripto</span> do GitHub (Actions → cripto → Run
          workflow); depois dela, as entradas aparecem aqui todo dia às 21h.
        </p>
      </section>
    );
  }
  const { setups, preferencias, rodada, perfil, nomes, volume, saidasDoBacktest, linhas, armados, candles, hoje, sinais, trades, tendencias } = dados;
  const sinaisVivos = sinais.filter((s) => s.estado === "aguardando" || s.estado === "aberto");
  const sinaisEncerrados = sinais.filter((s) => s.estado !== "aguardando" && s.estado !== "aberto");
  const t = textos(MERCADO);
  const diario: ContextoDoDiario = {
    mercado: MERCADO,
    perfil,
    tradePorSetup: trades.porSetup,
    tradePorSinal: trades.porSinal,
    abertoPorTicker: trades.abertoPorTicker,
  };

  const entradas = ordenarEntradas(
    armados.map((s) => {
      const entrada = gatilhoNoMercado(MERCADO, s.maxima);
      const stop = stopNoMercado(MERCADO, s.minima);
      return montarEntrada(
        {
          setup: s,
          chave: chaveDoBacktest(s.categoria),
          gatilho: entrada,
          stop,
          // a saida com que armou; sem ela, a que o backtest de cripto escolheu
          saida: s.saidaRegra ?? saidasDoBacktest[s.categoria] ?? preferencias[s.categoria].saida,
          lote: perfil ? calcularLoteFracionado({ ...perfil, entrada, stop }) : null,
        },
        linhas,
        {
          periodoDaNota: t.periodoDaNota,
          arredondarPreco: (v) => arredondarPreco(MERCADO, v),
        },
      );
    }),
  );
  const { cabem, naoCabem } = separarPeloBolso(entradas);
  const ultimoDia = setups.find((s) => s.ultimoPregao)?.ultimoPregao ?? volume.dia;

  const emAndamento = setups
    .filter((s) => s.estado === "confirmado")
    .sort((a, b) => (b.confirmadoEm ?? "").localeCompare(a.confirmadoEm ?? ""));
  const encerrados = setups
    .filter((s) => s.estado !== "armado" && s.estado !== "confirmado")
    .sort((a, b) => (b.encerradoEm ?? b.tradeDate).localeCompare(a.encerradoEm ?? a.tradeDate))
    .slice(0, ENCERRADOS_NA_ABA);

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-wrap items-center gap-4 p-5">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h1 className="text-[22px] font-extrabold tracking-tight">Cripto</h1>
          <p className="text-[13px] font-semibold text-tinta-3">
            As possíveis entradas do dia nas 50 maiores moedas, da melhor nota para a pior.
          </p>
        </div>
        <div className="flex-1" />
        <Link
          href="/trades?mercado=cripto"
          className="toque inline-flex h-10 items-center rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
        >
          Seus trades
        </Link>
        <Link
          href="/cripto/backtest"
          className="toque inline-flex h-10 items-center rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
        >
          Backtest
        </Link>
        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/cripto" });
          }}
        >
          <button
            type="submit"
            className="toque h-10 rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
          >
            Sair
          </button>
        </form>
      </section>

      {perfil === null && <PerfilDeRisco inicial={null} mercado={MERCADO} />}

      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="text-[18px] font-extrabold">
            Entradas de hoje
            <span className="num ml-2 text-[14px] font-bold text-tinta-3">{cabem.length}</span>
          </h2>
          {ultimoDia && (
            <span className="num text-[12px] font-semibold text-tinta-3">
              armaram no candle de {data(ultimoDia)}, que fechou às 21h
            </span>
          )}
        </div>
        {cabem.length === 0 ? (
          <p className="text-[13px] font-semibold text-tinta-3">
            {naoCabem.length === 0
              ? "Nenhum setup armou no último candle diário."
              : "Nenhuma entrada de hoje cabe no seu risco."}
          </p>
        ) : (
          <>
            <ResumoDasCores contagem={contarPorCor(cabem)} />
            <p className="text-[12px] font-semibold leading-relaxed text-tinta-3">
              Cada uma só vale se o preço passar do valor de compra até as 21h de amanhã, quando
              o próximo candle fecha. O dia de hoje vem da Binance na hora em que você abre a
              página, e um aviso chega no Telegram quando uma entrada passa (checagem de 15 em
              15 minutos). Preços em dólar (par com USDT na Binance).{" "}
              {rodada
                ? `O semáforo é a nota do setup no backtest de cripto (${t.historico} de Binance): mostra o que ele fez no passado, não o que vai fazer.`
                : "O semáforo fica cinza até o backtest de cripto ser enviado."}
            </p>
            <div className={GRADE}>
              {cabem.map((e) => (
                <CartaoDeEntrada
                  key={e.setup.id}
                  e={e}
                  candles={candles[e.setup.ticker] ?? []}
                  diario={diario}
                  hoje={situacaoDaEntrada(e.gatilho, e.setup.tradeDate, hoje[e.setup.ticker])}
                />
              ))}
            </div>
          </>
        )}
        {naoCabem.length > 0 && (
          <details className="group">
            <summary className="toque flex cursor-pointer list-none items-center text-[13px] font-bold text-tinta-2 [&::-webkit-details-marker]:hidden">
              {naoCabem.length === 1
                ? "1 entrada escondida: não cabe no seu risco"
                : `${naoCabem.length} entradas escondidas: não cabem no seu risco`}
              <span aria-hidden className="ml-2 transition-transform group-open:rotate-90">
                ›
              </span>
            </summary>
            <p className="pb-3 text-[12px] font-semibold text-tinta-3">
              Com o seu capital e o seu risco por trade, a posição destas ficaria abaixo de US$ 5,
              o mínimo que a corretora aceita.
            </p>
            <div className={GRADE}>
              {naoCabem.map((e) => (
                <CartaoDeEntrada
                  key={e.setup.id}
                  e={e}
                  candles={candles[e.setup.ticker] ?? []}
                  diario={diario}
                  hoje={situacaoDaEntrada(e.gatilho, e.setup.tradeDate, hoje[e.setup.ticker])}
                />
              ))}
            </div>
          </details>
        )}
      </section>

      <PainelDeTendencia
        mercado={MERCADO}
        dia={tendencias.dia}
        linhas={tendencias.linhas}
        nomes={Object.fromEntries(Object.values(nomes).map((m) => [m.ticker, m.nome]))}
      />

      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="text-[18px] font-extrabold">
            Setups do estudo
            <span className="num ml-2 text-[14px] font-bold text-tinta-3">{sinaisVivos.length}</span>
          </h2>
          <span className="text-[12px] font-semibold text-tinta-3">
            reversão no RSI (diário) e compressão na venda (4h)
          </span>
        </div>
        <p className="text-[12px] font-semibold leading-relaxed text-tinta-3">
          Os dois setups do crypto-trader-skill que se saíram melhor no estudo de 2017 a 2026.
          Eles entram na abertura do candle seguinte ao sinal, sem esperar passar da máxima, e
          saem no stop, no alvo de 3R ou no prazo. São conferidos de 15 em 15 minutos, com aviso
          no Telegram quando aparece um sinal. A cor é a nota do próprio estudo.
        </p>
        {sinaisVivos.length === 0 ? (
          <p className="text-[13px] font-semibold text-tinta-3">Nenhum sinal aberto agora.</p>
        ) : (
          <div className={GRADE}>
            {sinaisVivos.map((s) => (
              <CartaoDeSinal key={s.id} s={s} perfil={perfil} diario={diario} />
            ))}
          </div>
        )}
        {sinaisEncerrados.length > 0 && (
          <details className="group">
            <summary className="toque flex cursor-pointer list-none items-center text-[13px] font-bold text-tinta-2 [&::-webkit-details-marker]:hidden">
              {sinaisEncerrados.length === 1
                ? "1 encerrado nos últimos 30 dias"
                : `${sinaisEncerrados.length} encerrados nos últimos 30 dias`}
              <span aria-hidden className="ml-2 transition-transform group-open:rotate-90">
                ›
              </span>
            </summary>
            <ul className="flex flex-col divide-y divide-linha">
              {sinaisEncerrados.map((s) => (
                <LinhaDeSinalEncerrado key={s.id} s={s} />
              ))}
            </ul>
          </details>
        )}
      </section>

      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="text-[18px] font-extrabold">Volume fora do normal</h2>
          {volume.dia && (
            <span className="num text-[12px] font-semibold text-tinta-3">
              candle de {data(volume.dia)}
            </span>
          )}
        </div>
        {volume.moedas.length === 0 ? (
          <p className="text-[13px] font-semibold text-tinta-3">Sem medição de volume ainda.</p>
        ) : (
          <>
            <ul className="flex flex-col divide-y divide-linha">
              {volume.moedas.map((m) => (
                <li key={m.ticker} className="flex items-center gap-3 py-2.5">
                  <Link
                    href={`/cripto/${m.ticker}`}
                    className="w-16 text-[14px] font-extrabold transition-colors hover:text-acento"
                  >
                    {m.ticker}
                  </Link>
                  <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-tinta-3">
                    {nomes[m.ticker]?.nome ?? ""}
                  </span>
                  <span
                    className={`num w-16 text-right text-[13px] font-bold ${
                      m.variacao === null ? "text-tinta-3" : m.variacao >= 0 ? "text-alta" : "text-baixa"
                    }`}
                  >
                    {percentual(m.variacao)}
                  </span>
                  <span className="num hidden w-28 text-right text-[12px] font-semibold text-tinta-2 sm:inline">
                    {volumeCurto(m.volume)}
                  </span>
                  <span
                    className={`num w-14 text-right text-[14px] font-extrabold ${
                      m.z >= 6 ? "text-evento" : "text-tinta"
                    }`}
                    title="desvio do volume contra os 30 dias anteriores da própria moeda"
                  >
                    {numero(m.z, 1)}σ
                  </span>
                </li>
              ))}
            </ul>
            <p className="text-[12px] font-semibold text-tinta-3">
              Quantos desvios o volume do dia ficou acima do normal da própria moeda (30 dias
              anteriores). Acima de 6σ é o mesmo corte do alerta das ações. Mostra onde olhar,
              não para onde o preço vai.
            </p>
          </>
        )}
      </section>

      <SecaoRecolhida titulo="Em andamento" contagem={emAndamento.length}>
        {emAndamento.length === 0 ? (
          <p className="text-[13px] font-semibold text-tinta-3">Nenhum em andamento.</p>
        ) : (
          <>
            <ul className="flex flex-col divide-y divide-linha">
              {emAndamento.map((s) => (
                <LinhaEmAndamento key={s.id} s={s} diario={diario} />
              ))}
            </ul>
            <p className="text-[12px] font-semibold text-tinta-3">
              Resultado até o último fechamento, em R (múltiplos do risco) e já com o custo
              (0,15% por lado). Último fechamento de cada moeda em{" "}
              {ultimoDia ? data(ultimoDia) : "—"}.
            </p>
          </>
        )}
      </SecaoRecolhida>

      <SecaoRecolhida titulo="Encerrados" contagem={encerrados.length}>
        {encerrados.length === 0 ? (
          <p className="text-[13px] font-semibold text-tinta-3">
            Nenhum encerrado nos últimos 180 dias.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-linha">
            {encerrados.map((s) => (
              <LinhaDeEncerrado key={s.id} s={s} mercado={MERCADO} />
            ))}
          </ul>
        )}
      </SecaoRecolhida>

      {perfil !== null && (
        <SecaoRecolhida titulo="Seu capital em cripto">
          <PerfilDeRisco inicial={perfil} mercado={MERCADO} />
        </SecaoRecolhida>
      )}

      <p className="px-1 text-[12px] font-semibold text-tinta-3">
        Preço de referência do BTC no último fechamento:{" "}
        {preco(MERCADO, volume.moedas.find((m) => m.ticker === "BTC")?.fechamento ?? null)}.
      </p>
    </div>
  );
}
