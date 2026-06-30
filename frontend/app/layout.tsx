import type { Metadata, Viewport } from "next";
import Script from "next/script";

import "./globals.css";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export const metadata: Metadata = {
  title: "Futures Operator",
  description: "Paper-first Binance Futures trading operations console",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Script src="/runtime-config.js" strategy="beforeInteractive" />
        {children}
      </body>
    </html>
  );
}

