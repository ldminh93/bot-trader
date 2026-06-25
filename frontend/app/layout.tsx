import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Futures Operator",
  description: "Paper-first Binance Futures trading operations console",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

