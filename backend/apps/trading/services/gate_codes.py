"""Stable identifiers for every entry-rejection point.

Kept dependency-free so signal_service (pure scoring) can reference them
without importing Django models. Values are persisted in SignalDecision.result,
so never rename one — add a new code instead.
"""


class GateCode:
    # Score-level hard gates (signal_service.score_signal)
    MA_ALIGNMENT = "ma_alignment"
    MACRO_DIRECTION = "macro_direction"
    EXTENDED_MOVE = "extended_move"
    RSI_OVERSOLD = "rsi_oversold"
    PULLBACK_ZONE = "pullback_zone"
    REJECTION_CANDLE = "rejection_candle"
    ENTRY_LOCATION = "entry_location"
    BELOW_SCORE_THRESHOLD = "below_score_threshold"
    # Confirmation filters (market_snapshot_service)
    SIDEWAY_BLOCK = "sideway_block"
    TREND_ALIGNMENT = "trend_alignment"
    HTF_CONFIRM = "htf_confirm"
    BIAS_4H = "bias_4h"
    OI_CONFIRM = "oi_confirm"
    VOLUME_CONFIRM = "volume_confirm"
    MA7_SLOPE_CONFIRM = "ma7_slope_confirm"
    FUNDING_CONFIRM = "funding_confirm"
    # Cycle-level gates (tasks.process_config)
    CIRCUIT_BREAKER = "circuit_breaker"
    OPPOSITE_UNCONFIRMED = "opposite_unconfirmed"
    DAILY_LOSS = "daily_loss"
    MAX_POSITIONS = "max_positions"
    ATR_MIN = "atr_min"
    REGIME_CHOPPY = "regime_choppy"
    REVERSAL_HIGH_VOL = "reversal_high_vol"
    SUPPRESSED_TAG = "suppressed_tag"
    SUPPRESSED_SYMBOL = "suppressed_symbol"
    MIN_CONFIDENCE = "min_confidence"
    ATR_SPIKE = "atr_spike"
    FUNDING = "funding"
    TF_ALIGNMENT = "tf_alignment"
    SL_COOLDOWN = "sl_cooldown"
    VOLUME_SPIKE = "volume_spike"
    MA7_SLOPE = "ma7_slope"
    MARGIN_INSUFFICIENT = "margin_insufficient"
    RISK_LIMIT = "risk_limit"
    EXISTING_POSITION = "existing_position"
    EXCHANGE_POSITION = "exchange_position"

    ALL = tuple(
        v for k, v in list(vars().items()) if k.isupper() and isinstance(v, str)
    )
