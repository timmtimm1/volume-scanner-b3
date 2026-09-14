import type { Metadata, Viewport } from "next";
import { Manrope } from "next/font/google";
import { Navegacao } from "@/components/Navegacao";
import { SCRIPT_DO_TEMA } from "@/lib/tema";
import "./globals.css";

/**
 * Manrope para tudo, texto e numero: tem algarismos tabulares, entao as colunas
 * nao dancam sem precisar de uma segunda fonte monoespacada.
 */
const sans = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--fonte-sans",
});

export const metadata: Metadata = {
  title: "volume-scanner-b3",
  description:
    "Detector de volume financeiro anômalo na B3. Detecta e apresenta; a leitura do evento é sua.",
  applicationName: "volume-scanner-b3",
  appleWebApp: {
    capable: true,
    title: "vol-scanner",
    statusBarStyle: "default",
  },
  icons: {
    icon: [{ url: "/icone-192.png", sizes: "192x192", type: "image/png" }],
    apple: [{ url: "/icone-192.png", sizes: "192x192" }],
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#eef0f6" },
    { media: "(prefers-color-scheme: dark)", color: "#0e0f1a" },
  ],
  width: "device-width",
  initialScale: 1,
  // Instalado na tela inicial, a barra de navegacao encosta na area do gesto
  // do sistema; `viewport-fit` deixa o padding seguro funcionar.
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // O script do tema grava `data-tema` antes de o React hidratar: a diferenca
    // de atributo entre servidor e cliente e esperada.
    <html lang="pt-BR" className={sans.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: SCRIPT_DO_TEMA }} />
      </head>
      <body className="min-h-dvh">
        <Navegacao />
        <main className="mx-auto w-full max-w-[1440px] px-4 pb-28 pt-3 md:px-6 md:pb-8 md:pt-4">
          {children}
        </main>
      </body>
    </html>
  );
}
