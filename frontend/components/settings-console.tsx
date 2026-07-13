"use client";

import { FloppyDisk, Key, Plus, ShieldCheck, TrendDown, TrendUp, Trash, Warning } from "@phosphor-icons/react";
import { FormEvent, useEffect, useState } from "react";

import { PageFrame } from "@/components/page-frame";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { api, getToken } from "@/lib/api";
import type { BotConfig, DiscordAlertConfig } from "@/lib/types";

const inputClass =
  "h-10 w-full rounded-[var(--radius)] border border-[var(--line-strong)] bg-[var(--background)] px-3 text-sm outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]";

export function SettingsConsole() {
  const [configs, setConfigs] = useState<BotConfig[]>([]);
  const [config, setConfig] = useState<BotConfig | null>(null);
  const [newSymbol, setNewSymbol] = useState("");
  const [busy, setBusy] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [discordConfig, setDiscordConfig] = useState<DiscordAlertConfig | null>(null);
  const [discordWebhook, setDiscordWebhook] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [confirmApplyAll, setConfirmApplyAll] = useState(false);
  const [confirmRemoveAll, setConfirmRemoveAll] = useState(false);
  const [showGainers, setShowGainers] = useState(true);
  const [showLosers, setShowLosers] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem("top_movers_config");
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as { showGainers?: boolean; showLosers?: boolean };
        setShowGainers(parsed.showGainers !== false);
        setShowLosers(parsed.showLosers !== false);
      } catch {
        // ignore malformed storage
      }
    }
  }, []);

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    api.configs()
      .then((items) => {
        setConfigs(items);
        setConfig(items[0] ?? null);
      })
      .catch((reason) => setError(reason.message));
    api.discordAlerts()
      .then(setDiscordConfig)
      .catch(() => undefined);
  }, []);

  function updateStoredConfig(nextConfig: BotConfig) {
    setConfirmApplyAll(false);
    setConfig((current) => current?.id === nextConfig.id ? nextConfig : current);
    setConfigs((items) => items
      .map((item) => item.id === nextConfig.id ? nextConfig : item)
      .sort((a, b) => a.symbol.localeCompare(b.symbol)));
  }

  async function saveConfig(event: FormEvent) {
    event.preventDefault();
    if (!config) return;
    setError("");
    try {
      await api.saveConfig(config);
      const refreshedConfigs = await api.configs();
      setConfigs(refreshedConfigs);
      setConfig(refreshedConfigs.find((item) => item.id === config.id) ?? null);
      setMessage(`${config.symbol} configuration saved.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save settings");
    }
  }

  async function applyToAll() {
    if (!config) return;
    const others = configs.filter((c) => c.id !== config.id);
    if (!others.length) return;
    setBusy(true);
    setError("");
    setConfirmApplyAll(false);
    try {
      // Strip per-coin identity and status; copy all strategy settings
      const {
        id: _id,
        symbol: _sym,
        is_running: _run,
        live_mode_requested: _live,
        live_trading_available: _avail,
        live_trading_message: _msg,
        ...strategy
      } = config;
      await Promise.all([
        api.saveConfig(config),
        ...others.map((other) => api.saveConfig({ ...strategy, symbol: other.symbol })),
      ]);
      const refreshed = await api.configs();
      setConfigs(refreshed);
      setConfig(refreshed.find((c) => c.id === config.id) ?? null);
      setMessage(`Strategy settings applied to ${others.length} other coin${others.length > 1 ? "s" : ""}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to apply settings to all coins");
    } finally {
      setBusy(false);
    }
  }

  async function addCoin(event: FormEvent) {
    event.preventDefault();
    const symbol = newSymbol.trim().toUpperCase();
    if (!symbol) return;
    const existing = configs.find((item) => item.symbol === symbol);
    if (existing) {
      setConfig(existing);
      setNewSymbol("");
      setMessage(`${symbol} is already in the scanner.`);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const added = await api.addConfig(symbol, config?.symbol);
      setConfigs((items) => {
        const withoutDuplicate = items.filter((item) => item.id !== added.id);
        return [...withoutDuplicate, added].sort((a, b) => a.symbol.localeCompare(b.symbol));
      });
      setConfig(added);
      setNewSymbol("");
      setMessage(`${added.symbol} added. Start scanning when you're ready.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to add coin");
    } finally {
      setBusy(false);
    }
  }

  async function toggleScan(item: BotConfig) {
    setBusy(true);
    setError("");
    try {
      updateStoredConfig(item.is_running ? await api.stop(item.symbol) : await api.start(item.symbol));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to change scanner status");
    } finally {
      setBusy(false);
    }
  }

  async function removeCoin(item: BotConfig) {
    setBusy(true);
    setError("");
    try {
      await api.removeConfig(item.symbol);
      const remaining = configs.filter((candidate) => candidate.id !== item.id);
      setConfigs(remaining);
      if (config?.id === item.id) setConfig(remaining[0] ?? null);
      setMessage(`${item.symbol} removed from scanner.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to remove coin");
    } finally {
      setBusy(false);
    }
  }

  async function pauseAllCoins() {
    setBusy(true);
    setError("");
    try {
      const result = await api.pauseAllConfigs();
      const refreshed = await api.configs();
      setConfigs(refreshed);
      setConfig((current) => refreshed.find((item) => item.id === current?.id) ?? refreshed[0] ?? null);
      setMessage(`Paused ${result.paused.length} coin${result.paused.length === 1 ? "" : "s"}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to pause all coins");
    } finally {
      setBusy(false);
    }
  }

  async function scanAllCoins() {
    setBusy(true);
    setError("");
    try {
      const result = await api.scanAllConfigs();
      const refreshed = await api.configs();
      setConfigs(refreshed);
      setConfig((current) => refreshed.find((item) => item.id === current?.id) ?? refreshed[0] ?? null);
      setMessage(`Started scanning ${result.started.length} coin${result.started.length === 1 ? "" : "s"}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to start scanning all coins");
    } finally {
      setBusy(false);
    }
  }

  async function removeAllCoins() {
    setBusy(true);
    setError("");
    setConfirmRemoveAll(false);
    try {
      const result = await api.removeAllConfigs();
      const refreshed = await api.configs();
      setConfigs(refreshed);
      setConfig(refreshed[0] ?? null);
      setMessage(
        `Removed ${result.removed.length} coin${result.removed.length === 1 ? "" : "s"}.` +
          (result.skipped.length ? ` Kept ${result.skipped.length} with open positions.` : ""),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to remove all coins");
    } finally {
      setBusy(false);
    }
  }

  async function saveCredential(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api.saveCredential(apiKey, apiSecret);
      const refreshedConfigs = await api.configs();
      setConfigs(refreshedConfigs);
      setConfig((current) => (
        refreshedConfigs.find((item) => item.id === current?.id)
        ?? refreshedConfigs[0]
        ?? null
      ));
      setApiSecret("");
      setMessage("Credential encrypted and stored. Test the connection, then enable live mode for the coin you want to trade.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save credential");
    }
  }

  async function testConnection() {
    setError("");
    try {
      const result = await api.testConnection();
      setMessage(result.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Connection test failed");
    }
  }

  async function syncBalance() {
    if (!config) return;
    setError("");
    try {
      const result = await api.binanceBalance();
      setConfig({ ...config, paper_balance: String(result.balance) });
      setMessage(`Synced ${result.balance.toFixed(2)} USDT from Binance. Click Save to apply.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to fetch balance from Binance");
    }
  }

  async function saveDiscordAlerts(event: FormEvent) {
    event.preventDefault();
    if (!discordConfig) return;
    setError("");
    try {
      const saved = await api.saveDiscordAlerts({
        ...discordConfig,
        ...(discordWebhook.trim() ? { webhook_url: discordWebhook.trim() } : {}),
      });
      setDiscordConfig(saved);
      setDiscordWebhook("");
      setMessage("Discord alert settings saved.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save Discord alerts");
    }
  }

  async function testDiscordAlerts() {
    setError("");
    try {
      const result = await api.testDiscordAlerts();
      setMessage(result.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Discord alert test failed");
    }
  }

  function saveTopMoversConfig(next: { showGainers: boolean; showLosers: boolean }) {
    localStorage.setItem("top_movers_config", JSON.stringify(next));
    setShowGainers(next.showGainers);
    setShowLosers(next.showLosers);
    setMessage("Top Movers display settings saved.");
  }

  const riskPreview = config ? buildRiskPreview(config) : null;

  return (
    <PageFrame title="Settings" description="Risk controls, strategy thresholds, and exchange access.">
      {(message || error) && (
        <div className={`mb-4 flex items-start gap-3 rounded-[var(--radius)] border p-3 text-sm ${error ? "border-[var(--negative)]/40 bg-[var(--negative)]/10 text-[#ff9b9b]" : "border-[var(--positive)]/40 bg-[var(--positive)]/10 text-[#8ce9b8]"}`}>
          {error ? <Warning size={18} /> : <ShieldCheck size={18} />}
          {error || message}
        </div>
      )}
      <div className="grid min-w-0 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel className="min-w-0">
          <PanelHeader
            title="Scanner coins"
            action={<span className="font-mono text-[10px] text-[var(--muted)]">{configs.filter((item) => item.is_running).length} active / {configs.length} total</span>}
          />
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--line)] p-4">
            <Button type="button" size="sm" variant="secondary" disabled={busy || !configs.length} onClick={() => void pauseAllCoins()}>
              Pause all
            </Button>
            <Button type="button" size="sm" variant="secondary" disabled={busy || !configs.length} onClick={() => void scanAllCoins()}>
              Scan all
            </Button>
            {!confirmRemoveAll ? (
              <Button
                type="button"
                size="sm"
                variant="danger"
                disabled={busy || !configs.length}
                onClick={() => setConfirmRemoveAll(true)}
              >
                <Trash size={16} />Remove all
              </Button>
            ) : (
              <>
                <Button type="button" size="sm" variant="danger" disabled={busy} onClick={() => void removeAllCoins()}>
                  Confirm: remove {configs.length} coin{configs.length === 1 ? "" : "s"}
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setConfirmRemoveAll(false)}>
                  Cancel
                </Button>
              </>
            )}
          </div>
          <div className="border-b border-[var(--line)] p-4">
            <form onSubmit={addCoin} className="flex flex-col gap-2 sm:flex-row">
              <input
                aria-label="New futures symbol"
                className={inputClass}
                value={newSymbol}
                onChange={(event) => setNewSymbol(event.target.value.toUpperCase().replace(/\s/g, ""))}
                placeholder="ETHUSDT"
                required
              />
              <Button disabled={busy || !newSymbol.trim()}>
                <Plus size={17} />Add coin
              </Button>
            </form>
            <p className="mt-2 text-xs leading-5 text-[var(--muted)]">
              New coins copy the selected coin&apos;s strategy settings and stay paused until you click Scan.
            </p>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {configs.map((item) => (
                <div
                  key={item.id}
                  className={`flex items-center gap-2 rounded-[var(--radius)] border p-2 ${config?.id === item.id ? "border-[var(--accent)] bg-[var(--accent)]/[0.05]" : "border-[var(--line)] bg-[var(--background)]"}`}
                >
                  <button
                    type="button"
                    onClick={() => { setConfig(item); setConfirmApplyAll(false); }}
                    className="min-w-0 flex-1 px-1 text-left"
                  >
                    <span className="flex items-center gap-1.5">
                      <span className="block truncate font-mono text-sm font-bold">{item.symbol}</span>
                      {item.top_mover_side && (
                        <span
                          className={`shrink-0 rounded px-1 text-[9px] font-bold uppercase tracking-[0.05em] ${item.top_mover_side === "gainer" ? "bg-[var(--positive)]/15 text-[var(--positive)]" : "bg-[var(--negative)]/15 text-[var(--negative)]"}`}
                          title={item.top_mover_side === "gainer" ? "Auto-registered from top gainers" : "Auto-registered from top losers"}
                        >
                          {item.top_mover_side === "gainer" ? "Long" : "Short"}
                        </span>
                      )}
                    </span>
                    <span className={`text-[10px] font-bold uppercase tracking-[0.08em] ${item.is_running ? "text-[var(--positive)]" : "text-[var(--muted)]"}`}>
                      {item.is_running ? "Scanning" : "Paused"}
                    </span>
                  </button>
                  <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void toggleScan(item)}>
                    {item.is_running ? "Pause" : "Scan"}
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    disabled={busy}
                    onClick={() => void removeCoin(item)}
                    aria-label={`Remove ${item.symbol}`}
                    title={`Remove ${item.symbol}`}
                  >
                    <Trash size={16} />
                  </Button>
                </div>
              ))}
            </div>
          </div>
          <PanelHeader title={config ? `${config.symbol} strategy` : "Strategy settings"} />
          {config ? (
            <form onSubmit={saveConfig} className="grid gap-5 p-4 sm:grid-cols-2">
              <Field label="Symbol">
                <input className={`${inputClass} font-mono text-[var(--muted)]`} value={config.symbol} readOnly />
              </Field>
              <Field label="Leverage">
                <input className={inputClass} type="number" min="1" max="125" value={config.leverage} onChange={(event) => setConfig({ ...config, leverage: Number(event.target.value) })} />
              </Field>
              <Field label="Signal timeframe">
                <select className={inputClass} value={config.timeframe_signal} onChange={(event) => setConfig({ ...config, timeframe_signal: event.target.value })}>
                  <option value="1m">1 minute</option>
                  <option value="3m">3 minutes</option>
                  <option value="5m">5 minutes</option>
                  <option value="15m">15 minutes</option>
                  <option value="30m">30 minutes</option>
                  <option value="1h">1 hour</option>
                  <option value="4h">4 hours</option>
                </select>
              </Field>
              <Field label="Trend timeframe">
                <select className={inputClass} value={config.timeframe_trend} onChange={(event) => setConfig({ ...config, timeframe_trend: event.target.value })}>
                  <option value="15m">15 minutes</option>
                  <option value="30m">30 minutes</option>
                  <option value="1h">1 hour</option>
                  <option value="4h">4 hours</option>
                </select>
              </Field>
              <Field label="Margin type">
                <select className={inputClass} value={config.margin_type} onChange={(event) => setConfig({ ...config, margin_type: event.target.value as "isolated" | "cross" })}>
                  <option value="isolated">Isolated</option>
                  <option value="cross">Cross</option>
                </select>
              </Field>
              <Field label="Paper balance (USDT)">
                <div className="flex gap-2">
                  <input className={inputClass} type="number" min="100" value={config.paper_balance} onChange={(event) => setConfig({ ...config, paper_balance: event.target.value })} />
                  <Button type="button" variant="secondary" onClick={syncBalance}>Sync from Binance</Button>
                </div>
                <span className="font-normal leading-5 text-[var(--muted)]">
                  Fetches your live Binance futures balance and fills this field. Save to apply it.
                </span>
              </Field>
              <Field label="Position margin (USDT)">
                <input
                  className={inputClass}
                  type="number"
                  min="1"
                  step="1"
                  value={config.position_margin_usdt ?? ""}
                  placeholder="Risk-based"
                  onChange={(event) => setConfig({
                    ...config,
                    position_margin_usdt: event.target.value || null,
                  })}
                />
                <span className="font-normal leading-5 text-[var(--muted)]">
                  {config.position_margin_usdt
                    ? `${config.position_margin_usdt} USDT margin creates about ${(Number(config.position_margin_usdt) * config.leverage).toFixed(2)} USDT notional at x${config.leverage}.`
                    : "Leave empty to size positions from risk percentage and stop distance."}
                </span>
              </Field>
              <Field label="Maximum open positions">
                <input
                  className={inputClass}
                  type="number"
                  min="1"
                  max="20"
                  value={config.max_open_positions}
                  onChange={(event) => setConfig({
                    ...config,
                    max_open_positions: Number(event.target.value),
                  })}
                />
                <span className="font-normal leading-5 text-[var(--muted)]">
                  Account-wide limit shared by every scanned coin.
                </span>
              </Field>
              <Field label="Risk per trade (%)">
                <input className={inputClass} type="number" min="0.1" max="10" step="0.1" value={config.risk_per_trade_percent} onChange={(event) => setConfig({ ...config, risk_per_trade_percent: event.target.value })} />
              </Field>
              <Field label="Max daily loss (%)">
                <input className={inputClass} type="number" min="0.5" max="20" step="0.1" value={config.max_daily_loss_percent} onChange={(event) => setConfig({ ...config, max_daily_loss_percent: event.target.value })} />
              </Field>
              <Field label="Entry score threshold">
                <input
                  className={inputClass}
                  type="number"
                  min="60"
                  max="150"
                  step="1"
                  value={config.entry_score_threshold}
                  onChange={(event) => setConfig({ ...config, entry_score_threshold: Number(event.target.value) })}
                />
                <span className="font-normal leading-5 text-[var(--muted)]">
                  Higher values mean fewer but stricter entries.
                </span>
              </Field>
              <Field label="Margin loss cap (%)">
                <input
                  className={inputClass}
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={config.max_margin_loss_percent}
                  onChange={(event) => setConfig({ ...config, max_margin_loss_percent: event.target.value })}
                />
                <span className="font-normal leading-5 text-[var(--muted)]">
                  Skip entries when the technical stop would lose more than this percent of position margin. Set to 0 to disable this check.
                </span>
              </Field>
              <Field label="ADX minimum">
                <input className={inputClass} type="number" min="5" max="60" value={config.adx_min} onChange={(event) => setConfig({ ...config, adx_min: event.target.value })} />
              </Field>
              <Field label="ADX period">
                <input className={inputClass} type="number" min="2" max="50" value={config.adx_period} onChange={(event) => setConfig({ ...config, adx_period: Number(event.target.value) })} />
                <span className="font-normal leading-5 text-[var(--muted)]">
                  Lookback candles used to calculate ADX/ATR. Default 14.
                </span>
              </Field>
              <Field label="SL ATR buffer">
                <input className={inputClass} type="number" min="0" max="2" step="0.05" value={config.atr_multiplier_sl} onChange={(event) => setConfig({ ...config, atr_multiplier_sl: event.target.value })} />
                <span className="font-normal leading-5 text-[var(--muted)]">
                  Added beyond the lowest MA for LONG or highest MA for SHORT. Entries above your margin loss cap are skipped.
                </span>
              </Field>
              <Field label="TP3 risk multiple">
                <input className={inputClass} type="number" min="1" max="6" step="0.5" value={config.atr_multiplier_tp} onChange={(event) => setConfig({ ...config, atr_multiplier_tp: event.target.value })} />
                <span className="font-normal leading-5 text-[var(--muted)]">
                  TP1, TP2, and TP3 divide this target into three equal R steps.
                </span>
              </Field>
              <Field label="Trailing ATR multiplier">
                <input className={inputClass} type="number" min="0.2" max="10" step="0.1" value={config.trailing_atr_multiplier} onChange={(event) => setConfig({ ...config, trailing_atr_multiplier: event.target.value })} />
              </Field>
              <Field label="Max entry distance (ATR)">
                <input
                  className={inputClass}
                  type="number"
                  min="0.2"
                  max="5"
                  step="0.1"
                  value={config.max_entry_distance_atr}
                  onChange={(event) => setConfig({ ...config, max_entry_distance_atr: event.target.value })}
                />
                <span className="font-normal leading-5 text-[var(--muted)]">
                  Pullback mode waits when price is too far from MA7/MA25.
                </span>
              </Field>
              <div className="grid gap-3 sm:col-span-2 sm:grid-cols-3">
                <Toggle label="Allow long" checked={config.enable_long} onChange={(value) => setConfig({ ...config, enable_long: value })} />
                <Toggle label="Allow short" checked={config.enable_short} onChange={(value) => setConfig({ ...config, enable_short: value })} />
                <Toggle label="Trailing stop" checked={config.use_trailing_stop} onChange={(value) => setConfig({ ...config, use_trailing_stop: value })} />
              </div>
              <div className="grid gap-3 sm:col-span-2 sm:grid-cols-3">
                <Toggle
                  label="Trend alignment"
                  checked={config.require_trend_alignment}
                  onChange={(value) => setConfig({ ...config, require_trend_alignment: value })}
                />
                <Toggle
                  label="Require OI"
                  checked={config.require_open_interest_confirmation}
                  onChange={(value) => setConfig({ ...config, require_open_interest_confirmation: value })}
                />
                <Toggle
                  label="Require volume"
                  checked={config.require_volume_confirmation}
                  onChange={(value) => setConfig({ ...config, require_volume_confirmation: value })}
                />
              </div>
              <div className="sm:col-span-2">
                <Toggle
                  label="Confirmed HTF only"
                  checked={config.require_confirmed_higher_tf ?? false}
                  onChange={(value) => setConfig({ ...config, require_confirmed_higher_tf: value })}
                />
                <p className="mt-2 text-xs leading-5 text-[var(--muted)]">
                  Block entries when the trend timeframe shows a weak or early trend. Only allows LONG on{" "}
                  <strong className="text-[var(--text)]">confirmed_uptrend</strong>, SHORT on{" "}
                  <strong className="text-[var(--text)]">confirmed_downtrend</strong>. Most impactful setting for reducing{" "}
                  <code className="rounded bg-[var(--surface-raised)] px-1">higher:weak_uptrend</code> losses.
                </p>
              </div>
              <div className="grid gap-3 sm:col-span-2 sm:grid-cols-2">
                <div>
                  <Toggle
                    label="Require MA7 slope"
                    checked={config.require_ma7_slope_confirmation ?? false}
                    onChange={(value) => setConfig({ ...config, require_ma7_slope_confirmation: value })}
                  />
                  <p className="mt-2 text-xs leading-5 text-[var(--muted)]">
                    Block LONG when MA7 slope has flattened or turned down (and SHORT when it has turned up), even if the trend
                    is otherwise confirmed.
                  </p>
                </div>
                <div>
                  <Toggle
                    label="Require funding"
                    checked={config.require_funding_confirmation ?? false}
                    onChange={(value) => setConfig({ ...config, require_funding_confirmation: value })}
                  />
                  <p className="mt-2 text-xs leading-5 text-[var(--muted)]">
                    Block entries when funding is outside the acceptable band, avoiding crowded/overheated positioning.
                  </p>
                </div>
              </div>
              <div className="grid gap-3 sm:col-span-2 sm:grid-cols-2">
                <Toggle
                  label="Auto regime mode"
                  checked={config.auto_regime_enabled}
                  onChange={(value) => setConfig({ ...config, auto_regime_enabled: value })}
                />
                <Toggle
                  label="Confidence leverage"
                  checked={config.confidence_leverage_enabled}
                  onChange={(value) => setConfig({ ...config, confidence_leverage_enabled: value })}
                />
              </div>
              <div className="grid gap-3 sm:col-span-2 sm:grid-cols-2">
                <Toggle
                  label="Closed candle entry"
                  checked={config.use_closed_candle_confirmation}
                  onChange={(value) => setConfig({ ...config, use_closed_candle_confirmation: value })}
                />
                <Toggle
                  label="Pullback entry"
                  checked={config.pullback_entry_enabled}
                  onChange={(value) => setConfig({ ...config, pullback_entry_enabled: value })}
                />
              </div>

              {/* Early exit controls */}
              <div className="sm:col-span-2 border-t border-[var(--line)] pt-3">
                <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">Early exit controls</p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Min conditions to exit (1–7)">
                    <input
                      className={inputClass}
                      type="number"
                      min="1"
                      max="7"
                      step="1"
                      value={config.early_exit_min_conditions ?? 3}
                      onChange={(event) => setConfig({ ...config, early_exit_min_conditions: Number(event.target.value) })}
                    />
                    <span className="font-normal leading-5 text-[var(--muted)]">
                      How many bearish signals must align before the bot exits early. Default 3 (was 2). Higher = less sensitive to short-term noise.
                    </span>
                  </Field>
                  <Field label="Grace period (15m candles)">
                    <input
                      className={inputClass}
                      type="number"
                      min="0"
                      max="20"
                      step="1"
                      value={config.early_exit_grace_candles ?? 2}
                      onChange={(event) => setConfig({ ...config, early_exit_grace_candles: Number(event.target.value) })}
                    />
                    <span className="font-normal leading-5 text-[var(--muted)]">
                      Block early exit for the first N × 15 minutes after entry. Default 2 = 30 min buffer for the trade to breathe.
                    </span>
                  </Field>
                </div>
              </div>

              {/* Loss protection controls */}
              <div className="sm:col-span-2 border-t border-[var(--line)] pt-3">
                <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">Loss protection controls</p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Re-entry cooldown (candles)">
                    <input
                      className={inputClass}
                      type="number"
                      min="0"
                      max="50"
                      step="1"
                      value={config.sl_cooldown_candles ?? 0}
                      onChange={(event) => setConfig({ ...config, sl_cooldown_candles: Number(event.target.value) })}
                    />
                    <span className="font-normal leading-5 text-[var(--muted)]">
                      Candles to wait before re-entering this symbol after a stop-loss hit. 0 disables the cooldown.
                    </span>
                  </Field>
                  <Field label="Max consecutive losses">
                    <input
                      className={inputClass}
                      type="number"
                      min="0"
                      max="10"
                      step="1"
                      value={config.max_consecutive_losses ?? 0}
                      onChange={(event) => setConfig({ ...config, max_consecutive_losses: Number(event.target.value) })}
                    />
                    <span className="font-normal leading-5 text-[var(--muted)]">
                      Pause new entries on this symbol after N losses in a row. 0 disables the circuit breaker.
                    </span>
                  </Field>
                  <Field label="Circuit breaker duration (hours)">
                    <input
                      className={inputClass}
                      type="number"
                      min="0.5"
                      max="48"
                      step="0.5"
                      value={config.circuit_breaker_hours ?? 4}
                      onChange={(event) => setConfig({ ...config, circuit_breaker_hours: event.target.value })}
                    />
                    <span className="font-normal leading-5 text-[var(--muted)]">
                      How long entries stay blocked once the consecutive-loss circuit breaker trips.
                    </span>
                  </Field>
                  <Toggle
                    label="Auto-suppress losing tags"
                    checked={config.auto_suppress_losing_tags ?? false}
                    onChange={(value) => setConfig({ ...config, auto_suppress_losing_tags: value })}
                  />
                  <Toggle
                    label="Auto-suppress losing symbols"
                    checked={config.auto_suppress_losing_symbols ?? false}
                    onChange={(value) => setConfig({ ...config, auto_suppress_losing_symbols: value })}
                  />
                  <Field label="Minimum confidence to trade">
                    <input
                      className={inputClass}
                      type="number"
                      min="0"
                      max="160"
                      step="1"
                      value={config.min_confidence_to_trade ?? 0}
                      onChange={(event) => setConfig({ ...config, min_confidence_to_trade: Number(event.target.value) })}
                    />
                    <span className="font-normal leading-5 text-[var(--muted)]">
                      Block entries below this confidence score (sizing input, not just entry score). 0 disables the filter.
                    </span>
                  </Field>
                </div>
                <p className="mt-3 text-xs leading-5 text-[var(--muted)]">
                  Auto-suppress blocks entries whose setup tag (e.g. <code className="rounded bg-[var(--surface-raised)] px-1">state:confirmed_uptrend</code>) has &lt;40% win rate over its last 20+ closed trades.
                  Auto-suppress losing symbols applies the same &lt;40%/20-trade rule per coin instead of per tag.
                </p>
              </div>

              <div className="sm:col-span-2">
                <Toggle
                  label="Live trading for all scanner coins"
                  checked={config.live_mode_requested}
                  disabled={!config.live_trading_available}
                  onChange={(value) => setConfig({ ...config, live_mode_requested: value })}
                />
                <p className="mt-2 text-xs leading-5 text-[var(--muted)]">
                  This account-wide switch applies to every scanner coin. {config.live_trading_message}
                </p>
              </div>
              <div className="sm:col-span-2">
                {riskPreview && (
                  <div className="mb-4 grid gap-3 rounded-[var(--radius)] border border-[var(--line)] bg-[var(--background)] p-3 sm:grid-cols-4">
                    <PreviewStat label="Notional" value={`${riskPreview.notional} USDT`} />
                    <PreviewStat label="Margin" value={`${riskPreview.margin} USDT`} />
                    <PreviewStat label="Stop loss" value={`${riskPreview.stopLoss} USDT`} />
                    <PreviewStat label="Daily capacity" value={`${riskPreview.dailyLosses} losses`} />
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <Button disabled={busy}><FloppyDisk size={17} />Save configuration</Button>
                  {configs.length > 1 && !confirmApplyAll && (
                    <Button type="button" variant="secondary" disabled={busy} onClick={() => setConfirmApplyAll(true)}>
                      Apply to all coins
                    </Button>
                  )}
                  {confirmApplyAll && (
                    <>
                      <Button type="button" variant="danger" disabled={busy} onClick={() => void applyToAll()}>
                        Confirm: overwrite {configs.length - 1} coin{configs.length > 2 ? "s" : ""}
                      </Button>
                      <Button type="button" variant="ghost" onClick={() => setConfirmApplyAll(false)}>
                        Cancel
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </form>
          ) : (
            <div className="p-8 text-center text-sm text-[var(--muted)]">
              Add a USDT futures coin to create its scanner configuration.
            </div>
          )}
        </Panel>

        <div className="grid min-w-0 content-start gap-4">
          <Panel className="min-w-0">
            <PanelHeader title="Binance API credential" />
            <form onSubmit={saveCredential} className="grid gap-4 p-4">
              <p className="text-sm leading-6 text-[var(--muted)]">
                Use a restricted Futures key with withdrawals disabled. The API secret is encrypted at rest and never returned.
              </p>
              <Field label="API key">
                <input className={inputClass} autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} required />
              </Field>
              <Field label="API secret">
                <input className={inputClass} type="password" autoComplete="new-password" value={apiSecret} onChange={(event) => setApiSecret(event.target.value)} required />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button><Key size={17} />Store credential</Button>
                <Button type="button" variant="secondary" onClick={testConnection}>Test connection</Button>
              </div>
            </form>
          </Panel>
          <Panel className="min-w-0 border-[var(--accent)]/30 bg-[var(--accent)]/[0.04]">
            <div className="p-4">
              <p className="font-semibold text-[var(--accent)]">Live trading safety lock</p>
              <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
                Live mode requires ENABLE_LIVE_TRADING=true on the server, an active credential, and explicit user opt-in. This deployment reports{" "}
                <strong className="text-[var(--text)]">{config?.live_trading_available ? "ready" : "locked"}</strong>.
                {config ? ` ${config.live_trading_message}` : ""}
              </p>
            </div>
          </Panel>
          <Panel className="min-w-0">
            <PanelHeader title="Top Movers display" />
            <div className="grid gap-3 p-4">
              <p className="text-xs leading-5 text-[var(--muted)]">
                Control which lists appear on the Top Movers page. Disabling a list hides it from view but does not affect scanning.
              </p>
              <Toggle
                label={
                  <span className="flex items-center gap-2">
                    <TrendUp size={14} className="text-[var(--positive)]" />
                    Show Gainers list
                  </span>
                }
                checked={showGainers}
                onChange={(value) => saveTopMoversConfig({ showGainers: value, showLosers })}
              />
              <Toggle
                label={
                  <span className="flex items-center gap-2">
                    <TrendDown size={14} className="text-[var(--negative)]" />
                    Show Losers list
                  </span>
                }
                checked={showLosers}
                onChange={(value) => saveTopMoversConfig({ showGainers, showLosers: value })}
              />
            </div>
          </Panel>
          <Panel className="min-w-0">
            <PanelHeader title="Discord alerts" />
            <form onSubmit={saveDiscordAlerts} className="grid gap-4 p-4">
              <Field label="Webhook URL">
                <input
                  className={inputClass}
                  type="password"
                  autoComplete="off"
                  placeholder={discordConfig?.webhook_configured ? "Configured. Leave blank to keep current webhook." : "Discord webhook URL"}
                  value={discordWebhook}
                  onChange={(event) => setDiscordWebhook(event.target.value)}
                />
              </Field>
              {discordConfig && (
                <>
                  <Toggle
                    label="Enable Discord alerts"
                    checked={discordConfig.is_enabled}
                    onChange={(value) => setDiscordConfig({ ...discordConfig, is_enabled: value })}
                  />
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Toggle
                      label="Info"
                      checked={discordConfig.notify_info}
                      onChange={(value) => setDiscordConfig({ ...discordConfig, notify_info: value })}
                    />
                    <Toggle
                      label="Warning"
                      checked={discordConfig.notify_warning}
                      onChange={(value) => setDiscordConfig({ ...discordConfig, notify_warning: value })}
                    />
                  <Toggle
                    label="Error"
                    checked={discordConfig.notify_error}
                    onChange={(value) => setDiscordConfig({ ...discordConfig, notify_error: value })}
                  />
                </div>
                  <Toggle
                    label="Escalate repeated errors"
                    checked={discordConfig.error_escalation_enabled}
                    onChange={(value) => setDiscordConfig({ ...discordConfig, error_escalation_enabled: value })}
                  />
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Repeat threshold">
                      <input
                        className={inputClass}
                        type="number"
                        min="2"
                        max="20"
                        value={discordConfig.error_escalation_threshold}
                        onChange={(event) => setDiscordConfig({ ...discordConfig, error_escalation_threshold: Number(event.target.value) })}
                      />
                    </Field>
                    <Field label="Window minutes">
                      <input
                        className={inputClass}
                        type="number"
                        min="1"
                        max="240"
                        value={discordConfig.error_escalation_window_minutes}
                        onChange={(event) => setDiscordConfig({ ...discordConfig, error_escalation_window_minutes: Number(event.target.value) })}
                      />
                    </Field>
                  </div>
                </>
              )}
              <div className="flex flex-wrap gap-2">
                <Button disabled={!discordConfig}>Save alerts</Button>
                <Button type="button" variant="secondary" disabled={!discordConfig?.webhook_configured} onClick={testDiscordAlerts}>
                  Test Discord
                </Button>
              </div>
            </form>
          </Panel>
        </div>
      </div>
    </PageFrame>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="grid gap-2 text-xs font-semibold text-[var(--muted)]">{label}{children}</label>;
}

function Toggle({ label, checked, disabled = false, onChange }: { label: React.ReactNode; checked: boolean; disabled?: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className={`flex h-11 items-center justify-between rounded-[var(--radius)] border border-[var(--line)] bg-[var(--background)] px-3 text-sm font-semibold ${disabled ? "opacity-50" : ""}`}>
      {label}
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} className="size-4 accent-[var(--accent)]" />
    </label>
  );
}

function PreviewStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">{label}</p>
      <p className="mt-1 font-mono text-sm font-bold">{value}</p>
    </div>
  );
}

function buildRiskPreview(config: BotConfig) {
  const leverage = Math.max(Number(config.leverage) || 1, 1);
  const paperBalance = Math.max(Number(config.paper_balance) || 0, 0);
  const riskPercent = Math.max(Number(config.risk_per_trade_percent) || 0, 0);
  const dailyLossPercent = Math.max(Number(config.max_daily_loss_percent) || 0, 0);
  const fixedMargin = Number(config.position_margin_usdt || 0);
  const margin = fixedMargin > 0 ? fixedMargin : paperBalance * riskPercent / 100;
  const notional = margin * leverage;
  const stopLoss = fixedMargin > 0
    ? margin * Math.max(Number(config.max_margin_loss_percent) || 0, 0) / 100
    : paperBalance * riskPercent / 100;
  const dailyLoss = paperBalance * dailyLossPercent / 100;
  const dailyLosses = stopLoss > 0 ? Math.floor(dailyLoss / stopLoss) : 0;
  return {
    margin: margin.toFixed(2),
    notional: notional.toFixed(2),
    stopLoss: stopLoss.toFixed(2),
    dailyLosses: String(dailyLosses),
  };
}
