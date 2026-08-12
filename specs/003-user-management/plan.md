# Implementation Plan: User Management (Admin)

**Branch**: `003-user-management` | **Date**: 2026-08-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-user-management/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Add an admin-only page listing every registered user with their win rate and total profit, aggregated from the existing `Trade` model. Backend: one new `IsAdminUser`-gated DRF endpoint that reuses the exact win-rate/profit formulas already in `TradeStatsView` (`backend/apps/trading/views.py:504-553`), grouped across all users instead of `request.user`; one small `GET /api/auth/me` endpoint so the frontend knows whether the logged-in user is staff. Frontend: a new `/users` page following the existing `page.tsx` → `*-console.tsx` → `PageFrame`/`AppShell` pattern, a new nav entry gated on `is_staff`, and a plain HTML table matching `frontend/components/dashboard/trade-table.tsx`'s style. No new services, models, or storage — pure extension of `apps.trading` and `apps.accounts` per Constitution Principle VI.

## Technical Context

**Language/Version**: Python 3.11 (Django 5) for backend; TypeScript / Node 20+ (Next.js 15) for frontend — matches existing `backend/` and `frontend/` toolchains, no change.

**Primary Dependencies**: Django REST Framework + `rest_framework_simplejwt` (backend, already installed); Next.js 15 + Tailwind CSS 4 + `@phosphor-icons/react` (frontend, already installed). No new dependencies required.

**Storage**: PostgreSQL (prod) / SQLite (local) via existing `Trade` and Django `auth.User` models — no schema change, no migration. Figures are computed on read, same as `TradeStatsView` today; nothing new is persisted.

**Testing**: `pytest` under `backend/apps/trading/tests/` for the new aggregation endpoint and the admin-only gate (per Constitution Principle II — new/changed logic needs coverage, though this is read-only reporting logic rather than trading logic per se); manual exercise of the new page against `npm run dev` per Constitution's frontend verification rule.

**Target Platform**: Existing Docker Compose web stack (Django ASGI + Next.js), same as all other pages/endpoints — no new deployment target.

**Project Type**: Web application (Next.js frontend + Django backend) — matches `specs/002-fix-top-movers-sync/plan.md`.

**Performance Goals**: List view interactive in under 2 seconds under normal load (SC-005) for the expected registered-user count (tens to low hundreds of users for this operator tool, not a multi-tenant SaaS scale).

**Constraints**: Must not introduce a role/permission system beyond Django's existing `is_staff` flag (per user-confirmed scope); must not expose any user's performance data to a non-admin request, including in error responses (FR-002).

**Scale/Scope**: Single new admin page + single new list endpoint + single new "who am I" endpoint. No drill-down, no charts, no live updates (deferred per spec Assumptions).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Paper-First Safety Gate** — N/A. This feature does not touch order placement, live-trading flags, or credential handling.
- **II. Test-First for Trading Logic** — Not strictly "trading logic" (indicators/sizing/fills), but the win-rate/profit aggregation is user-facing financial reporting derived from `Trade` records, so it gets `pytest` coverage before merge (new aggregation logic + the admin-only gate) as good practice, even though the principle's NON-NEGOTIABLE scope is narrower. PASS.
- **III. Risk & Position Discipline** — N/A. No position sizing or entry/exit logic is touched.
- **IV. Secure Credential Handling** — N/A. No credentials are read or displayed on this page.
- **V. Graceful Degradation & Observability** — Denied (non-admin) access attempts return a standard DRF 403 with no data body; no new failure mode requiring a mock-data fallback (this is an authenticated internal reporting view, not a market-data integration). PASS.
- **VI. Simplicity Across the Stack** — The feature reuses the existing Next.js/DRF boundary: one new `APIView` in `apps.trading`, one new lightweight `APIView` in `apps.accounts`, one new Next.js route following the established `page.tsx`/`*-console.tsx` convention. No new service, queue, or framework. PASS.

**Result**: No violations. Complexity Tracking table not needed.

**Post-design re-check (after Phase 1)**: `data-model.md` confirms no new models/migrations; `contracts/api.md` confirms both new endpoints are plain `APIView`s using only DRF's built-in `IsAuthenticated`/`IsAdminUser` permission classes on existing apps. Design did not introduce anything that changes the gate results above — still PASS across all six principles.

## Project Structure

### Documentation (this feature)

```text
specs/003-user-management/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── apps/
│   ├── accounts/
│   │   ├── views.py          # + MeView (GET /api/auth/me — returns is_staff for the caller)
│   │   ├── serializers.py    # + CurrentUserSerializer
│   │   ├── urls.py           # + path("auth/me", MeView.as_view())
│   │   └── tests/            # + test_me_view.py (new)
│   └── trading/
│       ├── views.py          # + UserPerformanceListView (GET /api/users/performance, IsAdminUser)
│       ├── urls.py           # + path("users/performance", UserPerformanceListView.as_view())
│       └── tests/            # + test_user_performance_view.py (new)

frontend/
├── app/
│   └── users/
│       └── page.tsx          # new — thin wrapper rendering UsersConsole
├── components/
│   ├── users-console.tsx      # new — fetch + table + sort + search, mirrors trades-console.tsx
│   └── app-shell.tsx          # edit — add gated "Users" nav entry (visible when is_staff)
└── lib/
    ├── api.ts                 # + api.me(), api.userPerformance()
    └── types.ts                # + CurrentUser, UserPerformanceEntry types
```

**Structure Decision**: Extends the existing two-app Django backend (`apps.accounts` for identity/"who am I", `apps.trading` for the trade-derived aggregation) and the existing Next.js `app/<route>/page.tsx` + `components/<name>-console.tsx` convention on the frontend. No new top-level directory, package, or service is introduced.

## Complexity Tracking

*No violations — table omitted.*
