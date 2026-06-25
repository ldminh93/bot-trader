from django.contrib import admin

from .models import BotLog, MarketSnapshot, Trade, TradingBotConfig, UserBinanceCredential

admin.site.register(UserBinanceCredential)
admin.site.register(TradingBotConfig)
admin.site.register(MarketSnapshot)
admin.site.register(Trade)
admin.site.register(BotLog)

