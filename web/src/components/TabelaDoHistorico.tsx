"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import {
  chaveDoEvento,
  type EstadoDoHistorico,
  lerEstadoDoHistorico,
  type OrdemDoZ,
  TETO_DO_CORTE,
  temFiltro,
} from "@/lib/estado-do-historico";
import {
  data as fmtData,
  dinheiro,
  multiplo,
  nomeDaEmpresa,
  numero,
  percentual,
  reais,
} from "@/lib/formato";
import type { LinhaDoHistorico } from "@/lib/types";
import { carregarBarras } from "@/lib/useBarrasDoPapel";
import { useComputador } from "@/lib/useComputador";
import { ArranjoDaPagina, GradeDeCaixas } from "./OrganizarCaixas";

/**
 * A previa so existe no computador, e e ela que traz o grafico. Carregada a
 * parte, o celular nao baixa o lightweight-charts para abrir o historico.
 */
const PreviaDoHistorico = dynamic(
  () => import("@/components/PreviaDoHistorico").then((m) => m.PreviaDoHistorico),
  { ssr: false },
);

/**
 * Quantas linhas vao para a tela de cada vez. Cada linha renderizada pesa perto
 * de 1 KB de HTML; com os 1.000 eventos na tela, a pagina passava de 1 MB. O
 * dado de todos continua carregado, e os filtros valem sobre ele inteiro.
 */
const LINHAS_POR_VEZ = 100;

/** Onde a tela guarda o estado para quem abre a ficha e volta. */
const CHAVE = "vs:historico";

type Props = {
  /** Os eventos mais recentes, do pregao mais novo para o mais antigo. */
  eventos: LinhaDoHistorico[];
  limiarDoAlerta: number;
  minimo: number;
};

function lerDaSessao(): string | null {
  try {
    return sessionStorage.getItem(CHAVE);
  } catch {
    return null;
  }
}

// O estado salvo e lido UMA vez por visita a tela, e nao a cada renderizacao:
// a propria tela grava nele enquanto e usada, e reler o que ela mesma gravou
// nao restaura nada. Sair da tela zera a leitura (ver o efeito em
// `TabelaDoHistorico`), e a proxima visita le de novo.
let lidoNestaVisita: string | null | undefined;

function lerUmaVez(): string | null {
  if (lidoNestaVisita === undefined) lidoNestaVisita = lerDaSessao();
  return lidoNestaVisita;
}

function gravar(estado: EstadoDoHistorico) {
  try {
    sessionStorage.setItem(CHAVE, JSON.stringify(estado));
  } catch {
    // Armazenamento bloqueado: a tela funciona igual, so nao lembra ao voltar.
  }
}

const semAssinatura = () => () => {};
const noNavegador = () => true;
const noServidor = () => false;

/**
 * Serve para revisitar eventos e ir construindo repertorio de padroes.
 *
 * Filtra por papel, faixa de z e periodo, como a Tela 3 do plano pede. O
 * periodo vai ate onde os eventos carregados alcancam; o cabecalho diz qual e.
 *
 * No computador, clicar num evento mostra o grafico dele na previa ao lado, sem
 * sair da lista; as setas passam de evento em evento e o Enter abre a ficha. No
 * celular, o toque abre a ficha, como sempre.
 *
 * Quem abre a ficha e volta encontra a tela como deixou: filtros, linhas
 * abertas, evento escolhido e rolagem.
 */
