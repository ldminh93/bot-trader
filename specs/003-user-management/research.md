# Research: User Management (Admin)

## 1. How the admin gate is enforced

**Decision**: Use Django's built-in `User.is_staff` flag, enforced server-side via DRF's `permissions.IsAdminUser` on the new endpoint, plus a client-side check (hide the nav entry / redirect) driven by a new `GET /api/auth/me` response.

**Rationale**: `is_staff` already exists on every `auth.User` row (it's the same flag that gates Django's own `/admin/` site per `backend/apps/trading/admin.py`) and the user confirmed no new roles/permissions system should be introduced. `IsAdminUser` is DRF's standard built-in permission class for exactly this flag — zero new code for the check itself, and it returns a bare 403 with no body, satisfying FR-002 ("without revealing any user performance data").

**Alternatives considered**:
- New `Role`/`Permission` model — rejected: user explicitly scoped this out; violates Constitution Principle VI (simplicity) for a feature that only needs a binary admin/non-admin distinction.
- Environment-variable allowlist of admin emails — rejected: not queryable/manageable at runtime, worse than the existing Django mechanism that's already there for free.

## 2. How the frontend learns whether the current user is staff

**Decision**: Add a small `GET /api/auth/me` endpoint (`apps.accounts`) returning `{ "is_staff": bool }` for the authenticated caller. Frontend calls it once (e.g. from `AppShell`) to decide whether to render the "Users" nav link, and the `/users` page itself redirects to `/dashboard` if the call indicates non-staff or fails.

**Rationale**: The project currently has no "who am I" endpoint — `LoginView` (simplejwt's `TokenObtainPairView`) only returns raw access/refresh tokens, no user claims. Decoding a custom JWT claim client-side would require adding a JWT-decode dependency and a custom token serializer just to read one boolean; a one-field GET endpoint following the exact `APIView`/`IsAuthenticated` pattern already used everywhere in `apps.accounts`/`apps.trading` is simpler and matches Principle VI. It also gives a hook other features can reuse later (display name, etc.) without another new endpoint.

**Alternatives considered**:
- Embed `is_staff` as a custom claim in the JWT access token (subclass `TokenObtainPairSerializer`) — rejected: adds a JWT-decoding dependency to the frontend and a custom serializer to override simplejwt's default `LoginView`, for a single boolean that's cheap to fetch via a plain endpoint the client already knows how to call (`lib/api.ts`'s existing `request()` helper).
- Skip the client-side check entirely and rely only on the 403 from the data endpoint — rejected: still needed to decide whether to show the nav link at all, and to redirect politely instead of showing a page that immediately errors.

**Note**: this is a UX convenience only — the authoritative gate is the backend's `IsAdminUser` check on the data endpoint (FR-001/FR-002); the frontend check never gates access to actual data by itself.

## 3. Where the aggregation query lives and how it's computed

**Decision**: New `UserPerformanceListView` in `apps.trading.views`, reusing the same formulas as `TradeStatsView` (`backend/apps/trading/views.py:504-553`) but grouped by user via Django's `.values("user").annotate(...)` instead of filtering to `request.user`:
- `total_profit` = realized PnL of closed trades + unrealized PnL of open trades (same as `TradeStatsView`'s `total_profit`).
- `win_rate` = (closed trades with `realized_pnl__gt=0`) / (total closed trades) × 100, `None`/omitted when the user has zero closed trades (FR-006 "no trades yet" state — distinct from a real 0%).

**Rationale**: SC-004 requires these figures to always match what the user sees on their own stats view — reusing the exact same field names and formulas (rather than re-deriving them) is the only way to guarantee that by construction. Django's ORM `annotate`/`values` grouping is a direct, single-query way to aggregate `Trade` per user without pulling every trade row into Python.

**Alternatives considered**:
- Loop over `User.objects.all()` and call the existing per-user logic in Python — rejected: N+1 query pattern, would not scale even at "tens to low hundreds of users" without being needlessly slow; the grouped-aggregate query is one query for wins/losses/profit plus one for user metadata.
- A new denormalized `UserPerformanceSummary` table updated by a Celery task — rejected: over-engineered for the stated scale (SC-005 just needs sub-2s response for tens–hundreds of users), adds a new sync/consistency problem, and contradicts the spec's own Assumption that slight eventual-consistency lag is fine without needing a background job.

## 4. Sorting, search, and pagination

**Decision**: Server-side sort (`?ordering=total_profit|-total_profit|win_rate|-win_rate`, default `-total_profit`, secondary sort by username for stable tie-breaking per Edge Cases) and search (`?search=<username-or-email-substring>`) as query params on the same list endpoint; return all matching rows in one response (no pagination envelope) for v1.

**Rationale**: At the stated scale (an internal operator tool, not a multi-tenant product), a single unpaginated response kept sortable/searchable server-side is simpler than adding a paginator class, and still meets SC-005's 2-second budget. Doing sort/search server-side (rather than shipping the full list and sorting in the browser) keeps the response shape stable and avoids duplicating the tie-break/ordering rule in two places if the list ever does grow enough to need real pagination.

**Alternatives considered**:
- Client-side sort/search only (fetch everything once, filter in React) — rejected: works fine at today's scale but duplicates ordering logic on the frontend and doesn't leave a clean path to add real pagination later without a breaking response-shape change.
- Full DRF `PageNumberPagination` now — rejected as premature for v1 per FR-009's "usable, not necessarily paginated" bar and the spec's own scale assumption; noted here as the natural next step if user count grows materially (see quickstart.md follow-up note).
