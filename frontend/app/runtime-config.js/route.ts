import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080/api";
  const wsUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8080/ws";

  const body = `window.__APP_CONFIG__ = ${JSON.stringify({
    apiUrl,
    wsUrl,
  })};`;

  return new NextResponse(body, {
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
    },
  });
}
