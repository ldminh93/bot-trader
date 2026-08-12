# API Contracts: User Management (Admin)

Both endpoints are added to the existing DRF apps and follow the existing router style in `backend/apps/accounts/urls.py` / `backend/apps/trading/urls.py` (plain `path(...)` entries, no viewsets/routers used elsewhere in this project).

## `GET /api/auth/me`

New endpoint in `apps.accounts`. Tells the frontend whether the caller is an admin, so it can decide whether to show the "Users" nav link and page.

**Auth**: `IsAuthenticated` (project default — see `backend/config/settings.py:84-91`). No new permission class needed.

**Request**: no body, no query params.

**Response** `200 OK`:
```json
{
  "is_staff": false
}
```

**Response** `401 Unauthorized`: standard JWT-missing/expired body, handled by the existing frontend refresh-then-redirect flow in `frontend/lib/api.ts`.

## `GET /api/users/performance`

New endpoint in `apps.trading`. Returns the per-user win-rate/profit list. This is the one endpoint FR-001/FR-002 require to be admin-only.

**Auth**: `IsAdminUser` (DRF built-in, keyed off `request.user.is_staff`) — overrides the project's default `IsAuthenticated` for this view only, the same way `SystemStatusView` already overrides the default to `AllowAny` (`backend/apps/trading/views.py:700-701`).

**Request** (all query params optional):

| Param | Values | Default | Effect |
|---|---|---|---|
| `ordering` | `total_profit`, `-total_profit`, `win_rate`, `-win_rate`, `username`, `-username` | `-total_profit` | Primary sort field/direction. Ties always break by `username` ascending. |
| `search` | free text | none | Case-insensitive substring match against `username` or `email`. |

**Response** `200 OK`:
```json
{
  "results": [
    {
      "id": 12,
      "username": "jane",
      "email": "jane@example.com",
      "is_active": true,
      "total_trades": 34,
      "win_rate": 61.76,
      "total_profit": 482.13
    },
    {
      "id": 7,
      "username": "new_user",
      "email": "new@example.com",
      "is_active": true,
      "total_trades": 0,
      "win_rate": null,
      "total_profit": 0
    }
  ]
}
```

**Response** `403 Forbidden` (non-staff or unauthenticated caller): DRF's standard `IsAdminUser` denial —
```json
{
  "detail": "You do not have permission to perform this action."
}
```
No user data of any kind is included, satisfying FR-002.

## Frontend consumption (`frontend/lib/api.ts`, `frontend/lib/types.ts`)

New typed methods added to the existing `api` object (same pattern as `api.stats()` at `frontend/lib/api.ts:167`):

```ts
export type CurrentUser = { is_staff: boolean };

export type UserPerformanceEntry = {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  total_trades: number;
  win_rate: number | null;
  total_profit: number;
};

// api.me(): Promise<CurrentUser>              -> GET /auth/me
// api.userPerformance(params?: { ordering?: string; search?: string })
//   : Promise<{ results: UserPerformanceEntry[] }> -> GET /users/performance
```
