export interface BotConfig {
  id: number;
  symbol: string;
  timeframe_signal: string;
  timeframe_trend: string;
  leverage: number;
  margin_type: "isolated" | "cross";
  risk_per_trade_percent: string;
  max_daily_loss_percent: string;
  max_open_positions: number;
  adx_min: string;
  atr_multiplier_sl: string;
  atr_multiplier_tp: string;
  use_trailing_stop: boolean;
  trailing_atr_multiplier: string;
  enable_long: boolean;
  enable_short: boolean;
  is_running: boolean;
  live_mode_requested: boolean;
  live_trading_available: boolean;
  live_trading_message: string;
  paper_balance: string;
  position_margin_usdt: string | null;
}

export interface Candle {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  delta: number;
  cvd: number;
  ma7: number;
  ma25: number;
  ma99: number;
}

export type TrendState =
  | "SIDEWAY"
  | "EARLY_UPTREND"
  | "CONFIRMED_UPTREND"
  | "WEAK_UPTREND"
  | "EARLY_DOWNTREND"
  | "CONFIRMED_DOWNTREND"
  | "WEAK_DOWNTREND";

export interface MarketSnapshot {
  id: number;
  symbol: string;
  timeframe: string;
  price: string;
  ma7: string;
  ma25: string;
  ma99: string;
  delta: string;
  cvd: string;
  open_interest: string;
  open_interest_change_percent: string;
  funding_rate: string;
  top_trader_account_ratio: string;
  top_trader_position_ratio: string;
  adx: string;
  atr: string;
  volume: string;
  volume_ma20: string;
  trend: TrendState;
  created_at: string;
  payload: {
    trend_state: TrendState;
    trend_1h: TrendState;
    signal: "LONG" | "SHORT" | "NO_TRADE";
    long_score: number;
    short_score: number;
    risk_multiplier: number;
    reasons: string[];
    trend_reasons?: string[];
    sideways_reasons?: string[];
    open_interest_change_available?: boolean;
    statistics_period?: string;
    candles: Candle[];
    market_history?: {
      created_at: string;
      price: number;
      open_interest: number;
      funding_rate: number;
    }[];
  };
}

export interface Trade {
  id: number;
  symbol: string;
  side: "LONG" | "SHORT";
  status: "OPEN" | "CLOSED" | "CANCELLED";
  entry_price: string;
  exit_price: string | null;
  quantity: string;
  remaining_quantity: string;
  leverage: number;
  stop_loss: string;
  take_profit_1: string;
  take_profit_2: string;
  take_profit_3: string;
  realized_pnl: string;
  unrealized_pnl: string;
  pnl_percent: string;
  open_reason: string;
  close_reason: string;
  is_paper: boolean;
  opened_at: string;
  closed_at: string | null;
}

export interface BotLog {
  id: number;
  symbol: string;
  level: "INFO" | "WARNING" | "ERROR";
  message: string;
  created_at: string;
}

export interface TradeStats {
  realized_pnl: number;
  unrealized_pnl: number;
  total_profit: number;
  trades: number;
  win_rate: number;
  average_pnl_percent: number;
  daily: { day: string; pnl: number }[];
}
