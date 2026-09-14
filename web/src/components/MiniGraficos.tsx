import type { Barra } from "@/lib/types";

/** Cores de serie: as mesmas do grafico da ficha, nos dois temas. */
const ALTA = "#0E9F6E";
const BAIXA = "#E0474C";
const EVENTO = "#F0A020";

/**
 * O volume dos ultimos pregoes em barras, com o dia do evento em dourado.
 *
 * E o "5,5x o normal" em forma de desenho: a barra dourada contra a altura
 * habitual das outras. Estica na largura do container.
 */
export function FaixaDeVolume({
  barras,
  diaDoEvento,
  altura = 34,
}: {
  barras: Barra[];
  diaDoEvento: string;
  altura?: number;
}) {
  if (barras.length === 0) return <div style={{ height: altura }} />;
  const largura = 300;
  const passo = largura / barras.length;
  const w = Math.max(1.2, passo * 0.72);
  const topo = Math.max(...barras.map((b) => b.volumeFinancial), 1);
  return (
    <svg
      viewBox={`0 0 ${largura} ${altura}`}
      preserveAspectRatio="none"
      width="100%"
      height={altura}
      aria-hidden
      className="block"
    >
      {barras.map((b, i) => {
        const h = Math.max(1.5, (b.volumeFinancial / topo) * (altura - 1));
        const evento = b.tradeDate === diaDoEvento;
        return (
          <rect
            key={b.tradeDate}
            className="sobe"
            x={i * passo + (passo - w) / 2}
            y={altura - h}
            width={w}
            height={h}
            rx={1}
            fill={evento ? EVENTO : "var(--lavanda)"}
          />
        );
      })}
    </svg>
  );
}

/**
 * Candles e volume em SVG, para a previa do scanner. Leve de proposito: a
 * biblioteca de grafico completa so carrega na ficha, onde se le o evento.
 */
export function MiniCandles({
  barras,
  diaDoEvento,
  altura = 220,
}: {
  barras: Barra[];
  diaDoEvento: string;
  altura?: number;
}) {
  if (barras.length === 0) return null;
  const largura = 340;
  const alturaDoVolume = 44;
  const alturaDoPreco = altura - alturaDoVolume - 10;
  const passo = largura / barras.length;
  const corpo = Math.max(2, passo * 0.6);

  const maximas = barras.map((b) => b.high ?? b.close);
  const minimas = barras.map((b) => b.low ?? b.close);
  let hi = Math.max(...maximas);
  let lo = Math.min(...minimas);
  const folga = (hi - lo) * 0.08 || 1;
  hi += folga;
  lo -= folga;
  const y = (p: number) => ((hi - p) / (hi - lo)) * alturaDoPreco;
  const topoVolume = Math.max(...barras.map((b) => b.volumeFinancial), 1);

  return (
    <svg
      viewBox={`0 0 ${largura} ${altura}`}
      preserveAspectRatio="none"
      width="100%"
      height={altura}
      role="img"
      aria-label="candles e volume dos últimos pregões"
      className="block"
    >
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={f} x1={0} x2={largura} y1={alturaDoPreco * f} y2={alturaDoPreco * f} stroke="var(--linha)" strokeWidth={1} />
      ))}
      {barras.map((b, i) => {
        const cx = i * passo + passo / 2;
        const abertura = b.open ?? b.close;
        const evento = b.tradeDate === diaDoEvento;
        const cor = evento ? EVENTO : b.close >= abertura ? ALTA : BAIXA;
        const topo = y(Math.max(abertura, b.close));
        const fundo = y(Math.min(abertura, b.close));
        const hVol = Math.max(1.5, (b.volumeFinancial / topoVolume) * alturaDoVolume);
        return (
          <g key={b.tradeDate}>
            <line x1={cx} x2={cx} y1={y(b.high ?? b.close)} y2={y(b.low ?? b.close)} stroke={cor} strokeWidth={1.2} />
            <rect x={cx - corpo / 2} y={topo} width={corpo} height={Math.max(1.2, fundo - topo)} rx={1} fill={cor} />
            <rect
              className="sobe"
              x={cx - corpo / 2}
              y={altura - hVol}
              width={corpo}
              height={hVol}
              rx={1}
              fill={evento ? EVENTO : "var(--lavanda)"}
            />
          </g>
        );
      })}
    </svg>
  );
}
