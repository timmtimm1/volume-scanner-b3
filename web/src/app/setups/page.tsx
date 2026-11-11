import { ehDono, signIn, signOut } from "@/auth";
import Link from "next/link";
import { AjustesDosSetups } from "@/components/AjustesDosSetups";
import { CartaoDeEntrada, ResumoDasCores } from "@/components/CartaoDeEntrada";
import { LinhaDeEncerrado, LinhaEmAndamento } from "@/components/CartaoDeSetup";
import { PerfilDeRisco } from "@/components/PerfilDeRisco";
import { SecaoRecolhida } from "@/components/SecaoRecolhida";
import { escolhasDa, rodadaAtual } from "@/lib/backtest";
import type { Nivel } from "@/lib/backtest-tela";
import { CATEGORIAS_DE_SETUP, type SaidaDoSetup } from "@/lib/config";
import {
  contarPorCor,
  type LinhaDoBacktest,
  montarEntrada,
  ordenarEntradas,
  separarPeloBolso,
} from "@/lib/entradas";
import { candlesDosPapeis, linhasDoBacktest } from "@/lib/entradas-dados";
import { data } from "@/lib/formato";
import { calcularLote } from "@/lib/lote";
import { lerPerfil } from "@/lib/perfil";
import { conferenciaAoVivo, listarSetups, preferenciasDosSetups } from "@/lib/setups";
import {
  type CategoriaDoSetup,
  type Conferencia,
  categoriaDaChave,
  chaveDoBacktest,
  gatilho,
  stopDoSetup,
} from "@/lib/setups-tela";
import { tradesDosSetups } from "@/lib/trades";

/** Quantos encerrados a secao recolhida mostra. */
const ENCERRADOS_NA_ABA = 30;

const GRADE = "grid gap-3 md:grid-cols-2 xl:grid-cols-3";

/**
 * Setups: "Entradas de hoje" numa lista so, com o cartao simples; em andamento,
 * encerrados e ajustes recolhidos embaixo (secao 14 do plano, pedido de
 * 11/11/2026). A lista vai do semaforo verde ao vermelho; o que nao cabe no
 * risco do usuario fica escondido, com aviso.
 *
 * Mesma estrutura de `/trades`: le a sessao, entao roda no servidor a cada
 * visita, e quem nao esta logado so ve o que a aba e. Decisao de 21/10/2026:
 * uma pagina publica de "setups" leria como recomendacao de investimento.
 */
export const dynamic = "force-dynamic";

