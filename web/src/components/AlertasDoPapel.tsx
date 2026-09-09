"use client";

/**
 * O grafico da ficha mais a criacao de alerta.
 *
 * Existe porque a ficha e uma pagina estatica, gerada no build, e alerta e dado
 * pessoal que so pode ser lido com sessao. A saida e esta: a pagina continua
 * saindo do CDN, e esta ilha de cliente busca a camada pessoal depois, no
 * navegador. Quem nao esta logado recebe 401 e ve exatamente a ficha de antes.
 */

import { useCallback, useEffect, useState } from "react";
import { Grafico } from "@/components/Grafico";
import type { Alerta, Direcao } from "@/lib/alertas";
import { reais } from "@/lib/formato";
import type { Barra, Evento } from "@/lib/types";

type Props = {
  ticker: string;
  barras: Barra[];
  eventos: Evento[];
  destaque?: string;
  altura?: number;
};

/** Duas casas, que e a precisao de preco na B3. */
function duasCasas(v: number): string {
  return v.toFixed(2);
}

export function AlertasDoPapel({ ticker, barras, eventos, destaque, altura }: Props) {
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [autenticado, setAutenticado] = useState<boolean | null>(null);
  const [abrindo, setAbrindo] = useState(false);
  const [preco, setPreco] = useState("");
  const [direcao, setDirecao] = useState<Direcao>("acima");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // O ultimo fechamento serve de referencia para adivinhar a direcao a partir
  // de onde o usuario clicou.
  const ultimoFechamento = barras.at(-1)?.close ?? null;
  const pregaoDoAlerta = destaque ?? barras.at(-1)?.tradeDate ?? null;

  /**
   * Busca os alertas deste papel quando a ficha abre.
   *
   * O `cancelado` nao e zelo teorico: indo de /papel/PETR4 para /papel/VALE3
   * depressa, a resposta da primeira busca pode chegar depois da segunda e
   * pintar os alertas do papel errado. A bandeira descarta o que chegou tarde.
   */
  useEffect(() => {
    let cancelado = false;

    fetch(`/api/alertas/?ticker=${ticker}`)
      .then(async (r) => {
        if (cancelado) return;
        if (r.status === 401) {
          setAutenticado(false);
          return;
        }
        if (!r.ok) throw new Error();
        const { alertas } = (await r.json()) as { alertas: Alerta[] };
        if (cancelado) return;
        setAutenticado(true);
        setAlertas(alertas);
      })
      .catch(() => {
        // Falha de rede nao pode virar "voce nao esta logado" -- mas o efeito
        // pratico e o mesmo: some com o painel, que e o que o visitante
        // anonimo ja ve. Errar para o lado de nao mostrar e o certo aqui.
        if (!cancelado) setAutenticado(false);
      });

    return () => {
      cancelado = true;
    };
  }, [ticker]);

  const escolherNoGrafico = useCallback(
    (valor: number) => {
      setPreco(duasCasas(valor));
      // Acima ou abaixo sai de onde o clique caiu em relacao ao ultimo
      // fechamento -- quase sempre o que se quer, e continua trocavel no botao.
      if (ultimoFechamento !== null) {
        setDirecao(valor >= ultimoFechamento ? "acima" : "abaixo");
      }
    },
    [ultimoFechamento],
  );

  async function salvar() {
    const valor = Number(preco.replace(",", "."));
    if (!Number.isFinite(valor) || valor <= 0) {
      setErro("informe um preço válido");
      return;
    }
    if (!pregaoDoAlerta) {
      setErro("sem pregão de referência para este papel");
      return;
    }
    setSalvando(true);
    setErro(null);
    try {
      const r = await fetch("/api/alertas/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker,
          preco: valor,
          direcao,
          tradeDate: pregaoDoAlerta,
        }),
      });
      if (!r.ok) {
        const corpo = (await r.json().catch(() => null)) as { erro?: string } | null;
        throw new Error(corpo?.erro ?? "não foi possível salvar");
      }
      const { alerta } = (await r.json()) as { alerta: Alerta };
      setAlertas((atual) => [alerta, ...atual]);
      setPreco("");
      setAbrindo(false);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "algo deu errado");
    } finally {
      setSalvando(false);
    }
  }

  async function apagar(id: number) {
    setErro(null);
    const r = await fetch(`/api/alertas/${id}/`, { method: "DELETE" });
    if (r.ok) setAlertas((atual) => atual.filter((a) => a.id !== id));
    else setErro("não foi possível apagar");
  }

  return (
    <>
      <Grafico
        barras={barras}
        eventos={eventos}
        destaque={destaque}
        altura={altura}
        alertas={alertas}
        escolhendoPreco={abrindo}
        aoEscolherPreco={escolherNoGrafico}
      />

      {/* Enquanto a sessao nao foi resolvida nao ha nada aqui: piscar um botao
          e escondê-lo em seguida seria pior do que aparecer um instante depois. */}
      {autenticado && (
        <div className="mt-3 rounded-md border border-linha bg-painel">
          <div className="flex flex-wrap items-center gap-3 px-3.5 py-2.5">
            <button
              type="button"
              onClick={() => {
                setAbrindo((v) => !v);
                setErro(null);
              }}
              aria-expanded={abrindo}
              className={`toque rounded border px-3 py-1.5 text-[12px] transition-colors ${
                abrindo
                  ? "border-ambar bg-selecao text-ambar"
                  : "border-linha-2 text-tinta-2 hover:text-tinta"
              }`}
            >
              {abrindo ? "cancelar" : "criar alerta"}
            </button>

            {abrindo && (
              <>
                <div className="flex rounded border border-linha-2">
                  {(["acima", "abaixo"] as const).map((d) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => setDirecao(d)}
                      aria-pressed={direcao === d}
                      className={`toque px-2.5 py-1.5 text-[11px] transition-colors ${
                        direcao === d
                          ? "bg-selecao text-ambar"
                          : "text-tinta-3 hover:text-tinta-2"
                      }`}
                    >
                      {d === "acima" ? "subir até" : "cair até"}
                    </button>
                  ))}
                </div>

                <label className="flex items-center gap-2">
                  <span className="rotulo">R$</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={preco}
                    onChange={(e) => setPreco(e.target.value)}
                    placeholder="0,00"
                    aria-label="Preço do alerta"
                    className="num toque w-24 rounded border border-linha-2 bg-painel-2 px-2.5 py-1.5 text-right text-[13px] outline-none focus:border-ambar"
                  />
                </label>

                <button
                  type="button"
                  onClick={salvar}
                  disabled={salvando || preco.trim() === ""}
                  className="toque rounded border border-ambar bg-selecao px-3 py-1.5 text-[12px] text-ambar transition-colors hover:bg-linha-2 disabled:opacity-40"
                >
                  {salvando ? "salvando…" : "salvar"}
                </button>
              </>
            )}

            {!abrindo && alertas.length > 0 && (
              <span className="num text-[11px] text-tinta-3">
                {alertas.filter((a) => a.ativo).length} vigiando
              </span>
            )}
          </div>

          {erro && (
            <p className="border-t border-linha px-3.5 py-2 text-[12px] text-baixa">
              {erro}
            </p>
          )}

          {alertas.length > 0 && (
            <ul className="border-t border-linha">
              {alertas.map((a) => (
                <li
                  key={a.id}
                  className="flex items-center gap-3 border-b border-linha px-3.5 py-2 text-[12px] last:border-b-0"
                >
                  <span
                    aria-hidden
                    className={`h-2 w-2 shrink-0 rounded-full ${
                      a.ativo ? "bg-ambar" : "bg-tinta-3"
                    }`}
                  />
                  <span className="text-tinta-2">
                    {a.direcao === "acima" ? "subir até" : "cair até"}
                  </span>
                  <span className="num font-semibold">{reais(a.preco)}</span>
                  <span className="text-tinta-3">
                    {a.ativo ? (
                      "vigiando"
                    ) : (
                      <>
                        disparou a{" "}
                        <span className="num text-ambar">{reais(a.precoDisparo)}</span>
                      </>
                    )}
                  </span>
                  <button
                    type="button"
                    onClick={() => apagar(a.id)}
                    className="toque ml-auto rounded border border-linha-2 px-2 py-0.5 text-[11px] text-tinta-3 transition-colors hover:text-baixa"
                  >
                    apagar
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </>
  );
}
