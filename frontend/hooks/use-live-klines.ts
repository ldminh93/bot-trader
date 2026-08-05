"use client";

import { useEffect, useState } from "react";

import type { Candle } from "@/lib/types";

interface BinanceKlineTick {
  k?: {
    t: number;
    o: string;
    h: string;
    l: string;
    c: string;
    v: string;
  };
}

const RECONNECT_DELAY_MS = 3000;

/**
 * Merges live OHLCV ticks from Binance's public kline WebSocket stream into
 * the backend-provided candle array, so the chart updates between the
 * backend's ~10s snapshot poll instead of only on it.
 *
 * Only open/high/low/close/volume are ever touched here. ma7/ma25/ma99/delta/
 * cvd are authoritative, indicator-derived values computed server-side — they
 * are deliberately never recomputed client-side, and are simply carried over
 * from the last known candle (or overwritten wholesale) whenever a fresh
 * `seedCandles` array arrives from the next backend poll, which self-corrects
 * any placeholder values applied to a newly-opened live candle below.
 */
export function useLiveKlines(
  symbol: string | null,
  interval: string | null,
  seedCandles: Candle[],
): Candle[] {
  const [candles, setCandles] = useState<Candle[]>(seedCandles);

  useEffect(() => {
    setCandles(seedCandles);
  }, [seedCandles]);

  useEffect(() => {
    if (!symbol || !interval) return;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    function connect() {
      socket = new WebSocket(
        `wss://fstream.binance.com/ws/${symbol.toLowerCase()}@kline_${interval}`,
      );
      socket.onmessage = (event) => {
        let message: BinanceKlineTick;
        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }
        const k = message.k;
        if (!k) return;
        const open = Number(k.o);
        const high = Number(k.h);
        const low = Number(k.l);
        const close = Number(k.c);
        const volume = Number(k.v);
        setCandles((current) => {
          if (current.length === 0) return current;
          const last = current[current.length - 1];
          if (k.t === last.timestamp) {
            return [...current.slice(0, -1), { ...last, open, high, low, close, volume }];
          }
          if (k.t > last.timestamp) {
            const appended: Candle = { ...last, timestamp: k.t, open, high, low, close, volume };
            return [...current, appended];
          }
          return current;
        });
      };
      socket.onclose = () => {
        if (!stopped) reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      };
    }

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [symbol, interval]);

  return candles;
}
