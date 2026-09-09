import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";

/**
 * Login com GitHub, restrito a UMA conta.
 *
 * O site e publico e o repositorio tambem. Sem esta restricao, "entrar com
 * GitHub" significaria que qualquer pessoa com uma conta do GitHub -- ou seja,
 * qualquer pessoa -- poderia criar alertas no banco. Ter conta nao e
 * credencial; ser o dono e.
 *
 * O login permitido vem do ambiente e nao do codigo: e configuracao de
 * implantacao, e deixa o repositorio publico sem um nome de usuario cravado.
 */
const DONO = process.env.AUTH_GITHUB_LOGIN;

if (!DONO) {
  // Sem isto, um deploy com a variavel faltando ficaria recusando todo login
  // sem dizer por que -- e o sintoma ("nao consigo entrar") nao aponta para a
  // causa. Barulho no log do servidor e mais barato do que a investigacao.
  console.warn(
    "[auth] AUTH_GITHUB_LOGIN nao configurada: nenhum login sera aceito. " +
      "Defina com o login do GitHub dono do projeto.",
  );
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [GitHub],
  callbacks: {
    /**
     * Ultimo portao antes da sessao existir. Devolver false aqui aborta o
     * login -- o GitHub ate autentica, mas nenhuma sessao e criada.
     */
    signIn({ profile }) {
      // Sem DONO configurado, ninguem entra. Falhar fechado: uma variavel de
      // ambiente esquecida na Vercel nao pode virar porta aberta.
      if (!DONO) return false;
      return profile?.login === DONO;
    },
    session({ session, token }) {
      if (session.user) session.user.name = String(token.name ?? session.user.name);
      return session;
    },
  },
  pages: {
    // Sem tela de login propria: o "Entrar" da barra chama signIn direto e o
    // GitHub cuida do resto. Uma pagina a menos para manter.
    error: "/alertas",
  },
});

/** Se quem esta pedindo e o dono. Usado por toda rota de alerta. */
export async function ehDono(): Promise<boolean> {
  const sessao = await auth();
  return Boolean(sessao?.user);
}
