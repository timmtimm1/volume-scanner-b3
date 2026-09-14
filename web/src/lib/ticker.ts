/**
 * Formato de ticker da B3: quatro letras, um ou dois digitos, as vezes uma letra
 * de classe (PETR4, BPAC11, TAEE11B).
 *
 * Mesma regra que o Python aplica antes de mandar o ticker para a URL dos
 * fornecedores de cotacao. Repetida aqui porque este lado tambem monta URL com
 * o ticker: sem a checagem, um valor vindo da rota mudaria o caminho chamado.
 */
export const TICKER = /^[A-Z]{4}\d{1,2}[A-Z]?$/;
