import { data as fmtData, numero, reais } from "@/lib/formato";
import {
  descartesEmTexto,
  diaComSemana,
  diaEmBrasilia,
  ehErro,
  instanteEmBrasilia,
  soQuemCaiu,
  soQuemSubiu,
} from "@/lib/semana";
import type {
  Abertura,
  AtivoDaAbertura,
  BlocoComErro,
  CriptoDaSemana,
  MoedaCripto,
  NoticiasDaSemana,
} from "@/lib/types";
import { Bloco, Nota, Rotulo, Variacao } from "./SemanaPecas";

/* ------------------------------------------------------------------ */
/* Abertura                                                            */
/* ------------------------------------------------------------------ */

const ATIVOS: {
  chave: keyof Abertura;
  nome: string;
  valor: (v: number) => string;
}[] = [
  { chave: "ibovespa", nome: "Ibovespa", valor: (v) => `${numero(v, 0)} pts` },
  { chave: "dolar", nome: "Dólar", valor: (v) => reais(v, 4) },
  { chave: "brent", nome: "Brent", valor: (v) => `US$ ${numero(v, 2)}` },
  { chave: "ouro", nome: "Ouro", valor: (v) => `US$ ${numero(v, 2)}` },
];

function MiniCartao({
  nome,
  ativo,
  valor,
}: {
  nome: string;
  ativo: AtivoDaAbertura | BlocoComErro;
  valor: (v: number) => string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 rounded-2xl bg-painel-2 p-3.5">
      <span className="rotulo">{nome}</span>
      {ehErro(ativo) ? (
        <span title={ativo.erro} className="text-[13px] font-semibold text-tinta-3">
          Indisponível nesta edição
        </span>
      ) : (
        <>
          <span className="num text-[19px] font-extrabold leading-tight tracking-tight">
            {valor(ativo.valor)}
          </span>
          <span className="flex items-baseline justify-between gap-2 text-[12px] font-semibold text-tinta-3">
            na semana
            <Variacao valor={ativo.semana} className="text-[14px]" />
          </span>
          <span className="flex items-baseline justify-between gap-2 text-[12px] font-semibold text-tinta-3">
            no mês
            <Variacao valor={ativo.mes} className="text-[12px]" />
          </span>
          <span className="flex items-baseline justify-between gap-2 text-[12px] font-semibold text-tinta-3">
            no ano
            <Variacao valor={ativo.ano} className="text-[12px]" />
          </span>
        </>
      )}
    </div>
  );
}

export function SemanaAbertura({ abertura }: { abertura: Abertura | BlocoComErro }) {
  if (ehErro(abertura)) {
    return <Bloco titulo="Abertura" indisponivel={abertura.erro} />;
  }
  const datas = ATIVOS.map((a) => abertura[a.chave])
    .filter((x): x is AtivoDaAbertura => !ehErro(x))
    .map((x) => x.data);
  const ultima = datas.sort().at(-1);
  return (
    <Bloco titulo="Abertura" subtitulo={ultima ? `Fechamento de ${fmtData(ultima)}` : undefined}>
      <div className="grid grid-cols-2 gap-2.5 md:gap-3 lg:grid-cols-4">
        {ATIVOS.map((a) => (
          <MiniCartao key={a.chave} nome={a.nome} ativo={abertura[a.chave]} valor={a.valor} />
        ))}
      </div>
    </Bloco>
  );
}

/* ------------------------------------------------------------------ */
/* Notícias                                                            */
/* ------------------------------------------------------------------ */

