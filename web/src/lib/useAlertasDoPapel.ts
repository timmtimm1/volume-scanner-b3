"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Alerta, Direcao } from "./alertas";
import type { CandleDeHoje } from "./candle-de-hoje";
import { direcaoDoNivel, nivelEmCentavos } from "./nivel-do-alerta";
import type { Barra } from "./types";

/** Duas casas, que e a precisao de preco na B3. */
function duasCasas(v: number): string {
  return v.toFixed(2);
}

/**
 * A camada pessoal da ficha: os alertas deste papel e o formulario de criar.
 *
 * A ficha e estatica e sai do CDN; os alertas exigem sessao e sao buscados
 * depois, no navegador. Quem nao esta logado recebe 401 e ve a ficha sem eles.
 *
 * Fica num hook, e nao num componente, porque o grafico (no centro) e o
 * formulario (na coluna da direita) precisam do mesmo estado: o clique no
 * grafico preenche o nivel, e os alertas salvos viram linhas no grafico.
 */
export function useAlertasDoPapel(
  ticker: string,
  barras: Barra[],
  pregaoDoEvento: string | undefined,
  hoje: CandleDeHoje | null,
) {
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [autenticado, setAutenticado] = useState<boolean | null>(null);
  const [escolhendo, setEscolhendo] = useState(false);
  const [preco, setPreco] = useState("");
  const [direcao, setDirecao] = useState<Direcao>("acima");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // O preco de referencia para adivinhar a direcao pelo clique: o de agora,
  // quando existe. Com o fechamento de ontem, um papel que subiu desde entao
  // faria um clique abaixo do preco atual virar "subir ate".
  const ultimaBarra = barras.at(-1);
  const precoDeReferencia =
    hoje && (!ultimaBarra || hoje.dia >= ultimaBarra.tradeDate)
      ? hoje.close
      : (ultimaBarra?.close ?? null);
  const pregaoDoAlerta = pregaoDoEvento ?? ultimaBarra?.tradeDate ?? null;

  // Sobe a cada busca: a resposta de uma busca antiga (uma recarga atropelada
  // por outra) e descartada.
  const busca = useRef(0);

  /** Busca a lista; devolve o cancelamento, para a troca rapida de papel. */
  const buscar = useCallback(() => {
    const minha = ++busca.current;
    let cancelada = false;
    const valendo = () => !cancelada && minha === busca.current;
    fetch(`/api/alertas/?ticker=${ticker}`)
      .then(async (r) => {
        if (!valendo()) return;
        if (r.status === 401) {
          setAutenticado(false);
          return;
        }
        if (!r.ok) throw new Error();
        const corpo = (await r.json()) as { alertas: Alerta[] };
        if (!valendo()) return;
        setAutenticado(true);
        setAlertas(corpo.alertas);
      })
      .catch(() => {
        // Falha de rede nao vira "voce nao esta logado", mas o efeito pratico e
        // o mesmo: nao mostrar o que nao se conseguiu ler.
        if (valendo()) setAutenticado(false);
      });
    return () => {
      cancelada = true;
    };
  }, [ticker]);

  /** Busca os alertas deste papel quando a ficha abre. */
  useEffect(() => buscar(), [buscar]);

  const escolherNoGrafico = useCallback(
    (valor: number) => {
      setPreco(duasCasas(valor));
      if (precoDeReferencia !== null) {
        setDirecao(valor >= precoDeReferencia ? "acima" : "abaixo");
      }
      setEscolhendo(false);
    },
    [precoDeReferencia],
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
        body: JSON.stringify({ ticker, preco: valor, direcao, tradeDate: pregaoDoAlerta }),
      });
      if (!r.ok) {
        const corpo = (await r.json().catch(() => null)) as { erro?: string } | null;
        throw new Error(corpo?.erro ?? "não foi possível salvar");
      }
      const { alerta } = (await r.json()) as { alerta: Alerta };
      setAlertas((atual) => [alerta, ...atual]);
      setPreco("");
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

  /**
   * Cria um alerta com preco e direcao dados direto, sem passar pelo
   * formulario (`preco`/`direcao` acima) -- e o que a regua do grafico usa:
   * ela tem o proprio nivel medido e nao deve mexer no estado do cartao de
   * alerta. Lanca em caso de erro; quem chama decide como mostrar.
   */
  async function criarAlertaEm(valor: number, direcaoEscolhida: Direcao): Promise<Alerta> {
    if (!pregaoDoAlerta) {
      throw new Error("sem pregão de referência para este papel");
    }
    const r = await fetch("/api/alertas/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker,
        preco: valor,
        direcao: direcaoEscolhida,
        tradeDate: pregaoDoAlerta,
      }),
    });
    if (!r.ok) {
      const corpo = (await r.json().catch(() => null)) as { erro?: string } | null;
      throw new Error(corpo?.erro ?? "não foi possível salvar");
    }
    const { alerta } = (await r.json()) as { alerta: Alerta };
    setAlertas((atual) => [alerta, ...atual]);
    return alerta;
  }

  /**
   * O clique no grafico do computador: cria o alerta na hora, sem formulario.
   * A direcao sai do preco de agora, como no clique do celular.
   */
  async function criarNoGrafico(valor: number): Promise<void> {
    const nivel = nivelEmCentavos(valor);
    if (!(nivel > 0)) return;
    setErro(null);
    try {
      await criarAlertaEm(nivel, direcaoDoNivel(nivel, precoDeReferencia));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "não foi possível criar");
    }
  }

  /**
   * Muda o nivel de um alerta que esta vigiando: a linha arrastada no grafico
   * ou o valor digitado na lista.
   *
   * A tela muda antes da resposta, para a linha nao voltar ao lugar antigo e
   * pular de novo quando o servidor confirmar. Se ele recusar, a linha volta.
   * Se a recusa for porque o alerta disparou nesse meio-tempo, a lista e
   * buscada de novo, para a tela mostrar o disparo.
   */
  async function moverAlerta(id: number, valor: number): Promise<void> {
    const antes = alertas.find((a) => a.id === id);
    if (!antes || !antes.ativo) return;
    const preco = nivelEmCentavos(valor);
    if (!(preco > 0)) return;
    const direcaoNova = direcaoDoNivel(preco, precoDeReferencia, antes.direcao);
    if (preco === antes.preco && direcaoNova === antes.direcao) return;

    const trocar = (alerta: Alerta) =>
      setAlertas((atual) => atual.map((a) => (a.id === id ? alerta : a)));
    setErro(null);
    trocar({ ...antes, preco, direcao: direcaoNova });
    try {
      const r = await fetch(`/api/alertas/${id}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preco, direcao: direcaoNova }),
      });
      if (r.status === 409) {
        buscar();
        throw new Error("o alerta já disparou ou foi apagado");
      }
      if (!r.ok) {
        const corpo = (await r.json().catch(() => null)) as { erro?: string } | null;
        throw new Error(corpo?.erro ?? "não foi possível mover");
      }
      const { alerta } = (await r.json()) as { alerta: Alerta };
      trocar(alerta);
    } catch (e) {
      trocar(antes);
      setErro(e instanceof Error ? e.message : "não foi possível mover");
    }
  }

  return {
    alertas,
    autenticado,
    escolhendo,
    setEscolhendo,
    preco,
    setPreco,
    direcao,
    setDirecao,
    salvando,
    erro,
    salvar,
    apagar,
    escolherNoGrafico,
    precoDeReferencia,
    criarAlertaEm,
    criarNoGrafico,
    moverAlerta,
  };
}

export type EstadoDosAlertas = ReturnType<typeof useAlertasDoPapel>;
