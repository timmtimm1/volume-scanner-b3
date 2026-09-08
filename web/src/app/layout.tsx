import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { Navegacao } from "@/components/Navegacao";
import "./globals.css";

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--fonte-sans",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--fonte-mono",
});

export const metadata: Metadata = {
  title: "volume-scanner-b3",
  description:
    "Detector de volume financeiro anômalo na B3. Detecta e apresenta; a leitura do evento é sua.",
  applicationName: "volume-scanner-b3",
  appleWebApp: {
    capable: true,
    title: "vol-scanner",
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: [{ url: "/icone-192.png", sizes: "192x192", type: "image/png" }],
    apple: [{ url: "/icone-192.png", sizes: "192x192" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#0a0e14",
  width: "device-width",
  initialScale: 1,
  // Instalado na tela inicial, a barra inferior de navegacao encosta na area
  // do gesto do sistema; `viewport-fit` deixa o padding seguro funcionar.
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" className={`${sans.variable} ${mono.variable}`}>
      <body className="min-h-dvh md:flex">
        <Navegacao />
        <main className="min-w-0 flex-1 pb-16 md:pb-0">{children}</main>
      </body>
    </html>
  );
}
