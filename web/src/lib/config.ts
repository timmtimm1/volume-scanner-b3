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