export default async function Setups() {
  if (!(await ehDono())) {
    return (
      <section className="cartao mx-auto flex max-w-[560px] flex-col gap-4 p-6 md:mt-8 md:p-8">
        <h1 className="text-[22px] font-extrabold tracking-tight">Setups</h1>
        <p className="text-[14px] leading-relaxed text-tinta-2">
          Os setups do dia: o que armou, o que está em andamento e o que já terminou, com o
          alerta e a saída que você escolhe para cada um.
        </p>
        <form
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: "/setups" });
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

  const [setups, preferencias, rodada, aoVivo, perfil, trades] = await Promise.all([
    listarSetups(),
    preferenciasDosSetups(),
    rodadaAtual(),
    conferenciaAoVivo(),
    lerPerfil(),
    tradesDosSetups(),
  ]);
  const diario = { perfil, tradePorSetup: trades.porSetup, abertoPorTicker: trades.abertoPorTicker };

  // O selo de cada setup e o nivel da rodada mais recente; sem rodada, sem selo.
  // A conferencia junta o ao vivo (desde a estreia) com o numero do backtest.
  const niveis: Partial<Record<CategoriaDoSetup, Nivel>> = {};
  const conferencias: Partial<Record<CategoriaDoSetup, Conferencia>> = {};
  const saidasDoBacktest: Partial<Record<CategoriaDoSetup, SaidaDoSetup>> = {};
  for (const c of CATEGORIAS_DE_SETUP) {
    conferencias[c] = { aoVivo: aoVivo[c] ?? null, backtest: null };
  }
  let linhas: LinhaDoBacktest[] = [];
  if (rodada) {
    const [escolhas, grade] = await Promise.all([escolhasDa(rodada.id), linhasDoBacktest(rodada.id)]);
    linhas = grade;
    for (const e of escolhas) {
      const categoria = categoriaDaChave(e.setup);
      if (!categoria) continue;
      niveis[categoria] = e.nivel;
      if (e.saida) saidasDoBacktest[categoria] = e.saida;
      conferencias[categoria] = {
        aoVivo: aoVivo[categoria] ?? null,
        backtest: { r: e.expConferencia, saida: e.saida },
      };
    }
  }

  // As entradas: todo setup armado, com a saida com que armou (a escolhida em
  // Ajustes; por padrao, a melhor do backtest) e o lote do perfil.
  const armados = setups.filter((s) => s.estado === "armado");
  const entradas = ordenarEntradas(
    armados.map((s) => {
      const entrada = gatilho(s);
      const stop = stopDoSetup(s);
      return montarEntrada(
        {
          setup: s,
          chave: chaveDoBacktest(s.categoria),
          gatilho: entrada,
          stop,
          saida: s.saidaRegra ?? preferencias[s.categoria].saida,
          lote: perfil ? calcularLote({ ...perfil, entrada, stop }) : null,
        },
        linhas,
      );
    }),
  );
  const { cabem, naoCabem } = separarPeloBolso(entradas);
  const candles = await candlesDosPapeis(armados.map((s) => s.ticker));
  const ultimoPregao = setups.find((s) => s.ultimoPregao)?.ultimoPregao ?? null;

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
          <h1 className="text-[22px] font-extrabold tracking-tight">Setups</h1>
          <p className="text-[13px] font-semibold text-tinta-3">
            As possíveis entradas do dia, da melhor nota para a pior.
          </p>
        </div>
        <div className="flex-1" />
        <Link
          href="/setups/backtest"
          className="toque inline-flex h-10 items-center rounded-full border border-linha-2 px-4 text-[13px] font-bold text-tinta-2 transition-colors hover:text-tinta"
        >
          Backtest
        </Link>
        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/setups" });
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

      {/* sem capital salvo, o convite fica no topo: sem ele o cartao nao fala em reais */}
      {perfil === null && <PerfilDeRisco inicial={null} />}

      <section className="cartao flex flex-col gap-3 p-4 md:p-5">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="text-[18px] font-extrabold">
            Entradas de hoje
            <span className="num ml-2 text-[14px] font-bold text-tinta-3">{cabem.length}</span>
          </h2>
          {ultimoPregao && (
            <span className="num text-[12px] font-semibold text-tinta-3">
              armaram no pregão de {data(ultimoPregao)}
            </span>
          )}
        </div>
        {cabem.length === 0 ? (
          <p className="text-[13px] font-semibold text-tinta-3">
            {naoCabem.length === 0
              ? "Nenhum setup armou no último pregão."
              : "Nenhuma entrada de hoje cabe no seu risco."}
          </p>
        ) : (
          <>
            <ResumoDasCores contagem={contarPorCor(cabem)} />
            <p className="text-[12px] font-semibold leading-relaxed text-tinta-3">
              Cada uma só vale se o próximo pregão passar do preço de compra. O semáforo é a nota
              do setup no backtest de 30 anos: mostra o que ele fez no passado, não o que vai
              fazer.
            </p>
            <div className={GRADE}>
              {cabem.map((e) => (
                <CartaoDeEntrada
                  key={e.setup.id}
                  e={e}
                  candles={candles[e.setup.ticker] ?? []}
                  diario={diario}
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
              Com o seu capital e o seu risco por trade, nem 1 ação cabe entre a entrada e o stop
              destas.
            </p>
            <div className={GRADE}>
              {naoCabem.map((e) => (
                <CartaoDeEntrada
                  key={e.setup.id}
                  e={e}
                  candles={candles[e.setup.ticker] ?? []}
                  diario={diario}
                />
              ))}
            </div>
          </details>
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
              Resultado até o último fechamento, em R (múltiplos do risco) e já com o custo.
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
              <LinhaDeEncerrado key={s.id} s={s} />
            ))}
          </ul>
        )}
      </SecaoRecolhida>

      <SecaoRecolhida titulo="Ajustes dos setups">
        <div className="flex flex-col gap-4">
          {perfil !== null && <PerfilDeRisco inicial={perfil} />}
          <AjustesDosSetups
            preferencias={preferencias}
            niveis={niveis}
            conferencias={conferencias}
            saidasDoBacktest={saidasDoBacktest}
          />
        </div>
      </SecaoRecolhida>
    </div>
  );
}
