/**
 * "Quando comprar e quando vender": o estudo da cesta das 50 maiores criptos,
 * no topo da aba Sazonalidade. A janela de compra e a de venda sao escolhidas
 * so com 2017-2021 e conferidas em 2022-2026. Retorno passado, nao previsao.
 * As contas moram em `lib/analise.ts`; os numeros vem do estudo noturno
 * (`scanner/cripto/sazonal.py`).
 */

import { SecaoRecolhida } from "@/components/SecaoRecolhida";
import {
  ANOS_DA_CONFERENCIA,
  ANOS_DA_ESCOLHA,
  MESES_CURTOS,
  alturaDaBarra,
  anosDaJanela,
  escolhidaDoLado,
  explicacaoDoVeredito,
  melhorEPiorMes,
  pctCurto,
  perfilDaCesta,
  primeirasDoLado,
  rotuloDaJanela,
  tetoDasBarras,
  type AnoDaJanela,
  type JanelaDoEstudo,
  type LadoDoEstudo,
  type MesDaCesta,
  type MesDoPerfil,
  type VereditoDoEstudo,
} from "@/lib/analise";

export type EstudoDaTela = {
  cesta: MesDaCesta[];
  janelas: JanelaDoEstudo[];
  anos: AnoDaJanela[];
};

const MESES_LONGOS = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];

const VEREDITOS: Record<VereditoDoEstudo, { nome: string; classe: string }> = {
  repetiu: { nome: "Repetiu", classe: "bg-alta-fundo text-alta" },
  "em parte": { nome: "Em parte", classe: "bg-evento-fundo text-evento-tinta" },
  "nao repetiu": { nome: "Não repetiu", classe: "bg-baixa-fundo text-baixa" },
  "sem conferencia": { nome: "Sem conferência", classe: "bg-painel-2 text-tinta-3" },
};

