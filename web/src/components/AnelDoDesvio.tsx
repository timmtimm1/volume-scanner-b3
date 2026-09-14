import { LIMIAR_DO_ALERTA } from "@/lib/config";
import { numero } from "@/lib/formato";

/** Onde o anel fecha: 8σ ocupa a volta inteira. */
const TETO = 8;

/**
 * O desvio do volume como anel: quanto mais longe do normal, mais o anel fecha.
 *
 * Indigo abaixo do limiar do alerta, dourado a partir dele -- o dourado e a cor
 * do evento em todo o app. A marca dourada do lado de fora fica sempre no
 * limiar, para dar para ver de relance quanto falta.
 */
export function AnelDoDesvio({
  z,
  tamanho = 48,
  espessura = 5,
  fonte,
  rotulo = true,
}: {
  z: number;
  tamanho?: number;
  espessura?: number;
  fonte?: number;
  rotulo?: boolean;
}) {
  const r = (tamanho - espessura) / 2 - 4;
  const c = tamanho / 2;
  const volta = 2 * Math.PI * r;
  const fracao = Math.min(Math.max(z, 0), TETO) / TETO;
  const cruzou = z >= LIMIAR_DO_ALERTA;

  const angulo = (LIMIAR_DO_ALERTA / TETO) * 2 * Math.PI - Math.PI / 2;
  const fora = r + espessura / 2;
  const marca = {
    x1: c + (fora + 0.5) * Math.cos(angulo),
    y1: c + (fora + 0.5) * Math.sin(angulo),
    x2: c + (fora + 3.5) * Math.cos(angulo),
    y2: c + (fora + 3.5) * Math.sin(angulo),
  };
  const tam = fonte ?? Math.round(tamanho * 0.27);

  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox={`0 0 ${tamanho} ${tamanho}`}
      role="img"
      aria-label={`desvio de ${numero(z)} sigma`}
      className="shrink-0"
    >
      <circle cx={c} cy={c} r={r} fill="none" stroke="var(--selecao)" strokeWidth={espessura} />
      <circle
        cx={c}
        cy={c}
        r={r}
        fill="none"
        stroke={cruzou ? "var(--evento)" : "var(--acento)"}
        strokeWidth={espessura}
        strokeLinecap="round"
        strokeDasharray={`${volta * fracao} ${volta}`}
        transform={`rotate(-90 ${c} ${c})`}
      />
      {/* Em anel pequeno a marca encosta no numero e parece sinal de menos. */}
      {tamanho >= 80 && (
        <line {...marca} stroke="var(--evento)" strokeWidth={2.5} strokeLinecap="round" />
      )}
      {rotulo && (
        <text
          x={c}
          y={c + tam * 0.36}
          textAnchor="middle"
          fill="var(--tinta)"
          className="num"
          style={{ font: `800 ${tam}px var(--fonte-sans), system-ui, sans-serif` }}
        >
          {numero(z)}
        </text>
      )}
    </svg>
  );
}
