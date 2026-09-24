"use client";

import { type ReactNode, useState } from "react";
import { type MotivoDeDescarte, tempoRelativo } from "@/lib/noticias";
import type { EstadoDasNoticias } from "@/lib/useNoticias";

/** Como cada descarte aparece no rodape, em linguagem de gente. */
const MOTIVO_NO_RODAPE: Record<MotivoDeDescarte, (n: number) => string> = {
  "nao-e-a-empresa": (n) => `${n} não eram sobre a empresa`,
  "fora-da-imprensa-financeira": (n) => `${n} citavam um nome comum fora da imprensa financeira`,
  promocao: (n) => (n === 1 ? "1 era promoção" : `${n} eram promoção`),
  "nao-e-noticia": (n) => (n === 1 ? "1 não era notícia" : `${n} não eram notícia`),
  "fonte-desconhecida": (n) => `${n} de sites fora da imprensa`,
};

/**
 * Quantas aparecem antes do "Ver mais". Com as 15 abertas, a lista empurrava
 * os cartoes de trade e de alerta para longe, na mesma coluna.
 */
const VISIVEIS = 6;

function Aviso({ children }: { children: ReactNode }) {
  return <p className="py-6 text-[13px] text-tinta-3">{children}</p>;
}

export function PainelDeNoticias({ estado }: { estado: EstadoDasNoticias }) {
  const [todas, setTodas] = useState(false);
  if (estado.carregando) return <Aviso>Buscando manchetes…</Aviso>;
  const r = estado.resultado;
  if (estado.falhou || r === null) {
    return <Aviso>Não deu para buscar as notícias agora. Tente de novo mais tarde.</Aviso>;
  }
  if (r.grupos.length === 0) {
    return <Aviso>Nenhuma notícia sobre a empresa nos últimos {r.dias} dias.</Aviso>;
  }

  const partes = (Object.keys(MOTIVO_NO_RODAPE) as MotivoDeDescarte[])
    .filter((m) => r.descartes[m] > 0)
    .map((m) => MOTIVO_NO_RODAPE[m](r.descartes[m]));
  const descartadas = Object.values(r.descartes).reduce((a, b) => a + b, 0);

  return (
    <div>
      <ul>
        {(todas ? r.grupos : r.grupos.slice(0, VISIVEIS)).map((g) => (
          <li key={g.link} className="border-b border-linha py-3 last:border-b-0">
            <a
              href={g.link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[14px] font-bold leading-snug text-tinta transition-colors hover:text-acento"
            >
              {g.titulo}
            </a>
            <p className="num mt-1 text-[12px] font-semibold text-tinta-3">
              {g.fonte} · {tempoRelativo(g.publicadaEm)}
              {g.outrasFontes.length > 0 && (
                <span title={`Também em: ${g.outrasFontes.map((o) => o.fonte).join(", ")}`}>
                  {" "}
                  · +{g.outrasFontes.length} {g.outrasFontes.length === 1 ? "fonte" : "fontes"}
                </span>
              )}
            </p>
          </li>
        ))}
      </ul>
      {!todas && r.grupos.length > VISIVEIS && (
        <button
          type="button"
          onClick={() => setTodas(true)}
          className="toque mt-1 h-9 rounded-full border border-linha-2 px-3.5 text-[12px] font-bold text-tinta-2 transition-colors hover:border-acento hover:text-acento"
        >
          Ver mais {r.grupos.length - VISIVEIS}
        </button>
      )}
      <p className="pt-2 pb-3 text-[11px] leading-relaxed text-tinta-3">
        Manchetes do Google Notícias dos últimos {r.dias} dias.
        {descartadas > 0 && (
          <>
            {" "}
            Deixamos de fora {descartadas} de {r.total}: {partes.join(", ")}.
          </>
        )}{" "}
        O texto é de cada veículo; aqui só a manchete e o link.
      </p>
    </div>
  );
}
