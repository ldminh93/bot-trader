import pytest

from apps.trading.services.indicator_service import calculate_indicators


def make_candles(count: int = 150, direction: float = 1.0) -> list[dict]:
    candles = []
    price = 100.0
    for index in range(count):
        close = price + direction * (0.25 + index * 0.002)
        volume = 1000 + index * 5
        candles.append(
            {
                "timestamp": index,
                "open": price,
                "high": max(price, close) + 0.4,
                "low": min(price, close) - 0.4,
                "close": close,
                "volume": volume,
                "taker_buy_volume": volume * (0.6 if direction > 0 else 0.4),
            }
        )
        price = close
    return candles


def test_indicator_calculation_returns_complete_result():
    result = calculate_indicators(make_candles())
    assert result.ma7 > result.ma25 > result.ma99
    assert result.delta > 0
    assert result.cvd > 0
    assert result.atr > 0
    assert result.volume_ma20 > 0
    assert result.swing_high > result.swing_low


def test_requires_enough_candles():
    with pytest.raises(ValueError):
        calculate_indicators(make_candles(50))
