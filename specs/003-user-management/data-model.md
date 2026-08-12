# Data Model: User Management (Admin)

No new models, fields, or migrations. This feature only reads and aggregates data that already exists.

## Existing entities used (read-only)

### `User` (Django's built-in `auth.User`, via `get_user_model()`)

No custom model exists in `apps.accounts` — see `backend/apps/trading/models.py:5` (`User = get_user_model()`), used as-is here too.

Fields read by this feature:
- `id`, `username`, `email` — identity shown in the list.
- `is_staff` — the admin gate (FR-001/FR-002); also the field returned by the new "who am I" endpoint.
- `is_active` — used to render the "deactivated" state (FR-010, Edge Cases).

### `Trade` (`backend/apps/trading/models.py:318-371`)

Fields read for aggregation, unchanged:
- `user` (FK) — the grouping key.
- `status` (`OPEN` / `CLOSED` / `CANCELLED`) — closed trades feed win rate; open trades feed the unrealized-PnL component of profit, matching `TradeStatsView` (`backend/apps/trading/views.py:504-553`).
- `realized_pnl` — summed over closed trades per user.
- `unrealized_pnl` — summed over open trades per user.

## Derived (computed on read, not persisted)

### `UserPerformanceEntry` — one row per user in the new list endpoint's response

| Field | Type | Derivation |
|---|---|---|
| `id` | int | `User.id` |
| `username` | string | `User.username` |
| `email` | string | `User.email` |
| `is_active` | bool | `User.is_active` |
| `total_trades` | int | count of that user's `CLOSED` trades |
| `win_rate` | number \| null | `null` when `total_trades == 0` (FR-006); otherwise `(count of CLOSED trades with realized_pnl > 0) / total_trades * 100` |
| `total_profit` | number | `sum(realized_pnl for CLOSED trades) + sum(unrealized_pnl for OPEN trades)`, same definition as `TradeStatsView.total_profit` |

### `CurrentUser` — response of the new `/api/auth/me` endpoint

| Field | Type | Derivation |
|---|---|---|
| `is_staff` | bool | `User.is_staff` of the authenticated caller |

## Validation / business rules carried over from the spec

- A user with zero `CLOSED` trades MUST show `win_rate: null` (rendered as "No trades yet"), never `0` (FR-006, Edge Cases).
- Sorting by `total_profit` or `win_rate` MUST break ties deterministically by `username` ascending (Edge Cases).
- `is_active == false` users remain in the list (for auditing) but are visually distinguished (FR-010).
