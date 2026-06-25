declare global {
  interface Window {
    __APP_CONFIG__?: {
      apiUrl?: string;
      wsUrl?: string;
    };
  }
}

function trimTrailingSlash(value: string) {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

export function getApiBaseUrl() {
  if (typeof window !== "undefined") {
    const runtimeValue = window.__APP_CONFIG__?.apiUrl;
    if (runtimeValue) return trimTrailingSlash(runtimeValue);
  }

  return trimTrailingSlash(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080/api");
}

export function getWsBaseUrl() {
  if (typeof window !== "undefined") {
    const runtimeValue = window.__APP_CONFIG__?.wsUrl;
    if (runtimeValue) return trimTrailingSlash(runtimeValue);
  }

  return trimTrailingSlash(process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8080/ws");
}
