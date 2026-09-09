import type { NextConfig } from "next";
import { config as carregarEnv } from "dotenv";

/**
 * O `.env` mora na raiz do projeto e serve tanto ao Python quanto a este build.
 * Uma copia aqui dentro seria uma segunda fonte de verdade para a mesma
 * credencial -- e uma delas ficaria velha.
 */
carregarEnv({ path: "../.env", quiet: true });

const nextConfig: NextConfig = {
  /**
   * `output: "export"` saiu daqui quando os alertas entraram.
   *
   * Alerta e escrito pelo navegador e precisa de sessao; nada disso existe num
   * site sem servidor. A troca foi deliberada e o custo, contido: as telas de
   * dado -- scanner, historico, papeis e cada ficha de papel -- continuam
   * geradas no build, porque nenhuma delas usa cookie, cabecalho ou parametro
   * dinamico. Elas seguem saindo do CDN, instantaneas no 4G.
   *
   * O que passou a rodar no servidor e so o que nao poderia ser outra coisa:
   * as rotas em /api/alertas e /api/auth, marcadas com `force-dynamic`.
   *
   * Em outras palavras: o site nao virou dinamico, ele ganhou uma area
   * dinamica. Quem abre pelo link do Telegram nao paga por ela.
   */
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
