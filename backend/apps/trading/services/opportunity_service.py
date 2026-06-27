from django.utils import timezone

from apps.trading.models import MarketSnapshot, TradingBotConfig


def grade_from_context(confidence_score: int, alignment: str, signal: str, regime: str) -> str:
    if signal == "NO_TRADE":
        return "D"
    score = int(confidence_score or 0)
    if alignment == "aligned":
        score += 8
    if regime == "EXPANSION":
        score += 8
    elif regime == "TRENDING":
        score += 5
    elif regime in {"CHOPPY", "HIGH_VOLATILITY"}:
        score -= 10
    if score >= 125:
        return "A"
    if score >= 105:
        return "B"
    if score >= 90:
        return "C"
    return "D"


def opportunity_score(payload: dict) -> int:
    signal = payload.get("signal", "NO_TRADE")
    confidence = int(payload.get("confidence_score") or 0)
    alignment = (payload.get("higher_timeframe_bias") or {}).get("alignment", "counter")
    regime = payload.get("regime", "CHOPPY")
    score = confidence
    if signal != "NO_TRADE":
        score += 20
    if alignment == "aligned":
        score += 15
    if regime == "EXPANSION":
        score += 15
    elif regime == "TRENDING":
        score += 10
    elif regime == "PULLBACK":
        score += 5
    elif regime == "HIGH_VOLATILITY":
        score -= 10
    elif regime == "CHOPPY":
        score -= 15
    return max(0, min(score, 160))


def build_opportunity_scoreboard(user) -> list[dict]:
    rows = []
    for config in TradingBotConfig.objects.filter(user=user).order_by("symbol"):
        snapshot = MarketSnapshot.objects.filter(
            symbol=config.symbol,
            timeframe=config.timeframe_signal,
        ).first()
        if not snapshot:
            rows.append(
                {
                    "symbol": config.symbol,
                    "timeframe": config.timeframe_signal,
                    "signal": "NO_TRADE",
                    "score": 0,
                    "grade": "D",
                    "confidence_score": 0,
                    "regime": "NO_DATA",
                    "regime_label": "No data",
                    "alignment": "unknown",
                    "long_score": 0,
                    "short_score": 0,
                    "is_running": config.is_running,
                    "is_stale": True,
                    "age_seconds": None,
                    "reasons": ["No snapshot collected yet"],
                }
            )
            continue
        payload = snapshot.payload or {}
        alignment = (payload.get("higher_timeframe_bias") or {}).get("alignment", "counter")
        regime = payload.get("regime", "CHOPPY")
        grade = grade_from_context(
            int(payload.get("confidence_score") or 0),
            alignment,
            payload.get("signal", "NO_TRADE"),
            regime,
        )
        age_seconds = int((timezone.now() - snapshot.created_at).total_seconds())
        rows.append(
            {
                "symbol": config.symbol,
                "timeframe": config.timeframe_signal,
                "signal": payload.get("signal", "NO_TRADE"),
                "score": opportunity_score(payload),
                "grade": grade,
                "confidence_score": int(payload.get("confidence_score") or 0),
                "regime": regime,
                "regime_label": payload.get("regime_label", regime.replace("_", " ").title()),
                "alignment": alignment,
                "long_score": int(payload.get("long_score") or 0),
                "short_score": int(payload.get("short_score") or 0),
                "is_running": config.is_running,
                "is_stale": age_seconds > 90,
                "age_seconds": age_seconds,
                "reasons": list(payload.get("reasons", []))[:3],
            }
        )
    return sorted(rows, key=lambda item: item["score"], reverse=True)