export function TabelaDoHistorico(props: Props) {
  // No servidor e na hidratacao nao ha estado salvo: o HTML estatico sai com os
  // filtros padrao, e o salvo entra logo depois, sem erro de hidratacao.
  const salvo = useSyncExternalStore(semAssinatura, lerUmaVez, () => null);
  // Falso so na hidratacao. Ate la a tabela nao grava nada: na carga da pagina
  // (F5, link em aba nova) o React so le o valor salvo depois de rodar os
  // efeitos da tabela, e o primeiro deles gravaria os filtros padrao por cima.
  const hidratado = useSyncExternalStore(semAssinatura, noNavegador, noServidor);
  useEffect(
    () => () => {
      lidoNestaVisita = undefined;
    },
    [],
  );
  const inicial = useMemo(
    () => lerEstadoDoHistorico(salvo, props.minimo, LINHAS_POR_VEZ),
    [salvo, props.minimo],
  );
  // A `key` remonta a tabela quando o estado salvo chega depois da hidratacao:
  // os `useState` dela so leem o valor inicial na montagem.
  return (
    <Tabela
      key={inicial ? "restaurada" : "nova"}
      {...props}
      inicial={inicial}
      podeGravar={hidratado}
    />
  );
}

function Tabela({
  eventos,
  limiarDoAlerta,
  minimo,
  inicial,
  podeGravar,
}: Props & { inicial: EstadoDoHistorico | null; podeGravar: boolean }) {
  const router = useRouter();
  const computador = useComputador();
  const ate = eventos[0]?.tradeDate;
  const de = eventos.at(-1)?.tradeDate;
  // Quantos cruzaram o limiar do alerta. O rotulo ao lado diz "acima de Nσ",
  // e nao "notificados": o historico e carga retroativa, e evento antigo nunca
  // foi notificado.
  const acimaDoLimiar = useMemo(
    () => eventos.filter((e) => e.zLog >= limiarDoAlerta).length,
    [eventos, limiarDoAlerta],
  );

  const [corte, setCorte] = useState(inicial?.corte ?? minimo);
  const [busca, setBusca] = useState(inicial?.busca ?? "");
  // "" = sem limite daquele lado. Datas ISO comparam certo como texto.
  const [desde, setDesde] = useState(inicial?.desde ?? "");
  const [atePeriodo, setAtePeriodo] = useState(inicial?.ate ?? "");
  // null = ordem padrao (pregao mais recente primeiro, ja vinda do banco).
  // Um clique no cabecalho "Desvio (z)" liga a ordenacao por esse valor;
  // outro clique inverte; o terceiro volta a ordem padrao.
  const [ordemZ, setOrdemZ] = useState<OrdemDoZ>(inicial?.ordemZ ?? null);
  // Quantas linhas mostrar, amarrado aos filtros: mudou um filtro, volta a
  // mostrar a primeira leva sem precisar zerar estado dentro de efeito.
  const chaveDosFiltros = `${corte}|${busca}|${desde}|${atePeriodo}|${ordemZ}`;
  const [leva, setLeva] = useState({
    chave: chaveDosFiltros,
    linhas: inicial?.linhas ?? LINHAS_POR_VEZ,
  });
  const linhasNaTela = leva.chave === chaveDosFiltros ? leva.linhas : LINHAS_POR_VEZ;
  // O evento da previa. Null (ou um evento que o filtro tirou da lista) mostra
  // o primeiro da lista -- o mesmo criterio da previa do scanner.
  const [selecionado, setSelecionado] = useState<string | null>(inicial?.selecionado ?? null);

  const visiveis = useMemo(() => {
    const alvo = busca.trim().toUpperCase();
    const filtrados = eventos.filter(
      (e) =>
        e.zLog >= corte &&
        // Procurar "petrobras" tem de achar PETR3 e PETR4: quem nao decorou o
        // ticker sabe o nome. Olha o nome INTEIRO, e nao o que a tela mostra:
        // razao social longa fica fora da lista, mas continua achavel.
        (!alvo ||
          e.ticker.includes(alvo) ||
          (e.empresa ?? "").toUpperCase().includes(alvo)) &&
        (!desde || e.tradeDate >= desde) &&
        (!atePeriodo || e.tradeDate <= atePeriodo),
    );
    if (!ordemZ) return filtrados;
    const sinal = ordemZ === "desc" ? -1 : 1;
    return [...filtrados].sort((a, b) => sinal * (a.zLog - b.zLog));
  }, [eventos, corte, busca, desde, atePeriodo, ordemZ]);

  const indiceDaPrevia = useMemo(() => {
    const i =
      selecionado === null ? -1 : visiveis.findIndex((e) => chaveDoEvento(e) === selecionado);
    return i >= 0 ? i : visiveis.length > 0 ? 0 : -1;
  }, [visiveis, selecionado]);
  const previa = indiceDaPrevia >= 0 ? visiveis[indiceDaPrevia] : null;
  const chaveDaPrevia = previa ? chaveDoEvento(previa) : null;

  function alternarOrdemZ() {
    setOrdemZ((atual) => (atual === "desc" ? "asc" : atual === "asc" ? null : "desc"));
  }

  function limparFiltros() {
    setCorte(minimo);
    setBusca("");
    setDesde("");
    setAtePeriodo("");
    setOrdemZ(null);
  }

  /*
   * O estado vai para o `sessionStorage` a cada mudanca, e a rolagem a cada
   * parada da rolagem. Assim quem sai -- pelo link da ficha, pelo Enter ou pelo
   * menu -- deixa a tela salva, sem depender de aviso de saida.
   */
  const rolagem = useRef(inicial?.rolagem ?? 0);
  const estadoAtual = useRef<EstadoDoHistorico | null>(null);
  useEffect(() => {
    if (!podeGravar) return;
    estadoAtual.current = {
      corte,
      busca,
      desde,
      ate: atePeriodo,
      ordemZ,
      linhas: linhasNaTela,
      selecionado: chaveDaPrevia,
      rolagem: rolagem.current,
    };
    gravar(estadoAtual.current);
  }, [podeGravar, corte, busca, desde, atePeriodo, ordemZ, linhasNaTela, chaveDaPrevia]);

  useEffect(() => {
    let espera = 0;
    function aoRolar() {
      rolagem.current = window.scrollY;
      window.clearTimeout(espera);
      espera = window.setTimeout(() => {
        if (estadoAtual.current) gravar({ ...estadoAtual.current, rolagem: rolagem.current });
      }, 150);
    }
    window.addEventListener("scroll", aoRolar, { passive: true });
    return () => {
      window.removeEventListener("scroll", aoRolar);
      window.clearTimeout(espera);
    };
  }, []);

  // Voltando da ficha: a rolagem de onde a lista estava. Antes da pintura, e de
  // novo no quadro seguinte -- a navegacao do Next pode rolar a pagina depois
  // que a tela monta.
  useLayoutEffect(() => {
    const alvo = inicial?.rolagem ?? 0;
    if (alvo <= 0) return;
    window.scrollTo(0, alvo);
    const quadro = window.requestAnimationFrame(() => window.scrollTo(0, alvo));
    return () => window.cancelAnimationFrame(quadro);
  }, [inicial]);

  /** Guarda a tela antes de sair para a ficha, com a rolagem de agora. */
  const guardarAntesDeSair = useCallback(() => {
    rolagem.current = window.scrollY;
    if (estadoAtual.current) gravar({ ...estadoAtual.current, rolagem: rolagem.current });
  }, []);

  const abrirFicha = useCallback(
    (e: LinhaDoHistorico) => {
      guardarAntesDeSair();
      router.push(`/papel/${e.ticker}/?data=${e.tradeDate}`);
    },
    [guardarAntesDeSair, router],
  );

  // A seta leva o foco junto com a selecao (o Enter na linha abre a ficha) e
  // rola so o necessario para a linha aparecer. Marcado no teclado e feito
  // aqui, depois da renderizacao, quando a linha nova ja existe -- inclusive a
  // que acabou de entrar com a leva seguinte.
  const focarDepois = useRef<string | null>(null);
  useEffect(() => {
    const chave = focarDepois.current;
    if (!chave || chave !== chaveDaPrevia) return;
    focarDepois.current = null;
    const linha = document.querySelector<HTMLElement>(`[data-evento="${CSS.escape(chave)}"]`);
    linha?.focus({ preventScroll: true });
    linha?.scrollIntoView({ block: "nearest" });
  }, [chaveDaPrevia, linhasNaTela]);

  // Setas e Enter, so com a previa na tela. Fora de campo de texto, de data e
  // do controle de z, onde as setas ja tem outro uso.
  useEffect(() => {
    if (!computador) return;
    function aoTeclar(ev: KeyboardEvent) {
      if (ev.altKey || ev.ctrlKey || ev.metaKey || ev.shiftKey) return;
      const alvo = ev.target instanceof HTMLElement ? ev.target : null;
      if (alvo?.closest("input, textarea, select, [contenteditable='true']")) return;

      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        if (visiveis.length === 0) return;
        ev.preventDefault();
        const passo = ev.key === "ArrowDown" ? 1 : -1;
        const proximo = Math.min(Math.max(indiceDaPrevia + passo, 0), visiveis.length - 1);
        if (proximo >= linhasNaTela) {
          setLeva({ chave: chaveDosFiltros, linhas: linhasNaTela + LINHAS_POR_VEZ });
        }
        const chave = chaveDoEvento(visiveis[proximo]);
        focarDepois.current = chave;
        setSelecionado(chave);
        return;
      }
      // Enter numa linha ou num botao e deles; solto na pagina, abre a ficha.
      if (ev.key === "Enter" && previa && !alvo?.closest("a, button")) {
        ev.preventDefault();
        abrirFicha(previa);
      }
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [computador, visiveis, indiceDaPrevia, linhasNaTela, chaveDosFiltros, previa, abrirFicha]);

  // Os vizinhos da previa sao pedidos adiantado: a seta chega com o grafico
  // ja carregado.
  useEffect(() => {
    if (!computador || indiceDaPrevia < 0) return;
    for (const i of [indiceDaPrevia + 1, indiceDaPrevia - 1]) {
      const vizinho = visiveis[i];
      if (vizinho) carregarBarras(vizinho.ticker).catch(() => {});
    }
  }, [computador, visiveis, indiceDaPrevia]);

  const corDoZ = (z: number) => (z >= limiarDoAlerta ? "text-evento-tinta" : "text-acento");
  const corDaVariacao = (v: number | null) => ((v ?? 0) >= 0 ? "text-alta" : "text-baixa");
  const campo =
    "num toque h-11 rounded-xl border border-linha bg-painel px-3 text-[13px] font-semibold outline-none placeholder:text-tinta-3 focus:border-acento";
  // As colunas: todas no tablet; no computador, com a previa ao lado, ficam
  // pregao, papel, z, rvol e variacao. O resto esta no cabecalho da previa.
  const colunas =
    "md:grid-cols-[104px_176px_92px_72px_84px_120px_110px_1fr] lg:grid-cols-[92px_minmax(0,1fr)_64px_60px_72px]";
  const filtrado = temFiltro({ corte, busca, desde, ate: atePeriodo, ordemZ }, minimo);

  const caixaTabela = (
    <section className="cartao overflow-hidden p-2 md:p-3">
      <div className={`hidden gap-2 px-3 py-2 md:grid ${colunas}`}>
        <span className="rotulo">Pregão</span>
        <span className="rotulo">Papel</span>
        <button
          type="button"
          onClick={alternarOrdemZ}
          aria-label={
            ordemZ === "desc"
              ? "Ordenado por desvio, do maior para o menor. Clique para inverter."
              : ordemZ === "asc"
                ? "Ordenado por desvio, do menor para o maior. Clique para voltar ao padrão."
                : "Ordenar por desvio"
          }
          className="rotulo flex items-center justify-end gap-1 text-right transition-colors hover:text-acento"
        >
          Desvio (z)
          <span className="num text-[10px]">
            {ordemZ === "desc" ? "↓" : ordemZ === "asc" ? "↑" : "↕"}
          </span>
        </button>
        <span className="rotulo text-right">rvol</span>
        <span className="rotulo text-right">Var.</span>
        <span className="rotulo text-right lg:hidden">Desvio líquido (z)</span>
        <span className="rotulo text-right lg:hidden">Ticket</span>
        <span className="rotulo text-right lg:hidden">Volume</span>
      </div>

      <div className="flex flex-col gap-0.5">
        {visiveis.slice(0, linhasNaTela).map((e) => {
          const chave = chaveDoEvento(e);
          const naPrevia = computador && chave === chaveDaPrevia;
          return (
            <Link
              key={chave}
              href={`/papel/${e.ticker}/?data=${e.tradeDate}`}
              data-evento={chave}
              aria-current={naPrevia ? "true" : undefined}
              onClick={(ev) => {
                // Ctrl/Cmd/Shift ou botao do meio: nova aba, como todo link.
                if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey || ev.button !== 0) {
                  return;
                }
                // Celular, ou Enter na linha (clique sem mouse): abre a
                // ficha, guardando antes onde a lista estava.
                if (!computador || ev.detail === 0) {
                  guardarAntesDeSair();
                  return;
                }
                // Computador, clique do mouse: so troca a previa.
                ev.preventDefault();
                setSelecionado(chave);
              }}
              // `md:min-h-[52px]`: com nome a linha tem duas alturas, sem nome tem
              // uma. Sem o piso, a lista fica com um ritmo irregular que
              // parece defeito -- e so 61 das 321 empresas ficam sem nome.
              className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-xl px-3 py-2.5 transition-colors md:min-h-[52px] md:gap-2 ${colunas} ${
                naPrevia ? "bg-selecao" : "hover:bg-painel-2"
              }`}
            >
              <span className="order-1 flex min-w-0 flex-col md:order-2">
                <span className="text-[15px] font-extrabold md:text-[14px]">{e.ticker}</span>
                {nomeDaEmpresa(e.empresa) && (
                  <span className="truncate text-[11px] font-semibold text-tinta-3">
                    {nomeDaEmpresa(e.empresa)}
                  </span>
                )}
              </span>
              <span
                className={`num order-2 text-right text-[16px] font-extrabold md:order-3 md:text-[14px] ${corDoZ(e.zLog)}`}
              >
                {numero(e.zLog)}
              </span>
              <span className="num order-3 col-span-2 text-[12px] font-semibold text-tinta-3 md:order-1 md:col-span-1 md:text-[13px] md:text-tinta-2">
                {fmtData(e.tradeDate)}
                <span className="md:hidden">
                  {" · "}
                  {multiplo(e.rvol)}
                  {" · "}
                  <span className={`font-bold ${corDaVariacao(e.retDay)}`}>
                    {percentual(e.retDay)}
                  </span>
                  {" · "}
                  {dinheiro(e.volumeFinancial)}
                </span>
              </span>
              <span className="num order-4 hidden text-right text-[13px] font-semibold text-tinta-2 md:block">
                {multiplo(e.rvol)}
              </span>
              <span
                className={`num order-5 hidden text-right text-[13px] font-bold md:block ${corDaVariacao(e.retDay)}`}
              >
                {percentual(e.retDay)}
              </span>
              <span className="num order-6 hidden text-right text-[13px] font-semibold md:block lg:hidden">
                {numero(e.zExcess)}
              </span>
              <span className="num order-7 hidden text-right text-[13px] font-semibold text-tinta-2 md:block lg:hidden">
                {reais(e.avgTicket, 0)}
              </span>
              <span className="num order-8 hidden text-right text-[13px] font-semibold md:block lg:hidden">
                {dinheiro(e.volumeFinancial)}
              </span>
            </Link>
          );
        })}
      </div>

      {visiveis.length > linhasNaTela && (
        <button
          type="button"
          onClick={() => setLeva({ chave: chaveDosFiltros, linhas: linhasNaTela + LINHAS_POR_VEZ })}
          className="toque mt-2 w-full rounded-xl bg-painel-2 px-4 py-3 text-[13px] font-bold text-tinta-2 transition-colors hover:text-acento"
        >
          mostrar mais {Math.min(LINHAS_POR_VEZ, visiveis.length - linhasNaTela)} · faltam{" "}
          <span className="num">{numero(visiveis.length - linhasNaTela, 0)}</span>
        </button>
      )}
    </section>
  );

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex min-w-0 flex-col gap-0.5">
            <h1 className="text-[22px] font-extrabold tracking-tight">Histórico de eventos</h1>
            <p className="num text-[13px] font-semibold text-tinta-3">
              {de && ate
                ? `${fmtData(de)} a ${fmtData(ate)} · os ${numero(eventos.length, 0)} eventos mais recentes`
                : "sem eventos no período"}
            </p>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-3 rounded-2xl bg-evento-fundo px-4 py-2.5">
            <span className="num text-[24px] font-extrabold text-evento-tinta">
              {numero(acimaDoLimiar, 0)}
            </span>
            <span className="text-[12px] font-bold leading-tight text-evento-tinta">
              acima de
              <br />
              {numero(limiarDoAlerta, 0)}σ
            </span>
          </div>
        </div>

        <div className="grid gap-3 rounded-2xl bg-painel-2 p-3.5 sm:grid-cols-2 lg:grid-cols-[180px_auto_minmax(220px,1fr)_auto] lg:items-end">
          <label className="flex flex-col gap-1.5">
            <span className="rotulo">Papel ou empresa</span>
            <input
              type="text"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="todos"
              className={campo}
            />
          </label>

          <div className="flex gap-3">
            <label className="flex flex-1 flex-col gap-1.5">
              <span className="rotulo">De</span>
              <input
                type="date"
                value={desde}
                min={de}
                max={ate}
                onChange={(e) => setDesde(e.target.value)}
                className={`${campo} w-full min-w-[9.5rem]`}
              />
            </label>
            <label className="flex flex-1 flex-col gap-1.5">
              <span className="rotulo">Até</span>
              <input
                type="date"
                value={atePeriodo}
                min={de}
                max={ate}
                onChange={(e) => setAtePeriodo(e.target.value)}
                className={`${campo} w-full min-w-[9.5rem]`}
              />
            </label>
          </div>

          <div className="flex flex-col gap-1.5 sm:col-span-2 lg:col-span-1">
            <div className="flex justify-between">
              <span className="rotulo">z mínimo</span>
              <span className="num text-[13px] font-extrabold text-acento">{numero(corte, 1)}σ</span>
            </div>
            <input
              type="range"
              min={minimo}
              max={TETO_DO_CORTE}
              step={0.1}
              value={corte}
              onChange={(e) => setCorte(Number(e.target.value))}
              aria-label="z mínimo"
              className="h-11 w-full cursor-pointer bg-transparent"
            />
          </div>

          <span className="flex flex-col items-start gap-1 self-center lg:items-end lg:pb-3">
            <span className="num text-[12px] font-bold text-tinta-3">
              {numero(visiveis.length, 0)} de {numero(eventos.length, 0)}
            </span>
            {filtrado && (
              <button
                type="button"
                onClick={limparFiltros}
                className="text-[12px] font-bold text-acento hover:underline"
              >
                limpar filtros
              </button>
            )}
          </span>
        </div>
      </section>

      {visiveis.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-linha-2 p-8 text-center text-[13px] font-semibold text-tinta-3">
          Nenhum evento com esses filtros.
        </div>
      ) : (
        <ArranjoDaPagina pagina="historico">
          {/* As caixas e a ordem do celular estao em lib/paginas-arrumaveis.ts. */}
          <GradeDeCaixas
            caixas={{
              tabela: caixaTabela,
              previa: computador && previa && (
                <PreviaDoHistorico
                  evento={previa}
                  limiarDoAlerta={limiarDoAlerta}
                  aoAbrir={guardarAntesDeSair}
                />
              ),
            }}
          />
        </ArranjoDaPagina>
      )}
    </div>
  );
}