function Veredito({ v }: { v: VereditoDoEstudo }) {
  const { nome, classe } = VEREDITOS[v] ?? VEREDITOS["sem conferencia"];
  return (
    <span
      className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-[12px] font-extrabold ${classe}`}
    >
      {nome}
    </span>
  );
}

const textoDeAnos = (positivos: number, anos: number) =>
  anos === 0 ? "sem anos" : `${positivos} de ${anos} ${anos === 1 ? "ano" : "anos"} com lucro`;

function LinhaDoPeriodo({
  nome,
  media,
  positivos,
  anos,
  controle,
}: {
  nome: string;
  media: number | null;
  positivos: number;
  anos: number;
  controle: number | null;
}) {
  return (
    <p className="text-[13px] leading-relaxed text-tinta-2">
      <b className="text-tinta">{nome}:</b>{" "}
      {anos === 0 ? (
        "sem anos nesse período"
      ) : (
        <>
          média <span className="num font-bold text-tinta">{pctCurto(media)}</span> ·{" "}
          {textoDeAnos(positivos, anos)} · janela qualquer{" "}
          <span className="num font-bold text-tinta">{pctCurto(controle)}</span>
        </>
      )}
    </p>
  );
}

/** Uma barra por ano: altura pelo tamanho do resultado, cortada num teto para um ano gigante nao achatar os outros. */
function BarrasDosAnos({ anos }: { anos: AnoDaJanela[] }) {
  if (anos.length === 0) return null;
  const teto = tetoDasBarras(anos.map((a) => a.resultado));
  return (
    <div className="flex items-stretch gap-1" role="list" aria-label="Resultado ano a ano">
      {anos.map((a, i) => {
        const { fracao, cortada } = alturaDaBarra(a.resultado, teto);
        const fora = a.periodo === "fora";
        const nome =
          a.periodo === "escolha"
            ? "escolha"
            : a.periodo === "conferencia"
              ? "conferência"
              : "no meio das duas: não entra em nenhuma";
        return (
          <div key={a.ano} className="flex min-w-0 flex-1 items-stretch gap-1" role="listitem">
            {i > 0 && anos[i - 1].periodo !== a.periodo && (
              <span aria-hidden className="w-px shrink-0 bg-linha-2" />
            )}
            <div
              title={`${a.ano} (${nome}): ${pctCurto(a.resultado)}${cortada ? " · barra cortada para caber" : ""}`}
              className={`flex min-w-0 flex-1 flex-col items-center gap-0.5 ${fora ? "opacity-40" : ""}`}
            >
              <span className="num h-3 whitespace-nowrap text-[9px] font-semibold leading-3 text-tinta-3">
                {pctCurto(a.resultado)}
                {cortada && "↑"}
              </span>
              <div className="flex h-[72px] w-full items-end justify-center">
                <div
                  className={`w-[70%] max-w-[22px] rounded-t-[3px] ${a.resultado >= 0 ? "bg-alta" : "bg-baixa"}`}
                  style={{ height: `${Math.max(fracao * 100, a.resultado === 0 ? 0 : 2)}%` }}
                />
              </div>
              <span className="num text-[10px] font-bold text-tinta-3">{a.ano}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CartaoDoLado({
  titulo,
  lado,
  janelas,
  anos,
}: {
  titulo: string;
  lado: LadoDoEstudo;
  janelas: JanelaDoEstudo[];
  anos: AnoDaJanela[];
}) {
  const j = escolhidaDoLado(janelas, lado);
  return (
    <section className="cartao flex min-w-0 flex-col gap-3 p-4 md:p-5">
      <h3 className="rotulo">{titulo}</h3>
      {j === null ? (
        <p className="py-3 text-[13px] font-semibold text-tinta-3">
          Nenhuma janela com anos suficientes em {ANOS_DA_ESCOLHA}.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <p className="text-[26px] font-extrabold leading-none tracking-tight">
              {rotuloDaJanela(j.inicioMes, j.meses)}
              <span className="ml-2 text-[13px] font-semibold tracking-normal text-tinta-3">
                ({j.meses} {j.meses === 1 ? "mês" : "meses"})
              </span>
            </p>
            <Veredito v={j.veredito} />
          </div>
          <p className="text-[13px] font-semibold leading-relaxed text-tinta-2">
            {explicacaoDoVeredito(j)}
          </p>
          <div className="flex flex-col gap-1">
            <LinhaDoPeriodo
              nome={`${ANOS_DA_ESCOLHA} (escolha)`}
              media={j.escolhaMedia}
              positivos={j.escolhaPositivos}
              anos={j.escolhaAnos}
              controle={j.escolhaControle}
            />
            <LinhaDoPeriodo
              nome={`${ANOS_DA_CONFERENCIA} (conferência)`}
              media={j.conferenciaMedia}
              positivos={j.conferenciaPositivos}
              anos={j.conferenciaAnos}
              controle={j.conferenciaControle}
            />
          </div>
          <BarrasDosAnos anos={anosDaJanela(anos, lado, j.inicioMes, j.meses)} />
          <p className="text-[12px] leading-relaxed text-tinta-3">
            Média de poucos anos: um ano forte pode puxar sozinho. Veja cada ano nas barras.
          </p>
        </>
      )}
    </section>
  );
}

function TabelaDasPrimeiras({
  titulo,
  lado,
  janelas,
}: {
  titulo: string;
  lado: LadoDoEstudo;
  janelas: JanelaDoEstudo[];
}) {
  const linhas = primeirasDoLado(janelas, lado, 5);
  const celula = (media: number | null, positivos: number, anos: number) =>
    anos === 0 ? (
      <span className="text-tinta-3">—</span>
    ) : (
      <>
        <span className="font-bold text-tinta">{pctCurto(media)}</span>{" "}
        <span className="text-tinta-3">
          ({positivos}/{anos})
        </span>
      </>
    );
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <h3 className="rotulo">{titulo}</h3>
      {linhas.length === 0 ? (
        <p className="text-[13px] font-semibold text-tinta-3">Nenhuma janela com anos suficientes.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-linha text-left text-tinta-3">
                <th className="py-1.5 pr-2 font-bold">#</th>
                <th className="px-2 py-1.5 font-bold">Janela</th>
                <th className="whitespace-nowrap px-2 py-1.5 font-bold">{ANOS_DA_ESCOLHA}</th>
                <th className="whitespace-nowrap px-2 py-1.5 font-bold">{ANOS_DA_CONFERENCIA}</th>
                <th className="py-1.5 pl-2 font-bold">Veredito</th>
              </tr>
            </thead>
            <tbody>
              {linhas.map((j) => (
                <tr key={`${j.inicioMes}-${j.meses}`} className="border-b border-linha last:border-0">
                  <td className="num py-1.5 pr-2 font-bold text-tinta-3">{j.posicao}</td>
                  <td className="whitespace-nowrap px-2 py-1.5 font-extrabold">
                    {rotuloDaJanela(j.inicioMes, j.meses)}
                  </td>
                  <td className="num whitespace-nowrap px-2 py-1.5">
                    {celula(j.escolhaMedia, j.escolhaPositivos, j.escolhaAnos)}
                  </td>
                  <td className="num whitespace-nowrap px-2 py-1.5">
                    {celula(j.conferenciaMedia, j.conferenciaPositivos, j.conferenciaAnos)}
                  </td>
                  <td className="py-1.5 pl-2">
                    <Veredito v={j.veredito} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function BarraDaMediana({ v, maximo }: { v: number | null; maximo: number }) {
  if (v === null || maximo <= 0) return <span className="block h-2" />;
  const metade = Math.min(Math.abs(v) / maximo, 1) * 50;
  return (
    <span className="relative block h-2 w-full min-w-[56px] rounded-full bg-painel-2">
      <span aria-hidden className="absolute inset-y-0 left-1/2 w-px bg-linha-2" />
      <span
        className={`absolute inset-y-0 rounded-full ${v >= 0 ? "bg-alta" : "bg-baixa"}`}
        style={v >= 0 ? { left: "50%", width: `${metade}%` } : { right: "50%", width: `${metade}%` }}
      />
    </span>
  );
}

function MesAMes({ perfil }: { perfil: MesDoPerfil[] }) {
  const maximo = Math.max(0, ...perfil.map((p) => Math.abs(p.mediana ?? 0)));
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[12px]">
        <thead>
          <tr className="border-b border-linha text-left text-tinta-3">
            <th className="py-1.5 pr-2 font-bold">Mês</th>
            <th className="px-2 py-1.5 text-right font-bold">Mediana</th>
            <th className="px-2 py-1.5 font-bold">
              <span className="sr-only">Barra da mediana</span>
            </th>
            <th className="px-2 py-1.5 text-right font-bold">Média</th>
            <th className="whitespace-nowrap px-2 py-1.5 font-bold">Subiu em</th>
            <th className="whitespace-nowrap py-1.5 pl-2 text-right font-bold">BTC (média)</th>
          </tr>
        </thead>
        <tbody>
          {perfil.map((p) => (
            <tr key={p.mes} className="border-b border-linha last:border-0">
              <td className="py-1.5 pr-2 font-extrabold">{MESES_CURTOS[p.mes - 1]}</td>
              <td
                className={`num whitespace-nowrap px-2 py-1.5 text-right font-bold ${
                  p.mediana === null ? "text-tinta-3" : p.mediana >= 0 ? "text-alta" : "text-baixa"
                }`}
              >
                {pctCurto(p.mediana)}
              </td>
              <td className="w-full min-w-[64px] px-2 py-1.5">
                <BarraDaMediana v={p.mediana} maximo={maximo} />
              </td>
              <td className="num whitespace-nowrap px-2 py-1.5 text-right text-tinta-2">
                {pctCurto(p.media)}
              </td>
              <td className="num whitespace-nowrap px-2 py-1.5 text-tinta-2">
                {p.anos === 0 ? "—" : `${p.subiu} de ${p.anos}`}
              </td>
              <td className="num whitespace-nowrap py-1.5 pl-2 text-right text-tinta-3">
                {pctCurto(p.mediaBtc)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FraseDoMelhorEPior({ perfil }: { perfil: MesDoPerfil[] }) {
  const r = melhorEPiorMes(perfil);
  if (r === null) return null;
  const { melhor, pior } = r;
  return (
    <p className="text-[13px] leading-relaxed text-tinta-2">
      No mês típico (a mediana dos anos), o melhor mês da cesta foi{" "}
      <b className="text-alta">{MESES_LONGOS[melhor.mes - 1]}</b> (subiu em {melhor.subiu} de{" "}
      {melhor.anos} anos) e o pior foi <b className="text-baixa">{MESES_LONGOS[pior.mes - 1]}</b>{" "}
      (subiu em {pior.subiu} de {pior.anos}).
    </p>
  );
}

export function EstudoSazonal({ estudo }: { estudo: EstudoDaTela | null }) {
  const vazio = estudo === null || estudo.janelas.length === 0;
  const perfil = estudo ? perfilDaCesta(estudo.cesta) : [];
  const primeira = estudo?.cesta[0];
  const mesDaPrimeira = primeira
    ? `${MESES_CURTOS[Number(primeira.mes.slice(5, 7)) - 1]}/${primeira.mes.slice(0, 4)}`
    : "";

  return (
    <div className="flex flex-col gap-4">
      <section className="cartao flex flex-col gap-2 p-4 md:p-5">
        <h2 className="text-[18px] font-extrabold tracking-tight">Quando comprar e quando vender</h2>
        <p className="text-[13px] leading-relaxed text-tinta-2">
          A cesta: em cada mês, as 50 criptos com mais volume nos 90 dias anteriores, cada uma com o
          mesmo peso. A melhor janela do ano é escolhida só com {ANOS_DA_ESCOLHA} e conferida em{" "}
          {ANOS_DA_CONFERENCIA}, contra uma janela qualquer do mesmo tamanho.
        </p>
        {vazio && (
          <p className="rounded-xl bg-painel-2 px-3 py-2 text-[13px] font-semibold text-tinta-2">
            O estudo ainda não foi calculado. Ele roda toda noite junto com a análise.
          </p>
        )}
      </section>

      {!vazio && estudo && (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <CartaoDoLado
              titulo="Melhor período para comprar"
              lado="compra"
              janelas={estudo.janelas}
              anos={estudo.anos}
            />
            <CartaoDoLado
              titulo="Melhor período para vender (vendido)"
              lado="venda"
              janelas={estudo.janelas}
              anos={estudo.anos}
            />
          </div>

          <SecaoRecolhida titulo="As 5 primeiras de cada lado">
            <div className="flex flex-col gap-5">
              <TabelaDasPrimeiras titulo="Comprar" lado="compra" janelas={estudo.janelas} />
              <TabelaDasPrimeiras titulo="Vender (vendido)" lado="venda" janelas={estudo.janelas} />
              <p className="text-[12px] leading-relaxed text-tinta-3">
                Entre parênteses: em quantos anos a janela deu lucro, do total de anos.
              </p>
            </div>
          </SecaoRecolhida>

          <section className="cartao flex flex-col gap-3 p-4 md:p-5">
            <h2 className="text-[16px] font-extrabold">Mês a mês da cesta</h2>
            <FraseDoMelhorEPior perfil={perfil} />
            <MesAMes perfil={perfil} />
            {primeira && primeira.moedas < 50 && (
              <p className="text-[12px] leading-relaxed text-tinta-3">
                A cesta teve menos de 50 moedas no começo (a Binance tinha poucos pares em dólar):{" "}
                {primeira.moedas} {primeira.moedas === 1 ? "moeda" : "moedas"} em {mesDaPrimeira}.
              </p>
            )}
          </section>

          <p className="px-1 text-[12px] leading-relaxed text-tinta-3">
            Taxa de 0,1% na compra e 0,05% na venda (futuros), na entrada e na saída; sem funding nem
            custo de rebalancear a cesta. É o que aconteceu no passado, não previsão.
          </p>
        </>
      )}
    </div>
  );
}
