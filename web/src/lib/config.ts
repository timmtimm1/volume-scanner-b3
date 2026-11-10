/**
 * Parametros do `config.yaml` que o site usa, num lugar so.
 *
 * O site nao le o `config.yaml` direto: as fichas podem ser geradas sob demanda
 * na Vercel, e ali o arquivo da raiz do repositorio nao existe. Em troca, os
 * valores ficam aqui e `tests/test_config_web.py` compara com o `config.yaml`
 * na CI -- mudou la e nao mudou aqui, o teste falha.
 */

/** `alert.threshold`: onde o Telegram corta. */
export const LIMIAR_DO_ALERTA = 6.0;

/** `alert.min_volume_brl`: papel abaixo disso nao entra em lugar nenhum. */
export const PISO_DE_VOLUME = 500_000;

/** `universe.*`: a regra de quais papeis o scanner acompanha. */
export const UNIVERSO = {
  janela: 60,
  pisoMediana: 500_000,
  coberturaMinima: 0.8,
} as const;

/**
 * Piso do que o site carrega. Nao vem do `config.yaml`: e escolha da tela, para
 * o filtro de z ter faixa abaixo do limiar do alerta onde passear.
 */
export const Z_MINIMO_DO_SITE = 3.0;

/** Categorias de setup (a coluna `categoria` da tabela `setups`), na ordem do plano. */
export const CATEGORIAS_DE_SETUP = [
  "reversao",
  "media",
  "forca",
  "9.1",
  "9.2",
  "9.3",
  "9.4",
  "123",
  "pfr",
  "123_suporte",
  "pfr_suporte",
  "mma20",
  "pullback",
] as const;
export type CategoriaDoSetup = (typeof CATEGORIAS_DE_SETUP)[number];
export type SaidaDoSetup = "alvo1" | "alvo2" | "alvo3" | "minimas" | "mme9";

/**
 * `setups.padroes`: alerta e saida de cada setup ate o usuario mudar no app
 * (tabela `setup_preferencias`). Uma linha por setup, no formato que
 * `tests/test_config_web.py` le.
 */
export const PADROES_DOS_SETUPS: Record<
  CategoriaDoSetup,
  { alerta: boolean; saida: SaidaDoSetup }
> = {
  reversao: { alerta: true, saida: "alvo3" },
  media: { alerta: false, saida: "alvo3" },
  forca: { alerta: true, saida: "mme9" },
  "9.1": { alerta: false, saida: "mme9" },
  "9.2": { alerta: false, saida: "mme9" },
  "9.3": { alerta: false, saida: "mme9" },
  "9.4": { alerta: false, saida: "mme9" },
  "123": { alerta: false, saida: "alvo3" },
  pfr: { alerta: false, saida: "alvo3" },
  "123_suporte": { alerta: false, saida: "alvo3" },
  pfr_suporte: { alerta: false, saida: "alvo3" },
  mma20: { alerta: false, saida: "alvo3" },
  pullback: { alerta: false, saida: "mme9" },
};