export function SemanaNoticias({ noticias }: { noticias: NoticiasDaSemana | BlocoComErro }) {
  if (ehErro(noticias)) {
    return <Bloco titulo="Notícias da semana" indisponivel={noticias.erro} />;
  }
  const { total, partes } = descartesEmTexto(noticias.contagem.descartes);
  return (
    <Bloco
      titulo="Notícias da semana"
      subtitulo="As histórias que mais veículos deram"
    >
      {noticias.historias.length === 0 ? (
        <p className="text-[13px] text-tinta-3">Nenhuma história passou nos filtros.</p>
      ) : (
        <ol>
          {noticias.historias.map((h) => (
            <li key={h.link} className="border-b border-linha py-3 first:pt-0 last:border-b-0">
              <a
                href={h.link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[14px] font-bold leading-snug text-tinta transition-colors hover:text-acento"
              >
                {h.titulo}
              </a>
              <p className="num mt-1 text-[12px] font-semibold text-tinta-3">
                {h.fonte} · {diaComSemana(diaEmBrasilia(h.publicada_em))}
              </p>
              {h.outras_fontes.length > 0 && (
                <details className="group">
                  <summary className="inline-flex min-h-8 cursor-pointer list-none items-center gap-1 text-[12px] font-bold text-acento marker:hidden [&::-webkit-details-marker]:hidden">
                    e mais {h.outras_fontes.length}{" "}
                    {h.outras_fontes.length === 1 ? "veículo" : "veículos"}
                    <span aria-hidden className="transition-transform group-open:rotate-90">
                      ›
                    </span>
                  </summary>
                  <ul className="flex flex-col gap-0.5 pb-1 pl-3">
                    {h.outras_fontes.map((o) => (
                      <li key={o.link}>
                        <a
                          href={o.link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-block py-1 text-[12px] font-semibold text-tinta-2 hover:text-acento"
                        >
                          {o.fonte}
                        </a>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </li>
          ))}
        </ol>
      )}
      {noticias.avisos.length > 0 && (
        <Nota>{noticias.avisos.join(" · ")}</Nota>
      )}
      <Nota>
        Manchetes do Google Notícias, <span className="num">{numero(noticias.contagem.distintas, 0)}</span>{" "}
        distintas na coleta.
        {total > 0 && (
          <>
            {" "}
            Deixamos de fora <span className="num">{numero(total, 0)}</span>: {partes.join(", ")}.
          </>
        )}{" "}
        O texto é de cada veículo; aqui só a manchete e o link.
      </Nota>
    </Bloco>
  );
}

/* ------------------------------------------------------------------ */
/* Cripto                                                              */
/* ------------------------------------------------------------------ */

const preco = (v: number) => `US$ ${numero(v, v >= 1000 ? 0 : v >= 1 ? 2 : 4)}`;

function Destaque({ moeda }: { moeda: MoedaCripto | null }) {
  if (!moeda) return null;
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-2xl bg-painel-2 p-3.5">
      <span className="rotulo">{moeda.nome}</span>
      <span className="num whitespace-nowrap text-[19px] font-extrabold leading-tight tracking-tight">
        {preco(moeda.preco)}
      </span>
      <span className="flex items-baseline justify-between gap-2 text-[12px] font-semibold text-tinta-3">
        em 7 dias
        <Variacao valor={moeda.variacao_7d} className="text-[14px]" />
      </span>
    </div>
  );
}

function LinhaDaMoeda({ moeda, rank = false }: { moeda: MoedaCripto; rank?: boolean }) {
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 border-b border-linha py-2 last:border-b-0">
      <span className="flex min-w-0 items-baseline gap-2">
        {rank && <span className="num w-5 shrink-0 text-[11px] font-semibold text-tinta-3">{moeda.rank}</span>}
        <span className="text-[14px] font-extrabold">{moeda.simbolo}</span>
        <span className="truncate text-[12px] text-tinta-3">{moeda.nome}</span>
      </span>
      <Variacao valor={moeda.variacao_7d} className="text-[14px]" />
      <span className={`num col-span-2 text-[12px] font-semibold text-tinta-3 ${rank ? "pl-7" : ""}`}>
        {preco(moeda.preco)}
      </span>
    </li>
  );
}

function ListaDeMoedas({ titulo, moedas, vazio }: { titulo: string; moedas: MoedaCripto[]; vazio: string }) {
  return (
    <div className="flex min-w-0 flex-col">
      <Rotulo>{titulo}</Rotulo>
      {moedas.length === 0 ? (
        <p className="py-3 text-[13px] text-tinta-3">{vazio}</p>
      ) : (
        <ul>
          {moedas.map((m) => (
            <LinhaDaMoeda key={m.id} moeda={m} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function SemanaCripto({ cripto }: { cripto: CriptoDaSemana | BlocoComErro }) {
  if (ehErro(cripto)) return <Bloco titulo="Cripto" indisponivel={cripto.erro} />;
  return (
    <Bloco
      titulo="Cripto"
      subtitulo={`7 dias até a coleta, ${instanteEmBrasilia(cripto.coletado_em)}`}
    >
      <div className="grid grid-cols-2 gap-2.5">
        <Destaque moeda={cripto.btc} />
        <Destaque moeda={cripto.eth} />
      </div>
      <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
        <ListaDeMoedas
          titulo="Maiores altas"
          moedas={soQuemSubiu(cripto.altas, (m) => m.variacao_7d)}
          vazio="Nenhuma subiu na semana."
        />
        <ListaDeMoedas
          titulo="Maiores quedas"
          moedas={soQuemCaiu(cripto.quedas, (m) => m.variacao_7d)}
          vazio="Nenhuma caiu na semana."
        />
      </div>
      {cripto.moedas.length > 0 && (
        <details className="group">
          <summary className="toque inline-flex min-h-9 cursor-pointer list-none items-center gap-1.5 rounded-full border border-linha-2 px-3.5 text-[12px] font-bold text-tinta-2 hover:border-acento hover:text-acento [&::-webkit-details-marker]:hidden">
            ver as {cripto.moedas.length}
            <span aria-hidden className="transition-transform group-open:rotate-90">
              ›
            </span>
          </summary>
          <ul className="pt-2">
            {cripto.moedas.map((m) => (
              <LinhaDaMoeda key={m.id} moeda={m} rank />
            ))}
          </ul>
        </details>
      )}
      <Nota>
        CoinGecko, por valor de mercado, sem stablecoins nem ativos tokenizados. A janela de 7 dias
        termina na hora da coleta, não na sexta.
      </Nota>
    </Bloco>
  );
}
