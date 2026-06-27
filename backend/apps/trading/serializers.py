import re

from rest_framework import serializers

from .models import BotLog, MarketSnapshot, Trade, TradingBotConfig


class TradingBotConfigSerializer(serializers.ModelSerializer):
    live_trading_available = serializers.SerializerMethodField()
    live_trading_message = serializers.SerializerMethodField()

    class Meta:
        model = TradingBotConfig
        exclude = ("user",)
        read_only_fields = (
            "is_running",
            "created_at",
            "updated_at",
            "live_trading_available",
            "live_trading_message",
        )

    def _live_trading_status(self, obj) -> tuple[bool, str]:
        from django.conf import settings

        from .services.credential_service import decrypt_secret

        if not settings.ENABLE_LIVE_TRADING:
            return False, "Live trading is disabled by the server."
        credential = getattr(obj.user, "binance_credential", None)
        if not credential or not credential.is_active:
            return False, "Store an active Binance API credential."
        try:
            decrypt_secret(credential.api_secret_encrypted)
        except ValueError:
            return False, "Re-save the Binance API key and secret, then test the connection."
        if obj.live_mode_requested:
            return True, "Live mode is enabled for this symbol."
        return True, "Binance credential is ready. Enable live mode and save this configuration."

    def get_live_trading_available(self, obj) -> bool:
        return self._live_trading_status(obj)[0]

    def get_live_trading_message(self, obj) -> str:
        return self._live_trading_status(obj)[1]

    def validate_symbol(self, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,20}USDT", normalized):
            raise serializers.ValidationError("Symbol must be a valid USDT futures pair, for example BTCUSDT")
        return normalized

    def validate_timeframe_signal(self, value: str) -> str:
        allowed = {"1m", "3m", "5m", "15m", "30m", "1h", "4h"}
        if value not in allowed:
            raise serializers.ValidationError(f"Signal timeframe must be one of: {', '.join(sorted(allowed))}")
        return value

    def validate_timeframe_trend(self, value: str) -> str:
        allowed = {"15m", "30m", "1h", "4h"}
        if value not in allowed:
            raise serializers.ValidationError(f"Trend timeframe must be one of: {', '.join(sorted(allowed))}")
        return value

    def validate_leverage(self, value: int) -> int:
        if value < 1 or value > 125:
            raise serializers.ValidationError("Leverage must be between 1x and 125x")
        return value

    def validate_position_margin_usdt(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Position margin must be greater than 0 USDT")
        return value

    def validate_atr_multiplier_sl(self, value):
        if value < 0 or value > 2:
            raise serializers.ValidationError("SL ATR buffer must be between 0 and 2")
        return value

    def validate_atr_multiplier_tp(self, value):
        if value < 1 or value > 6:
            raise serializers.ValidationError("TP3 risk multiple must be between 1 and 6")
        return value

    def validate_max_open_positions(self, value: int) -> int:
        if value < 1 or value > 20:
            raise serializers.ValidationError("Maximum open positions must be between 1 and 20")
        return value

    def validate_max_margin_loss_percent(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Margin loss cap must be between 0% and 100%")
        return value

    def validate_entry_score_threshold(self, value: int) -> int:
        if value < 60 or value > 150:
            raise serializers.ValidationError("Entry score threshold must be between 60 and 150")
        return value


class MarketSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketSnapshot
        fields = "__all__"


class TradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trade
        fields = "__all__"
        read_only_fields = ("user",)


class BotLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotLog
        fields = "__all__"


class CredentialSerializer(serializers.Serializer):
    api_key = serializers.CharField(max_length=255, write_only=True)
    api_secret = serializers.CharField(max_length=255, write_only=True)
    is_active = serializers.BooleanField(default=True)
