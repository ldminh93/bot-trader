from collections import Counter, defaultdict
from decimal import Decimal

from apps.trading.models import Trade


def _as_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _bucket(rows, key_fn):
    grouped: dict[str, list[Trade]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    return grouped


def _aggregate(label: str, rows: list[Trade]) -> dict:
    total = len(rows)
    wins = sum(1 for row in rows if _as_float(row.realized_pnl) > 0)
    realized = sum(_as_float(row.realized_pnl) for row in rows)
    avg_pnl = realized / total if total else 0
    return {
        "label": label,
        "trades": total,
        "win_rate": (wins / total * 100) if total else 0,
        "realized_pnl": realized,
        "average_realized_pnl": avg_pnl,
    }


RECENT_TRADE_WINDOW = 20


def _profit_factor(rows: list[Trade]) -> float | None:
    """Gross wins / gross losses. None when there are no losses to divide by (undefined, not infinite)."""
    gross_win = sum(_as_float(row.realized_pnl) for row in rows if _as_float(row.realized_pnl) > 0)
    gross_loss = sum(-_as_float(row.realized_pnl) for row in rows if _as_float(row.realized_pnl) < 0)
    if gross_loss == 0:
        return None
    return gross_win / gross_loss


def _avg_hold_minutes(rows: list[Trade]) -> float:
    durations = [
        (row.closed_at - row.opened_at).total_seconds() / 60
        for row in rows
        if row.closed_at and row.opened_at
    ]
    return sum(durations) / len(durations) if durations else 0.0


def _symbol_detail(symbol: str, rows: list[Trade]) -> dict:
    base = _aggregate(symbol, rows)
    recent_rows = sorted(rows, key=lambda row: row.opened_at or row.closed_at, reverse=True)[
        :RECENT_TRADE_WINDOW
    ]
    recent = _aggregate(symbol, recent_rows)
    pnls = [_as_float(row.realized_pnl) for row in rows]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    long_rows = [row for row in rows if row.side == Trade.Side.LONG]
    short_rows = [row for row in rows if row.side == Trade.Side.SHORT]
    long_stats = _aggregate(symbol, long_rows)
    short_stats = _aggregate(symbol, short_rows)
    base.update(
        {
            "recent_win_rate": recent["win_rate"],
            "recent_trades": len(recent_rows),
            "profit_factor": _profit_factor(rows),
            "average_win": sum(wins) / len(wins) if wins else 0.0,
            "average_loss": sum(losses) / len(losses) if losses else 0.0,
            "best_trade": max(pnls) if pnls else 0.0,
            "worst_trade": min(pnls) if pnls else 0.0,
            "avg_hold_minutes": _avg_hold_minutes(rows),
            "long_trades": long_stats["trades"],
            "long_win_rate": long_stats["win_rate"],
            "long_pnl": long_stats["realized_pnl"],
            "short_trades": short_stats["trades"],
            "short_win_rate": short_stats["win_rate"],
            "short_pnl": short_stats["realized_pnl"],
        }
    )
    return base


def build_trade_analytics(user) -> dict:
    closed = list(Trade.objects.filter(user=user, status=Trade.Status.CLOSED))
    by_symbol = sorted(
        (_symbol_detail(symbol, rows) for symbol, rows in _bucket(closed, lambda row: row.symbol).items()),
        key=lambda item: item["realized_pnl"],
        reverse=True,
    )
    by_side = sorted(
        (_aggregate(side, rows) for side, rows in _bucket(closed, lambda row: row.side).items()),
        key=lambda item: item["label"],
    )
    by_hour = sorted(
        (
            _aggregate(f"{hour:02d}:00", rows)
            for hour, rows in _bucket(closed, lambda row: row.opened_at.hour if row.opened_at else -1).items()
        ),
        key=lambda item: item["label"],
    )
    by_close_reason = sorted(
        (
            _aggregate(reason[:72], rows)
            for reason, rows in _bucket(
                closed,
                lambda row: row.close_reason or "No close reason",
            ).items()
        ),
        key=lambda item: item["trades"],
        reverse=True,
    )[:12]

    tag_counter = Counter()
    tag_rows: dict[str, list[Trade]] = defaultdict(list)
    for trade in closed:
        for tag in trade.setup_tags or []:
            tag_counter[tag] += 1
            tag_rows[tag].append(trade)
    by_setup_tag = sorted(
        (_aggregate(tag, tag_rows[tag]) for tag, _ in tag_counter.most_common(20)),
        key=lambda item: item["trades"],
        reverse=True,
    )
    grade_rows: dict[str, list[Trade]] = defaultdict(list)
    for trade in closed:
        grade = "D"
        for tag in trade.setup_tags or []:
            if str(tag).startswith("grade:"):
                grade = str(tag).split(":", 1)[1].upper()
                break
        grade_rows[grade].append(trade)
    by_grade = sorted(
        (_aggregate(grade, rows) for grade, rows in grade_rows.items()),
        key=lambda item: item["label"],
    )

    return {
        "by_symbol": by_symbol,
        "by_side": by_side,
        "by_hour": by_hour,
        "by_close_reason": by_close_reason,
        "by_setup_tag": by_setup_tag,
        "by_grade": by_grade,
    }
