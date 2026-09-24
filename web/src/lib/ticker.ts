/**
 * Formato de ticker da B3: o codigo do emissor (quatro caracteres, o primeiro
 * letra), um ou dois digitos, as vezes uma letra de classe (PETR4, BPAC11,
 * TAEE11B). O emissor pode ter digito: a propria B3 negocia como B3SA3.
 *
 * Mesma regra que o Python aplica antes de mandar o ticker para a URL dos
 * fornecedores de cotacao. Repetida aqui porque este lado tambem monta URL com
 * o ticker: sem a checagem, um valor vindo da rota mudaria o caminho chamado.
 */
export const TICKER = /^[A-Z][A-Z0-9]{3}\d{1,2}[A-Z]?$/;
