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
   * Estatico: os dados mudam uma vez por pregao, e o Actions dispara o rebuild
   * depois do scan. Sem API no ar, sem cold start no 4G (secao 5 do plano).
   */
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
