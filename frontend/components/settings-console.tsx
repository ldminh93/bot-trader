"use client";

import { FloppyDisk, Key, Plus, ShieldCheck, Trash, Warning } from "@phosphor-icons/react";
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

  return (
    <PageFrame title="Settings" description="Risk controls, strategy thresholds, and exchange access.">
      {(message || error) && (
        <div className={`mb-4 flex items-start gap-3 rounded-[var(--radius)] border p-3 text-sm ${error ? "border-[var(--negative)]/40 bg-[var(--negative)]/10 text-[#ff9b9b]" : "border-[var(--positive)]/40 bg-[var(--positive)]/10 text-[#8ce9b8]"}`}>
          {error ? <Warning size={18} /> : <ShieldCheck size={18} />}
          {error || message}
        </div>
      )}
      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel>
          <PanelHeader
            title="Scanner coins"
            action={<span className="font-mono text-[10px] text-[var(--muted)]">{configs.filter((item) => item.is_running).length} active / {configs.length} total</span>}
          />
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
                    onClick={() => setConfig(item)}
                    className="min-w-0 flex-1 px-1 text-left"
                  >
                    <span className="block truncate font-mono text-sm font-bold">{item.symbol}</span>
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
                <input className={inputClass} type="number" min="100" value={config.paper_balance} onChange={(event) => setConfig({ ...config, paper_balance: event.target.value })} />
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
                <Button disabled={busy}><FloppyDisk size={17} />Save configuration</Button>
              </div>
            </form>
          ) : (
            <div className="p-8 text-center text-sm text-[var(--muted)]">
              Add a USDT futures coin to create its scanner configuration.
            </div>
          )}
        </Panel>

        <div className="grid content-start gap-4">
          <Panel>
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
          <Panel className="border-[var(--accent)]/30 bg-[var(--accent)]/[0.04]">
            <div className="p-4">
              <p className="font-semibold text-[var(--accent)]">Live trading safety lock</p>
              <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
                Live mode requires ENABLE_LIVE_TRADING=true on the server, an active credential, and explicit user opt-in. This deployment reports{" "}
                <strong className="text-[var(--text)]">{config?.live_trading_available ? "ready" : "locked"}</strong>.
                {config ? ` ${config.live_trading_message}` : ""}
              </p>
            </div>
          </Panel>
          <Panel>
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

function Toggle({ label, checked, disabled = false, onChange }: { label: string; checked: boolean; disabled?: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className={`flex h-11 items-center justify-between rounded-[var(--radius)] border border-[var(--line)] bg-[var(--background)] px-3 text-sm font-semibold ${disabled ? "opacity-50" : ""}`}>
      {label}
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} className="size-4 accent-[var(--accent)]" />
    </label>
  );
}
